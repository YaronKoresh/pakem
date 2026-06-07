from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, TextIO

from pakem.analyze import FileMetadata
from pakem.cloud_io import write_bytes, write_text


class Serializer(Protocol):
    def start_repository(
        self,
        root: str,
        timestamp: str,
        total_files: int,
        total_size: int,
        total_tokens: int,
    ) -> None:
        pass

    def update_repository_totals(
        self,
        total_files: int,
        total_size: int,
        total_tokens: int,
        total_content_size: int = 0,
        total_artifact_size: int = 0,
    ) -> None:
        pass

    def end_repository(self) -> None:
        pass

    def start_directory(self, name: str, rel_path: str, depth: int) -> None:
        pass

    def end_directory(self, depth: int) -> None:
        pass

    def add_file(
        self,
        name: str,
        rel_path: str,
        metadata: FileMetadata,
        content_lines: Iterable[str],
        depth: int,
    ) -> None:
        pass

    def write_to(self, output_path: str) -> int:
        pass


class XmlSerializer:
    def __init__(self, output_path: str | None = None) -> None:
        self.output_path = output_path
        self._file: TextIO | None = None
        self._header_offset: int | None = None
        self._header_line_length: int | None = None
        self._root: str | None = None
        self._timestamp: str | None = None

    @staticmethod
    def _escape_cdata(text: str) -> str:
        return text.replace("]]>", "]]]]>\x3c![CDATA[>")

    def _open(self) -> TextIO:
        if self._file is None:
            if not self.output_path:
                raise ValueError(
                    "No output path provided for streaming serializer"
                )

            mode = "r+" if os.path.exists(self.output_path) else "w+"
            self._file = open(
                self.output_path, mode, encoding="utf-8", newline=""
            )
        return self._file

    def start_repository(
        self,
        root: str,
        timestamp: str,
        total_files: int,
        total_size: int,
        total_tokens: int,
    ) -> None:
        self._root = root
        self._timestamp = timestamp

        if self.output_path:
            f = self._open()
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            self._header_offset = f.tell()

            total_files_s = str(total_files)
            total_size_s = str(total_size)
            total_tokens_s = str(total_tokens)

            line = (
                f'<repository root="{root}" timestamp="{timestamp}" '
                f'total_files="{total_files_s}" total_size="{total_size_s}" '
                f'total_tokens="{total_tokens_s}">\n'
            )
            f.write(line)
            self._header_line_length = len(line.encode("utf-8"))
        else:
            self.lines: list[str] = []
            self.lines.append('<?xml version="1.0" encoding="UTF-8"?>\n')
            self.lines.append(
                f'<repository root="{root}" timestamp="{timestamp}" '
                f'total_files="{total_files}" total_size="{total_size}" '
                f'total_tokens="{total_tokens}">\n'
            )

    def update_repository_totals(
        self,
        total_files: int,
        total_size: int,
        total_tokens: int,
        total_content_size: int = 0,
        total_artifact_size: int = 0,
    ) -> None:
        if not self.output_path or self._file is None:
            return

        assert self._header_offset is not None
        assert self._header_line_length is not None

        f = self._file
        f.seek(self._header_offset)

        total_files_s = str(total_files)
        total_size_s = str(total_size)
        total_tokens_s = str(total_tokens)

        if not self._root or not self._timestamp:
            return

        line = (
            f'<repository root="{self._root}" timestamp="{self._timestamp}" '
            f'total_files="{total_files_s}" total_size="{total_size_s}" '
            f'total_tokens="{total_tokens_s}">\n'
        )
        encoded = line.encode("utf-8")
        if len(encoded) != self._header_line_length:
            f.seek(self._header_offset + self._header_line_length)
            remainder = f.read()
            f.seek(self._header_offset)
            f.write(line)
            f.write(remainder)
            f.truncate()
        else:
            f.write(line)

    def end_repository(self) -> None:
        if self.output_path and self._file:
            self._file.write("</repository>")
        else:
            self.lines.append("</repository>")

    def start_directory(self, name: str, rel_path: str, depth: int) -> None:
        indent = "  " * depth
        if self.output_path and self._file:
            self._file.write(
                f'{indent}<directory name="{name}" path="{rel_path}" depth="{depth}">\n'
            )
        else:
            self.lines.append(
                f'{indent}<directory name="{name}" path="{rel_path}" depth="{depth}">\n'
            )

    def end_directory(self, depth: int) -> None:
        indent = "  " * depth
        if self.output_path and self._file:
            self._file.write(f"{indent}</directory>\n")
        else:
            self.lines.append(f"{indent}</directory>\n")

    def add_file(
        self,
        name: str,
        rel_path: str,
        metadata: FileMetadata,
        content_lines: Iterable[str],
        depth: int,
    ) -> None:
        indent = "  " * depth
        file_attrs = (
            f'name="{name}" path="{rel_path}" size="{metadata.size}" '
            f'tokens="{metadata.tokens}" type="file" extension="{metadata.extension}" '
            f'lines="{metadata.lines}" depth="{depth}"'
        )

        if metadata.sha256:
            file_attrs += f' hash="{metadata.sha256}"'
        if getattr(metadata, "status", None):
            file_attrs += f' status="{metadata.status}"'
        if getattr(metadata, "git_commit", None):
            file_attrs += f' git_commit="{metadata.git_commit}"'
        if getattr(metadata, "git_author", None):
            file_attrs += f' git_author="{metadata.git_author}"'
        if getattr(metadata, "git_date", None):
            file_attrs += f' git_date="{metadata.git_date}"'
        if getattr(metadata, "summary", None):
            safe_summary = str(metadata.summary).replace('"', "'")
            file_attrs += f' summary="{safe_summary}"'

        if self.output_path and self._file:
            self._file.write(f"{indent}<file {file_attrs}>\n")
        else:
            self.lines.append(f"{indent}<file {file_attrs}>\n")

        for index, line in enumerate(content_lines, 1):
            safe_line = self._escape_cdata(line)
            length = len(line)
            leading_ws = length - len(line.lstrip())
            line_attrs = (
                f'index="{index}" length="{length}" indentation="{leading_ws}"'
            )
            if self.output_path and self._file:
                self._file.write(
                    f"{indent}  <line {line_attrs}><![CDATA[{safe_line}]]></line>\n"
                )
            else:
                self.lines.append(
                    f"{indent}  <line {line_attrs}><![CDATA[{safe_line}]]></line>\n"
                )

        if self.output_path and self._file:
            self._file.write(f"{indent}</file>\n")
        else:
            self.lines.append(f"{indent}</file>\n")

    def write_to(self, output_path: str) -> int:
        if self.output_path:
            if self._file:
                self._file.flush()
                self._file.close()
                self._file = None
            return Path(self.output_path).stat().st_size

        return write_text(output_path, "".join(self.lines), encoding="utf-8")


