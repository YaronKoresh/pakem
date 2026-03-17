from __future__ import annotations

import concurrent.futures
import datetime
import json
import os
import zlib
from dataclasses import dataclass, replace
from pathlib import Path

from pakem.analyze import FileMetadata, analyze_text, is_binary
from pakem.fs import FileEntry, FileWalker
from pakem.ignore import IgnoreRules
from pakem.serialize import JsonSerializer, Serializer, XmlSerializer
from pakem.state import FileState, RepoState, compute_file_hash
from pakem.tokenizer import TokenCounter
from pakem.validation import is_path_safe


@dataclass(frozen=True)
class FileAnalysisResult:
    rel_path: str
    metadata: FileMetadata
    content_lines: list[str]
    payload_bytes: bytes
    depth: int


class RepoPacker:
    def __init__(
        self,
        root_dir: str,
        output_file: str,
        ignore_rules: IgnoreRules,
        walker: FileWalker | None = None,
        state_path: str | None = None,
        delta: bool = False,
        model: str | None = None,
        token_counter: TokenCounter | None = None,
        workers: int | None = None,
        output_format: str = "xml",
        compression: str = "none",
        encryption_key: str | None = None,
        split_size: int | None = None,
    ) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.output_file = Path(output_file).resolve()
        self.ignore_rules = ignore_rules
        self.walker = walker or FileWalker(
            str(self.root_dir), ignore_rules, output_path=str(self.output_file)
        )

        self.total_files = 0
        self.total_tokens = 0
        self.total_size = 0

        self.state_path = state_path
        self.delta = delta
        self.model = model
        self.token_counter = token_counter
        self.workers = workers or max(1, (os.cpu_count() or 1) * 4)
        self.output_format = output_format.lower()
        self.compression = compression
        self.encryption_key = encryption_key
        self.split_size = split_size

        self._previous_state = (
            RepoState.load(state_path)
            if state_path is not None
            else RepoState(files={})
        )
        self._current_state = RepoState(files={})

        self.serializer = self._make_serializer(output_format)

    def _make_serializer(self, output_format: str) -> Serializer:
        if output_format == "json":
            return JsonSerializer(output_path=str(self.output_file))
        if output_format in ("proto", "protobuf"):
            from pakem.serialize import ProtoSerializer

            return ProtoSerializer(output_path=str(self.output_file))
        if output_format == "pakem":
            from pakem.serialize import PakemSerializer

            return PakemSerializer(output_path=str(self.output_file))
        return XmlSerializer(output_path=str(self.output_file))

    def _apply_payload_transforms(self, payload: bytes) -> bytes:
        transformed = payload
        if self.compression == "zlib":
            transformed = zlib.compress(transformed)
        if self.encryption_key:
            key = self.encryption_key.encode("utf-8", errors="replace")
            if key:
                transformed = bytes(
                    byte ^ key[index % len(key)]
                    for index, byte in enumerate(transformed)
                )
        return transformed

    def _reverse_payload_transforms(self, payload: bytes) -> bytes:
        transformed = payload
        if self.encryption_key:
            key = self.encryption_key.encode("utf-8", errors="replace")
            if key:
                transformed = bytes(
                    byte ^ key[index % len(key)]
                    for index, byte in enumerate(transformed)
                )
        if self.compression == "zlib":
            transformed = zlib.decompress(transformed)
        return transformed

    def _read_pakem_input(self, input_file: Path) -> bytes:
        if input_file.exists():
            return input_file.read_bytes()
        parts = sorted(input_file.parent.glob(f"{input_file.name}.part*"))
        if not parts:
            raise FileNotFoundError(str(input_file))
        return b"".join(part.read_bytes() for part in parts)

    def pack(self) -> int:
        now = datetime.datetime.now(datetime.timezone.utc)
        timestamp = now.strftime("%Y-%m-%dT%H:%M:%S GMT")

        self.serializer.start_repository(
            root=str(self.root_dir),
            timestamp=timestamp,
            total_files=0,
            total_size=0,
            total_tokens=0,
        )

        self._process_entries()

        if self.state_path and self.delta:
            added, modified, removed = self._previous_state.diff_paths(
                self._current_state
            )
            if hasattr(self.serializer, "repository"):
                self.serializer.repository["delta"] = {
                    "added": added,
                    "modified": modified,
                    "removed": removed,
                }

        self.serializer.end_repository()

        self.total_size = self.total_size
        self.serializer.update_repository_totals(
            total_files=self.total_files,
            total_size=self.total_size,
            total_tokens=self.total_tokens,
        )

        self.serializer.write_to(str(self.output_file))

        if self.state_path:
            self._current_state.save(self.state_path)

        self._print_stats()
        return 0

    def diff(self) -> dict[str, list[str]]:
        added, modified, removed = self._previous_state.diff_paths(
            self._current_state
        )
        return {"added": added, "modified": modified, "removed": removed}

    def restore(self, input_file: str, target_dir: str) -> int:
        if self.output_format != "pakem":
            return 1
        source = Path(input_file)
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        data = self._read_pakem_input(source)
        if data[:4] != b"PAKM":
            return 1
        header_len = int.from_bytes(data[5:9], "big")
        metadata_start = 9
        metadata_end = metadata_start + header_len
        metadata = json.loads(data[metadata_start:metadata_end].decode("utf-8"))
        payload = data[metadata_end:]
        offset = 0
        for item in metadata.get("files", []):
            length = int(item.get("payload_length", 0))
            chunk = payload[offset : offset + length]
            offset += length
            chunk = self._reverse_payload_transforms(chunk)
            rel = item.get("path", "")
            if not rel:
                continue
            out = target / rel
            if not is_path_safe(str(target), str(out)):
                return 1
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(chunk)
        return 0

    def _process_entries(self) -> None:
        stack: list[int] = []
        pending: list[
            tuple[str, concurrent.futures.Future[FileAnalysisResult]]
        ] = []
        payload_parts: list[bytes] = []

        def analyze_entry(entry: FileEntry) -> FileAnalysisResult:
            rel_path = entry.rel_path
            metadata = analyze_text(
                entry.path,
                token_counter=self.token_counter,
                model=self.model,
            )

            old_state = self._previous_state.files.get(rel_path)
            stat = Path(entry.path).stat()
            mtime = float(stat.st_mtime)

            if (
                old_state
                and old_state.mtime == mtime
                and old_state.size == metadata.size
            ):
                file_hash = old_state.sha256
            else:
                file_hash = compute_file_hash(entry.path)

            if old_state is None:
                status = "added"
            elif old_state.sha256 != file_hash:
                status = "modified"
            else:
                status = "unchanged"

            metadata = replace(metadata, sha256=file_hash, status=status)

            content = Path(entry.path).read_text(
                encoding="utf-8", errors="replace"
            )
            content_lines = content.splitlines()
            payload_bytes = content.encode("utf-8", errors="replace")

            return FileAnalysisResult(
                rel_path=rel_path,
                metadata=metadata,
                content_lines=content_lines,
                payload_bytes=payload_bytes,
                depth=rel_path.count("/") + 1,
            )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.workers
        ) as executor:
            for entry in self.walker.walk():
                if entry.is_dir:
                    depth = entry.rel_path.count("/") + 1
                    self.serializer.start_directory(
                        name=Path(entry.path).name,
                        rel_path=entry.rel_path,
                        depth=depth,
                    )
                    stack.append(depth)
                    continue

                if entry.is_file:
                    if is_binary(entry.path):
                        continue

                    pending.append(
                        (entry.rel_path, executor.submit(analyze_entry, entry))
                    )

            for _, future in pending:
                result = future.result()
                metadata = result.metadata

                self._current_state.files[result.rel_path] = FileState(
                    rel_path=result.rel_path,
                    mtime=float(
                        Path(self.root_dir / result.rel_path).stat().st_mtime
                    ),
                    size=metadata.size,
                    sha256=metadata.sha256 or "",
                )

                if self.delta and metadata.status == "unchanged":
                    continue

                self.total_files += 1
                self.total_tokens += metadata.tokens
                self.total_size += metadata.size

                self.serializer.add_file(
                    name=Path(self.root_dir / result.rel_path).name,
                    rel_path=result.rel_path,
                    metadata=metadata,
                    content_lines=result.content_lines,
                    depth=result.depth,
                )
                if self.output_format == "pakem":
                    payload_parts.append(
                        self._apply_payload_transforms(result.payload_bytes)
                    )

        if self.output_format == "pakem":
            if hasattr(self.serializer, "set_payload_parts"):
                self.serializer.set_payload_parts(payload_parts)
            elif hasattr(self.serializer, "set_payload_bytes"):
                self.serializer.set_payload_bytes(b"".join(payload_parts))
            if hasattr(self.serializer, "set_split_size"):
                self.serializer.set_split_size(self.split_size)

        while stack:
            depth = stack.pop()
            self.serializer.end_directory(depth)

    def _print_stats(self) -> None:
        print(f"📦 Packing repository: {self.root_dir}")
        print("✅ Done! Stats:")
        print(f"   Files:  {self.total_files}")
        print(f"   Size:   {self.total_size / 1024:.2f} KB")
        print(f"   Tokens: {self.total_tokens}")
        print(f"   Output: {self.output_file}")
