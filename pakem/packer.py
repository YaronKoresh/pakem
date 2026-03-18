from __future__ import annotations

import concurrent.futures
import datetime
import hashlib
import hmac
import json
import math
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

from pakem.analyze import FileMetadata, is_binary
from pakem.cache import AnalysisCache
from pakem.cloud_io import is_cloud_uri, read_bytes
from pakem.fs import FileEntry, FileWalker
from pakem.gitinfo import get_git_metadata_for_path
from pakem.ignore import IgnoreRules
from pakem.policy import PackagingPolicy
from pakem.redaction import SensitiveFinding, apply_sensitive_data_policy
from pakem.registries import (
    get_analyzer,
    get_compression_profile,
    get_crypto_profile,
    get_serializer_factory,
)
from pakem.semantic import (
    extract_semantic_chunks,
    summarize_chunks_low_priority,
)
from pakem.serialize import Serializer
from pakem.state import FileState, RepoState, compute_file_hash
from pakem.state_backends import resolve_state_backend
from pakem.tokenizer import DEFAULT_TOKEN_COUNTER, TokenCounter
from pakem.validation import is_path_safe


@dataclass(frozen=True)
class FileAnalysisResult:
    rel_path: str
    metadata: FileMetadata
    content_lines: list[str]
    payload_bytes: bytes
    depth: int
    state_sha256: str
    sensitive_findings: list[SensitiveFinding]
    focus_score: int
    skip_reason: str | None = None


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
        encryption_cipher: str = "aes-gcm",
        signing_key: str | None = None,
        verify_signature_key: str | None = None,
        legacy_mode: bool = False,
        analyzer_profile: str = "text",
        split_size: int | None = None,
        sensitive_data_policy: str = "off",
        sensitive_report_out: str | None = None,
        selection_report_out: str | None = None,
        distributed_shards: int | None = None,
        distributed_index: int | None = None,
        dedup_chunks: bool = False,
        cache_mode: str = "off",
        max_file_size: int | None = None,
        max_total_tokens: int | None = None,
        dry_run: bool = False,
        focus_ranking: str = "basic",
        policy: PackagingPolicy | None = None,
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
        self.total_content_size = 0
        self.total_artifact_size = 0

        self.state_path = state_path
        self.delta = delta
        self.model = model
        self.token_counter = token_counter
        self.workers = workers or max(1, (os.cpu_count() or 1) * 4)
        self.output_format = output_format.lower()
        self.compression = compression
        self.encryption_key = encryption_key
        self.encryption_cipher = encryption_cipher
        self.signing_key = signing_key
        self.verify_signature_key = verify_signature_key
        self.legacy_mode = legacy_mode
        self.analyzer_profile = analyzer_profile
        self.split_size = split_size
        self.distributed_shards = distributed_shards
        self.distributed_index = distributed_index
        self.dedup_chunks = dedup_chunks
        self.cache_mode = cache_mode
        self.policy = policy or PackagingPolicy(
            include_patterns=list(
                getattr(self.walker, "include_patterns", []) or []
            ),
            max_file_size=max_file_size,
            max_total_tokens=max_total_tokens,
            sensitive_data_policy=sensitive_data_policy,
            focus_ranking=focus_ranking,
            dry_run=dry_run,
        )
        self.sensitive_data_policy = self.policy.sensitive_data_policy
        self.max_file_size = self.policy.max_file_size
        self.max_total_tokens = self.policy.max_total_tokens
        self.dry_run = self.policy.dry_run
        self.focus_ranking = self.policy.focus_ranking
        self.secret_scanner = self.policy.secret_scanner
        self.sensitive_report_out = (
            Path(sensitive_report_out).resolve()
            if sensitive_report_out is not None
            else None
        )
        self.selection_report_out = (
            Path(selection_report_out).resolve()
            if selection_report_out is not None
            else None
        )
        self._payload_transform_info: dict[str, str] = {
            "compression": self.compression,
            "cipher": "none",
        }
        self.total_sensitive_findings = 0
        self._blocked_sensitive_data = False
        self._sensitive_findings_by_file: list[dict[str, object]] = []
        self.skipped_max_file_size = 0
        self.skipped_token_budget = 0
        self.selected_paths: list[str] = []
        self.skipped_max_file_size_paths: list[str] = []
        self.skipped_token_budget_paths: list[str] = []

        self.state_backend = (
            resolve_state_backend(state_path)
            if state_path is not None
            else None
        )
        self._previous_state = (
            self.state_backend.load()
            if self.state_backend is not None
            else RepoState(files={})
        )
        self._current_state = RepoState(files={})
        self.analysis_cache = AnalysisCache(
            str(self.root_dir),
            enabled=self.cache_mode in {"local", "memory"},
        )

        self.serializer = self._make_serializer(output_format)

    def _make_serializer(self, output_format: str) -> Serializer:
        output_path = None
        if not self.dry_run and not is_cloud_uri(str(self.output_file)):
            output_path = str(self.output_file)
        normalized = (
            "proto" if output_format in ("proto", "protobuf") else output_format
        )
        return get_serializer_factory(normalized)(output_path)

    def _calculate_focus_score(
        self, rel_path: str, metadata: FileMetadata
    ) -> int:
        extension_weights = {
            ".py": 35,
            ".toml": 25,
            ".yml": 22,
            ".yaml": 22,
            ".json": 18,
            ".md": 8,
        }
        status_weights = {
            "added": 40,
            "modified": 30,
            "unchanged": 5,
        }

        score = 0
        score += extension_weights.get(metadata.extension, 12)
        score += status_weights.get(str(metadata.status), 0)
        score += min(metadata.tokens // 200, 12)

        lowered = rel_path.lower()
        if "security" in lowered or "auth" in lowered:
            score += 10
        if "core" in lowered or "cli" in lowered:
            score += 8

        depth = rel_path.count("/") + 1
        score += max(0, 6 - depth)
        return score

    def _tokenize_for_bm25(self, text: str) -> list[str]:
        return [
            token
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text.lower())
            if len(token) > 2
        ]

    def _score_with_bm25(
        self, candidates: list[FileAnalysisResult]
    ) -> dict[str, float]:
        if not candidates:
            return {}

        docs: dict[str, list[str]] = {}
        doc_lens: dict[str, int] = {}
        df: dict[str, int] = {}

        for item in candidates:
            content_sample = "\n".join(item.content_lines[:120])
            tokens = self._tokenize_for_bm25(
                item.rel_path + "\n" + content_sample
            )
            docs[item.rel_path] = tokens
            doc_lens[item.rel_path] = max(1, len(tokens))
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1

        corpus_terms = sorted(df.items(), key=lambda kv: (-kv[1], kv[0]))
        query_terms = [term for term, _ in corpus_terms[:20]]
        if not query_terms:
            return {item.rel_path: 0.0 for item in candidates}

        avgdl = sum(doc_lens.values()) / max(1, len(doc_lens))
        n_docs = len(candidates)
        k1 = 1.5
        b = 0.75

        scores: dict[str, float] = {}
        for item in candidates:
            rel = item.rel_path
            term_freq: dict[str, int] = {}
            for token in docs.get(rel, []):
                term_freq[token] = term_freq.get(token, 0) + 1

            score = 0.0
            for term in query_terms:
                freq = term_freq.get(term, 0)
                if freq == 0:
                    continue
                n_qi = df.get(term, 0)
                idf = math.log(1 + (n_docs - n_qi + 0.5) / (n_qi + 0.5))
                denom = freq + k1 * (1 - b + b * (doc_lens[rel] / avgdl))
                score += idf * (freq * (k1 + 1) / denom)

            scores[rel] = score
        return scores

    def _apply_payload_transforms(self, payload: bytes) -> bytes:
        transformed = get_compression_profile(self.compression).compress(
            payload
        )
        if self.encryption_key:
            if self.encryption_cipher == "none":
                raise ValueError(
                    "Encryption key provided but cipher is set to none"
                )

            transformed, crypto_meta = get_crypto_profile(
                self.encryption_cipher
            ).encrypt(transformed, self.encryption_key)

            self._payload_transform_info = {
                "compression": self.compression,
                **crypto_meta,
            }
        else:
            self._payload_transform_info = {
                "compression": self.compression,
                "cipher": "none",
            }
        return transformed

    def _reverse_payload_transforms(
        self, payload: bytes, transform_info: dict[str, str]
    ) -> bytes:
        transformed = payload

        cipher = str(transform_info.get("cipher", "none"))
        compression = str(transform_info.get("compression", "none"))

        if cipher != "none":
            if not self.encryption_key:
                raise ValueError(
                    "Archive is encrypted. Provide --encrypt-key to restore."
                )

            transformed = get_crypto_profile(cipher).decrypt(
                transformed,
                self.encryption_key,
                transform_info,
                self.legacy_mode,
            )

        transformed = get_compression_profile(compression).decompress(
            transformed
        )

        return transformed

    def _read_pakem_input(self, input_file: str) -> bytes:
        if is_cloud_uri(input_file):
            return read_bytes(input_file)

        path = Path(input_file)
        if path.exists():
            return path.read_bytes()
        parts = sorted(path.parent.glob(f"{path.name}.part*"))
        if not parts:
            raise FileNotFoundError(str(path))
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

        if self._blocked_sensitive_data:
            self._write_sensitive_report(status="blocked")
            self._write_selection_report(status="blocked")
            self._cleanup_output_artifacts()
            print("❌ Packaging blocked due to sensitive data policy")
            return 1

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

        if self.output_format == "pakem" and hasattr(
            self.serializer, "set_payload_transform_info"
        ):
            self.serializer.set_payload_transform_info(
                self._payload_transform_info
            )
            if hasattr(self.serializer, "set_archive_negotiation"):
                self.serializer.set_archive_negotiation(
                    min_reader_version=2,
                    max_reader_version=2,
                    features=[
                        "policy-layer",
                        "selection-report",
                        "authenticated-encryption",
                    ],
                )
            if hasattr(self.serializer, "set_signature_key"):
                self.serializer.set_signature_key(self.signing_key)

        self.total_size = self.total_size
        self.serializer.update_repository_totals(
            total_files=self.total_files,
            total_size=self.total_size,
            total_tokens=self.total_tokens,
            total_content_size=self.total_content_size,
            total_artifact_size=0,
        )

        if self.dry_run:
            self.total_artifact_size = 0
        else:
            self.total_artifact_size = self.serializer.write_to(
                str(self.output_file)
            )

            if self.state_backend is not None:
                self.state_backend.save(self._current_state)

        self._write_sensitive_report(status="ok")
        self._write_selection_report(status="ok")

        if self.cache_mode == "local":
            self.analysis_cache.flush()

        self._print_stats()
        return 0

    def _estimate_artifact_size(self) -> int:
        if self.output_format == "pakem":
            ratio = {
                "none": 1.0,
                "zlib": 0.55,
                "zstd": 0.48,
                "lz4": 0.65,
            }.get(self.compression, 1.0)
            encrypted_overhead = 28 if self.encryption_key else 0
            return int(
                (self.total_content_size * ratio) + 512 + encrypted_overhead
            )

        if self.output_format == "json":
            return int(self.total_content_size * 1.15 + 256)
        if self.output_format == "xml":
            return int(self.total_content_size * 1.28 + 320)
        if self.output_format in {"proto", "protobuf"}:
            return int(self.total_content_size * 1.05 + 192)
        return int(self.total_content_size + 256)

    def _write_sensitive_report(self, status: str) -> None:
        if self.dry_run:
            return
        if self.sensitive_data_policy == "off":
            return
        if self.sensitive_report_out is None:
            return

        report = {
            "status": status,
            "policy": self.sensitive_data_policy,
            "total_files_with_findings": len(self._sensitive_findings_by_file),
            "total_findings": self.total_sensitive_findings,
            "files": self._sensitive_findings_by_file,
        }
        self.sensitive_report_out.parent.mkdir(parents=True, exist_ok=True)
        self.sensitive_report_out.write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

    def _write_selection_report(self, status: str) -> None:
        if self.dry_run:
            return
        if self.selection_report_out is None:
            return

        report = {
            "status": status,
            "total_selected": len(self.selected_paths),
            "selected_paths": self.selected_paths,
            "skipped": {
                "max_file_size": {
                    "count": self.skipped_max_file_size,
                    "paths": self.skipped_max_file_size_paths,
                },
                "token_budget": {
                    "count": self.skipped_token_budget,
                    "paths": self.skipped_token_budget_paths,
                },
            },
        }
        self.selection_report_out.parent.mkdir(parents=True, exist_ok=True)
        self.selection_report_out.write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

    def _cleanup_output_artifacts(self) -> None:
        serializer_file = getattr(self.serializer, "_file", None)
        if serializer_file is not None:
            try:
                serializer_file.close()
            except Exception:
                pass
            try:
                self.serializer._file = None
            except Exception:
                pass

        if self.output_file.exists():
            self.output_file.unlink()
        for part in self.output_file.parent.glob(
            f"{self.output_file.name}.part*"
        ):
            part.unlink()

    def diff(self) -> dict[str, list[str]]:
        added, modified, removed = self._previous_state.diff_paths(
            self._current_state
        )
        return {"added": added, "modified": modified, "removed": removed}

    def _canonical_metadata_for_signature(
        self, metadata: dict[str, object]
    ) -> bytes:
        clone = json.loads(json.dumps(metadata))
        repository = clone.get("repository", {})
        if isinstance(repository, dict):
            repository.pop("signature", None)
            repository.pop("signature_profile", None)
        return json.dumps(
            clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def _verify_archive_signature(
        self, metadata: dict[str, object], payload: bytes
    ) -> None:
        repository = metadata.get("repository", {})
        if not isinstance(repository, dict):
            return
        signature = repository.get("signature")
        if not signature:
            return

        profile = str(repository.get("signature_profile", "hmac-sha256"))
        if profile != "hmac-sha256":
            raise ValueError("Unsupported archive signature profile")

        key = (
            self.verify_signature_key or self.signing_key or self.encryption_key
        )
        if not key:
            raise ValueError(
                "Archive is signed. Provide --verify-signature-key to restore."
            )

        canonical = self._canonical_metadata_for_signature(metadata)
        expected = hmac.new(
            key.encode("utf-8", errors="replace"),
            canonical + payload,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, str(signature)):
            raise ValueError("Archive signature verification failed")

    def restore(self, input_file: str, target_dir: str) -> int:
        if self.output_format != "pakem":
            return 1
        source_text = str(input_file).strip().strip("\"'")
        if not is_cloud_uri(source_text):
            source_text = str(Path(source_text).expanduser().resolve())
        target = (
            Path(str(target_dir).strip().strip("\"'")).expanduser().resolve()
        )
        target.mkdir(parents=True, exist_ok=True)
        data = self._read_pakem_input(source_text)
        if data[:4] != b"PAKM":
            return 1
        version = int(data[4])
        if version not in {1, 2}:
            print("❌ Unsupported pakem archive version")
            return 1
        if version == 1 and not self.legacy_mode:
            print(
                "❌ Legacy archive detected. Re-run with --legacy-mode to restore"
            )
            return 1
        header_len = int.from_bytes(data[5:9], "big")
        metadata_start = 9
        metadata_end = metadata_start + header_len
        metadata = json.loads(data[metadata_start:metadata_end].decode("utf-8"))
        repository_meta = metadata.get("repository", {})

        min_reader = int(repository_meta.get("min_reader_version", 2))
        max_reader = int(repository_meta.get("max_reader_version", 2))
        if not (min_reader <= 2 <= max_reader):
            print("❌ Archive reader negotiation failed for this pakem version")
            return 1

        transform_info = {
            "compression": str(
                repository_meta.get("compression", self.compression)
            ),
            "cipher": str(repository_meta.get("cipher", "none")),
            "kdf": str(repository_meta.get("kdf", "")),
            "kdf_iterations": str(
                repository_meta.get("kdf_iterations", "200000")
            ),
            "kdf_salt_b64": str(repository_meta.get("kdf_salt_b64", "")),
            "nonce_b64": str(repository_meta.get("nonce_b64", "")),
        }

        try:
            payload = self._reverse_payload_transforms(
                data[metadata_end:], transform_info
            )
            self._verify_archive_signature(metadata, payload)
        except ValueError as exc:
            print(f"❌ {exc}")
            return 1

        offset = 0
        for item in metadata.get("files", []):
            length = int(item.get("payload_length", 0))
            item_offset = int(item.get("payload_offset", offset))
            if (
                length < 0
                or item_offset < 0
                or item_offset + length > len(payload)
            ):
                print("❌ Invalid payload length in archive metadata")
                return 1
            chunk = payload[item_offset : item_offset + length]
            if "payload_offset" not in item:
                offset += length
            rel = item.get("path", "")
            if not rel:
                continue
            out = target / rel
            if not is_path_safe(str(target), str(out)):
                return 1
            expected_hash = item.get("hash")
            if expected_hash:
                actual_hash = hashlib.sha256(chunk).hexdigest()
                if actual_hash != str(expected_hash):
                    print(
                        f"❌ Integrity check failed for {rel}: invalid key or corrupted archive"
                    )
                    return 1
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(chunk)
        return 0

    def _process_entries(self) -> None:
        stack: list[int] = []
        pending: list[concurrent.futures.Future[FileAnalysisResult]] = []
        payload_parts: list[tuple[str, bytes]] = []
        analyzer = get_analyzer(self.analyzer_profile)

        def analyze_entry(entry: FileEntry) -> FileAnalysisResult:
            rel_path = entry.rel_path
            metadata, content = analyzer(
                entry.path,
                self.token_counter,
                self.model,
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

            source_sha256 = file_hash

            cache_key = "|".join(
                [
                    file_hash,
                    str(self.sensitive_data_policy),
                    str(self.secret_scanner),
                    str(
                        bool(
                            self.policy.semantic_chunking
                            or self.output_format == "llm-prompt"
                        )
                    ),
                    str(self.policy.summary_mode),
                    str(metadata.extension),
                ]
            )
            cached = self.analysis_cache.get(cache_key)
            if cached is not None:
                cached_lines = [
                    str(line) for line in cached.get("content_lines", [])
                ]
                cached_payload = str(cached.get("payload_text", "")).encode(
                    "utf-8", errors="replace"
                )
                metadata = replace(
                    metadata,
                    tokens=int(cached.get("tokens", 0)),
                    lines=int(cached.get("lines", 0)),
                    sha256=str(cached.get("payload_sha256", "")),
                    status=status,
                    summary=(
                        str(cached.get("summary"))
                        if cached.get("summary") is not None
                        else None
                    ),
                )
                return FileAnalysisResult(
                    rel_path=rel_path,
                    metadata=metadata,
                    content_lines=cached_lines,
                    payload_bytes=cached_payload,
                    depth=rel_path.count("/") + 1,
                    state_sha256=source_sha256,
                    sensitive_findings=[],
                    focus_score=self._calculate_focus_score(rel_path, metadata),
                )

            if (
                self.max_file_size is not None
                and metadata.size > self.max_file_size
            ):
                metadata = replace(metadata, status=status)
                return FileAnalysisResult(
                    rel_path=rel_path,
                    metadata=metadata,
                    content_lines=[],
                    payload_bytes=b"",
                    depth=rel_path.count("/") + 1,
                    state_sha256=source_sha256,
                    sensitive_findings=[],
                    focus_score=0,
                    skip_reason="max_file_size",
                )

            processed_content, sensitive_findings = apply_sensitive_data_policy(
                content,
                self.sensitive_data_policy,
                scanner_mode=self.secret_scanner,
            )

            counter = self.token_counter or DEFAULT_TOKEN_COUNTER
            processed_tokens = counter.count(
                processed_content, model=self.model
            )
            payload_bytes = processed_content.encode("utf-8", errors="replace")
            payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
            content_lines = processed_content.splitlines()

            if (
                self.policy.semantic_chunking
                or self.output_format == "llm-prompt"
            ):
                chunks = extract_semantic_chunks(
                    rel_path,
                    processed_content,
                    metadata.extension,
                )
                rendered: list[str] = []
                for chunk in chunks:
                    rendered.append(
                        f"### {chunk.kind}: {chunk.name} [{chunk.start_line}-{chunk.end_line}]"
                    )
                    rendered.extend(chunk.content.splitlines())
                    rendered.append("")
                if rendered:
                    content_lines = rendered

            summary_text: str | None = None
            if self.policy.summary_mode == "basic":
                summary_text = summarize_chunks_low_priority(
                    extract_semantic_chunks(
                        rel_path,
                        processed_content,
                        metadata.extension,
                    )
                )

            git_meta = None
            if self.policy.git_metadata:
                git_meta = get_git_metadata_for_path(
                    str(self.root_dir),
                    rel_path,
                )

            processed_lines = len(content_lines)

            metadata = replace(
                metadata,
                tokens=processed_tokens,
                lines=processed_lines,
                sha256=payload_sha256,
                status=status,
                git_commit=(git_meta.commit if git_meta else None),
                git_author=(git_meta.author if git_meta else None),
                git_date=(git_meta.date if git_meta else None),
                summary=summary_text,
            )
            focus_score = self._calculate_focus_score(rel_path, metadata)

            self.analysis_cache.put(
                cache_key,
                {
                    "tokens": processed_tokens,
                    "lines": processed_lines,
                    "payload_sha256": payload_sha256,
                    "content_lines": content_lines,
                    "payload_text": processed_content,
                    "summary": summary_text,
                },
            )

            return FileAnalysisResult(
                rel_path=rel_path,
                metadata=metadata,
                content_lines=content_lines,
                payload_bytes=payload_bytes,
                depth=rel_path.count("/") + 1,
                state_sha256=source_sha256,
                sensitive_findings=sensitive_findings,
                focus_score=focus_score,
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

                    pending.append(executor.submit(analyze_entry, entry))

            analyzed_results = [future.result() for future in pending]

            included_results: list[FileAnalysisResult] = []
            for result in analyzed_results:
                if result.skip_reason is not None:
                    if result.skip_reason == "max_file_size":
                        self.skipped_max_file_size += 1
                        self.skipped_max_file_size_paths.append(result.rel_path)
                    continue

                included_results.append(result)

            if self.distributed_shards is not None:
                shard_count = int(self.distributed_shards)
                shard_index = int(self.distributed_index or 0)
                if shard_count <= 0:
                    raise ValueError("distributed_shards must be positive")
                if shard_index < 0 or shard_index >= shard_count:
                    raise ValueError("distributed_index out of range")
                included_results = [
                    item
                    for item in included_results
                    if (
                        int(
                            hashlib.sha256(
                                item.rel_path.encode("utf-8")
                            ).hexdigest(),
                            16,
                        )
                        % shard_count
                    )
                    == shard_index
                ]

            if (
                self.focus_ranking == "basic"
                and self.max_total_tokens is not None
            ):
                bm25_scores = self._score_with_bm25(included_results)
                included_results.sort(
                    key=lambda item: (
                        -bm25_scores.get(item.rel_path, 0.0),
                        -item.focus_score,
                        item.rel_path,
                    )
                )

            used_tokens = 0
            for result in included_results:
                metadata = result.metadata

                if (
                    self.max_total_tokens is not None
                    and used_tokens + metadata.tokens > self.max_total_tokens
                ):
                    self.skipped_token_budget += 1
                    self.skipped_token_budget_paths.append(result.rel_path)
                    continue
                used_tokens += metadata.tokens
                self.selected_paths.append(result.rel_path)

                self._current_state.files[result.rel_path] = FileState(
                    rel_path=result.rel_path,
                    mtime=float(
                        Path(self.root_dir / result.rel_path).stat().st_mtime
                    ),
                    size=metadata.size,
                    sha256=result.state_sha256,
                )

                if self.delta and metadata.status == "unchanged":
                    continue

                self.total_files += 1
                self.total_tokens += metadata.tokens
                self.total_size += metadata.size
                self.total_content_size += len(result.payload_bytes)
                if result.sensitive_findings:
                    finding_summary = ", ".join(
                        f"{item.kind}={item.count}"
                        for item in result.sensitive_findings
                    )
                    self._sensitive_findings_by_file.append(
                        {
                            "path": result.rel_path,
                            "findings": [
                                {"kind": item.kind, "count": item.count}
                                for item in result.sensitive_findings
                            ],
                        }
                    )
                    self.total_sensitive_findings += sum(
                        item.count for item in result.sensitive_findings
                    )
                    print(
                        f"⚠️ Sensitive data detected in {result.rel_path}: {finding_summary}"
                    )
                    if self.sensitive_data_policy == "block":
                        self._blocked_sensitive_data = True
                        return

                self.serializer.add_file(
                    name=Path(self.root_dir / result.rel_path).name,
                    rel_path=result.rel_path,
                    metadata=metadata,
                    content_lines=result.content_lines,
                    depth=result.depth,
                )
                if self.output_format == "pakem":
                    payload_parts.append(
                        (result.rel_path, result.payload_bytes)
                    )

        if self.output_format == "pakem":
            raw_payload = b""
            chunk_map: dict[str, tuple[int, int]] = {}
            if self.dedup_chunks:
                dedup: dict[str, tuple[int, int]] = {}
                unique_parts: list[bytes] = []
                offset = 0
                for rel_path, payload in payload_parts:
                    digest = hashlib.sha256(payload).hexdigest()
                    existing = dedup.get(digest)
                    if existing is None:
                        length = len(payload)
                        dedup[digest] = (offset, length)
                        unique_parts.append(payload)
                        chunk_map[rel_path] = (offset, length)
                        offset += length
                    else:
                        chunk_map[rel_path] = existing
                raw_payload = b"".join(unique_parts)
            else:
                offset = 0
                chunks: list[bytes] = []
                for rel_path, payload in payload_parts:
                    length = len(payload)
                    chunk_map[rel_path] = (offset, length)
                    chunks.append(payload)
                    offset += length
                raw_payload = b"".join(chunks)

            transformed_payload = self._apply_payload_transforms(raw_payload)
            if hasattr(self.serializer, "set_payload_bytes"):
                self.serializer.set_payload_bytes(transformed_payload)
            if hasattr(self.serializer, "apply_payload_chunk_map"):
                self.serializer.apply_payload_chunk_map(chunk_map)
            if hasattr(self.serializer, "set_split_size"):
                self.serializer.set_split_size(self.split_size)

        while stack:
            depth = stack.pop()
            self.serializer.end_directory(depth)

    def _print_stats(self) -> None:
        print(f"📦 Packing repository: {self.root_dir}")
        print("✅ Done! Stats:")
        print(f"   Files:  {self.total_files}")
        print(f"   Source size:   {self.total_size / 1024:.2f} KB")
        print(f"   Content size:  {self.total_content_size / 1024:.2f} KB")
        if self.dry_run:
            estimated = self._estimate_artifact_size()
            print(f"   Estimated artifact size: {estimated / 1024:.2f} KB")
        else:
            print(f"   Artifact size: {self.total_artifact_size / 1024:.2f} KB")
        print(f"   Sensitive findings: {self.total_sensitive_findings}")
        print(f"   Tokens: {self.total_tokens}")
        print(f"   Skipped (max-file-size): {self.skipped_max_file_size}")
        print(f"   Skipped (token-budget): {self.skipped_token_budget}")
        if self.dry_run:
            print("   Output: [dry-run] no artifacts written")
        else:
            print(f"   Output: {self.output_file}")