class JsonSerializer:
    def __init__(self, output_path: str | None = None) -> None:
        self.output_path = output_path
        self.repository: dict[str, Any] = {}
        self.directories: list[dict[str, Any]] = []
        self.files: list[dict[str, Any]] = []

    def start_repository(
        self,
        root: str,
        timestamp: str,
        total_files: int,
        total_size: int,
        total_tokens: int,
    ) -> None:
        self.repository = {
            "root": root,
            "timestamp": timestamp,
            "total_files": total_files,
            "total_size": total_size,
            "total_tokens": total_tokens,
        }

    def update_repository_totals(
        self,
        total_files: int,
        total_size: int,
        total_tokens: int,
        total_content_size: int = 0,
        total_artifact_size: int = 0,
    ) -> None:
        self.repository["total_files"] = total_files
        self.repository["total_size"] = total_size
        self.repository["total_tokens"] = total_tokens
        self.repository["total_content_size"] = total_content_size
        self.repository["total_artifact_size"] = total_artifact_size

    def end_repository(self) -> None:

        return

    def start_directory(self, name: str, rel_path: str, depth: int) -> None:
        self.directories.append(
            {"name": name, "path": rel_path, "depth": depth}
        )

    def end_directory(self, depth: int) -> None:

        return

    def add_file(
        self,
        name: str,
        rel_path: str,
        metadata: FileMetadata,
        content_lines: Iterable[str],
        depth: int,
    ) -> None:
        record: dict[str, Any] = {
            "name": name,
            "path": rel_path,
            "size": metadata.size,
            "tokens": metadata.tokens,
            "type": "file",
            "extension": metadata.extension,
            "lines": metadata.lines,
            "depth": depth,
            "content": list(content_lines),
        }
        if metadata.sha256:
            record["hash"] = metadata.sha256
        if getattr(metadata, "status", None):
            record["status"] = metadata.status
        if getattr(metadata, "git_commit", None):
            record["git_commit"] = metadata.git_commit
        if getattr(metadata, "git_author", None):
            record["git_author"] = metadata.git_author
        if getattr(metadata, "git_date", None):
            record["git_date"] = metadata.git_date
        if getattr(metadata, "summary", None):
            record["summary"] = metadata.summary

        self.files.append(record)

    def write_to(self, output_path: str) -> int:
        payload = {
            "repository": self.repository,
            "directories": self.directories,
            "files": self.files,
        }

        text = __import__("json").dumps(payload, indent=2, ensure_ascii=False)
        return write_text(output_path, text, encoding="utf-8")


class ProtoSerializer:
    def __init__(self, output_path: str | None = None) -> None:
        self.output_path = output_path
        self._message_cls = __import__(
            "pakem.proto", fromlist=["get_repository_message_class"]
        ).get_repository_message_class()
        self._message = None

    def start_repository(
        self,
        root: str,
        timestamp: str,
        total_files: int,
        total_size: int,
        total_tokens: int,
    ) -> None:
        self._message = self._message_cls()
        self._message.root = root
        self._message.timestamp = timestamp
        self._message.total_files = total_files
        self._message.total_size = total_size
        self._message.total_tokens = total_tokens

    def update_repository_totals(
        self,
        total_files: int,
        total_size: int,
        total_tokens: int,
        total_content_size: int = 0,
        total_artifact_size: int = 0,
    ) -> None:
        if self._message is None:
            return
        self._message.total_files = total_files
        self._message.total_size = total_size
        self._message.total_tokens = total_tokens

    def end_repository(self) -> None:
        return

    def start_directory(self, name: str, rel_path: str, depth: int) -> None:
        if self._message is None:
            return
        d = self._message.directories.add()
        d.name = name
        d.path = rel_path
        d.depth = depth

    def end_directory(self, depth: int) -> None:
        return

    def add_file(
        self,
        name: str,
        rel_path: str,
        metadata: FileMetadata,
        content_lines: Iterable[str],
        depth: int,
    ) -> None:
        if self._message is None:
            return
        f = self._message.files.add()
        f.name = name
        f.path = rel_path
        f.size = metadata.size
        f.tokens = metadata.tokens
        f.type = "file"
        f.extension = metadata.extension
        f.lines = metadata.lines
        f.depth = depth
        if metadata.sha256:
            f.hash = metadata.sha256
        if getattr(metadata, "status", None):
            f.status = metadata.status
        f.content.extend(content_lines)

    def write_to(self, output_path: str) -> int:
        if self._message is None:
            return 0
        data = self._message.SerializeToString()
        return write_bytes(output_path, data)


class PakemSerializer:
    MAGIC = b"PAKM"
    VERSION = 2

    def __init__(self, output_path: str | None = None) -> None:
        self.output_path = output_path
        self.repository: dict[str, Any] = {}
        self.directories: list[dict[str, Any]] = []
        self.files: list[dict[str, Any]] = []
        self._payload_parts: list[bytes] = []
        self._raw_bytes: bytes = b""
        self._split_size: int | None = None
        self._signature_key: str | None = None
        self._dedup_enabled: bool = False

    def start_repository(
        self,
        root: str,
        timestamp: str,
        total_files: int,
        total_size: int,
        total_tokens: int,
    ) -> None:
        self.repository = {
            "root": root,
            "timestamp": timestamp,
            "total_files": total_files,
            "total_size": total_size,
            "total_tokens": total_tokens,
            "format": "pakem",
        }

    def update_repository_totals(
        self,
        total_files: int,
        total_size: int,
        total_tokens: int,
        total_content_size: int = 0,
        total_artifact_size: int = 0,
    ) -> None:
        self.repository["total_files"] = total_files
        self.repository["total_size"] = total_size
        self.repository["total_tokens"] = total_tokens
        self.repository["total_content_size"] = total_content_size
        self.repository["total_artifact_size"] = total_artifact_size

    def end_repository(self) -> None:
        return

    def start_directory(self, name: str, rel_path: str, depth: int) -> None:
        self.directories.append(
            {"name": name, "path": rel_path, "depth": depth}
        )

    def end_directory(self, depth: int) -> None:
        return

    def add_file(
        self,
        name: str,
        rel_path: str,
        metadata: FileMetadata,
        content_lines: Iterable[str],
        depth: int,
    ) -> None:
        content = "\n".join(content_lines).encode("utf-8", errors="replace")
        self._payload_parts.append(content)
        item: dict[str, Any] = {
            "name": name,
            "path": rel_path,
            "size": metadata.size,
            "tokens": metadata.tokens,
            "type": "file",
            "extension": metadata.extension,
            "lines": metadata.lines,
            "depth": depth,
            "payload_length": len(content),
        }
        if metadata.sha256:
            item["hash"] = metadata.sha256
        if getattr(metadata, "status", None):
            item["status"] = metadata.status
        if getattr(metadata, "git_commit", None):
            item["git_commit"] = metadata.git_commit
        if getattr(metadata, "git_author", None):
            item["git_author"] = metadata.git_author
        if getattr(metadata, "git_date", None):
            item["git_date"] = metadata.git_date
        if getattr(metadata, "summary", None):
            item["summary"] = metadata.summary
        self.files.append(item)

    def set_payload_bytes(self, payload: bytes) -> None:
        self._raw_bytes = payload

    def set_payload_parts(self, parts: list[bytes]) -> None:
        self._payload_parts = parts
        self._raw_bytes = b"".join(parts)
        for index, part in enumerate(parts):
            if index < len(self.files):
                self.files[index]["payload_length"] = len(part)

    def set_payload_transform_info(self, info: dict[str, str]) -> None:
        if not isinstance(info, dict):
            return
        for key, value in info.items():
            self.repository[key] = value

    def set_split_size(self, split_size: int | None) -> None:
        self._split_size = split_size if split_size and split_size > 0 else None

    def set_dedup_enabled(self, enabled: bool) -> None:
        self._dedup_enabled = bool(enabled)

    def apply_payload_chunk_map(
        self, chunk_map: dict[str, tuple[int, int]]
    ) -> None:
        if not chunk_map:
            return
        for item in self.files:
            rel = str(item.get("path", ""))
            mapping = chunk_map.get(rel)
            if not mapping:
                continue
            offset, length = mapping
            item["payload_offset"] = int(offset)
            item["payload_length"] = int(length)

    def set_archive_negotiation(
        self,
        min_reader_version: int,
        max_reader_version: int,
        features: list[str] | None = None,
    ) -> None:
        self.repository["min_reader_version"] = int(min_reader_version)
        self.repository["max_reader_version"] = int(max_reader_version)
        self.repository["features"] = list(features or [])

    def set_signature_key(self, key: str | None) -> None:
        self._signature_key = key

    def _canonical_signature_payload(
        self, metadata: dict[str, Any], payload: bytes
    ) -> bytes:
        clone = json.loads(json.dumps(metadata))
        repository = clone.get("repository", {})
        if isinstance(repository, dict):
            repository.pop("signature", None)
            repository.pop("signature_profile", None)
        stable = json.dumps(
            clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return stable + payload

    def _build(self) -> bytes:
        payload = (
            self._raw_bytes
            if self._raw_bytes
            else b"".join(self._payload_parts)
        )
        metadata = {
            "repository": self.repository,
            "directories": self.directories,
            "files": self.files,
            "payload_size": len(payload),
        }

        if self._signature_key:
            signature = hmac.new(
                self._signature_key.encode("utf-8", errors="replace"),
                self._canonical_signature_payload(metadata, payload),
                hashlib.sha256,
            ).hexdigest()
            self.repository["signature_profile"] = "hmac-sha256"
            self.repository["signature"] = signature
            metadata["repository"] = self.repository

        metadata_bytes = json.dumps(metadata, ensure_ascii=False).encode(
            "utf-8"
        )
        return (
            self.MAGIC
            + bytes([self.VERSION])
            + struct.pack(">I", len(metadata_bytes))
            + metadata_bytes
            + payload
        )

    def write_to(self, output_path: str) -> int:
        blob = self._build()
        if self._split_size and len(blob) > self._split_size:
            index = 1
            offset = 0
            total_written = 0
            while offset < len(blob):
                part = blob[offset : offset + self._split_size]
                part_path = f"{output_path}.part{index:03d}"
                write_bytes(part_path, part)
                total_written += len(part)
                offset += self._split_size
                index += 1
            return total_written
        return write_bytes(output_path, blob)


class LlmPromptSerializer:
    def __init__(self, output_path: str | None = None) -> None:
        self.output_path = output_path
        self.repository: dict[str, Any] = {}
        self.files: list[dict[str, Any]] = []

    def start_repository(
        self,
        root: str,
        timestamp: str,
        total_files: int,
        total_size: int,
        total_tokens: int,
    ) -> None:
        self.repository = {
            "root": root,
            "timestamp": timestamp,
            "total_files": total_files,
            "total_size": total_size,
            "total_tokens": total_tokens,
        }

    def update_repository_totals(
        self,
        total_files: int,
        total_size: int,
        total_tokens: int,
        total_content_size: int = 0,
        total_artifact_size: int = 0,
    ) -> None:
        self.repository["total_files"] = total_files
        self.repository["total_size"] = total_size
        self.repository["total_tokens"] = total_tokens
        self.repository["total_content_size"] = total_content_size
        self.repository["total_artifact_size"] = total_artifact_size

    def end_repository(self) -> None:
        return

    def start_directory(self, name: str, rel_path: str, depth: int) -> None:
        return

    def end_directory(self, depth: int) -> None:
        return

    def add_file(
        self,
        name: str,
        rel_path: str,
        metadata: FileMetadata,
        content_lines: Iterable[str],
        depth: int,
    ) -> None:
        self.files.append(
            {
                "name": name,
                "path": rel_path,
                "tokens": metadata.tokens,
                "summary": getattr(metadata, "summary", None),
                "content": list(content_lines),
            }
        )

    def write_to(self, output_path: str) -> int:
        lines: list[str] = []
        lines.append("# LLM Prompt Profile")
        lines.append("")
        lines.append(f"Root: {self.repository.get('root', '')}")
        lines.append(f"Timestamp: {self.repository.get('timestamp', '')}")
        lines.append(f"Total files: {self.repository.get('total_files', 0)}")
        lines.append(f"Total tokens: {self.repository.get('total_tokens', 0)}")
        lines.append("")

        ordered = sorted(self.files, key=lambda item: str(item.get("path", "")))
        for item in ordered:
            lines.append(f"## File: {item['path']}")
            lines.append(f"Tokens: {item.get('tokens', 0)}")
            summary = item.get("summary")
            if summary:
                lines.append(f"Summary: {summary}")
            lines.append("```")
            lines.extend(item.get("content", []))
            lines.append("```")
            lines.append("")

        text = "\n".join(lines).rstrip() + "\n"
        return write_text(output_path, text, encoding="utf-8")
