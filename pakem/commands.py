from __future__ import annotations

import abc
import json
from argparse import Namespace
from pathlib import Path

from pakem.archive_diff import diff_archives
from pakem.cloud_io import write_text
from pakem.fs import FileWalker
from pakem.gitinfo import list_tracked_files
from pakem.ignore import IgnoreRules
from pakem.packer import RepoPacker
from pakem.plugins import load_plugins
from pakem.policy import PackagingPolicy
from pakem.reports import render_html_diff_report
from pakem.tui import explore_archive


class BaseCommand(abc.ABC):
    def __init__(self, args: Namespace) -> None:
        self.args = args

    @abc.abstractmethod
    def execute(self) -> int:
        raise RuntimeError("abstract")


def _sanitize_path_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    while cleaned and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:]
    while cleaned and cleaned[-1] in {'"', "'"}:
        cleaned = cleaned[:-1]
    return cleaned.strip()


def _normalize_path(value: str | None) -> str | None:
    cleaned = _sanitize_path_value(value)
    if not cleaned:
        return None
    if "://" in cleaned:
        return cleaned
    return str(Path(cleaned).expanduser().resolve())


def _normalize_state_spec(value: str | None) -> str | None:
    cleaned = _sanitize_path_value(value)
    if not cleaned:
        return None
    if "://" in cleaned:
        return cleaned
    return str(Path(cleaned).expanduser().resolve())


class PackCommand(BaseCommand):
    def _validate_options(self) -> int:
        if self.args.format != "pakem":
            if self.args.compress != "none":
                print(
                    "❌ --compress is only supported when --format pakem is used"
                )
                return 2
            if self.args.encrypt_key:
                print(
                    "❌ --encrypt-key is only supported when --format pakem is used"
                )
                return 2
            if self.args.split_size:
                print(
                    "❌ --split-size is only supported when --format pakem is used"
                )
                return 2
            if self.args.cipher != "aes-gcm":
                print(
                    "❌ --cipher can only be customized when --format pakem is used"
                )
                return 2
            if getattr(self.args, "sign_key", None):
                print(
                    "❌ --sign-key is only supported when --format pakem is used"
                )
                return 2

        if self.args.format == "pakem":
            if self.args.encrypt_key and self.args.cipher == "none":
                print("❌ --cipher none cannot be used with --encrypt-key")
                return 2
            if self.args.cipher == "legacy-xor" and not self.args.encrypt_key:
                print("❌ --cipher legacy-xor requires --encrypt-key")
                return 2

        return 0

    def execute(self) -> int:
        validation_code = self._validate_options()
        if validation_code != 0:
            return validation_code

        load_plugins(getattr(self.args, "plugin", None))

        root_path = _normalize_path(self.args.path) or str(Path(".").resolve())
        output_path = _normalize_path(self.args.out) or str(
            Path("repo").resolve()
        )
        ignore_file = _normalize_path(self.args.ignore_file)
        state_path = _normalize_state_spec(self.args.state)
        emit_schema = _normalize_path(self.args.emit_schema)
        sensitive_report_out = _normalize_path(self.args.sensitive_report_out)
        selection_report_out = _normalize_path(self.args.selection_report_out)

        ignores = self.args.ignore or []
        ignore_rules = IgnoreRules.from_defaults(
            root_path, ignores, extra_ignore_file=ignore_file
        )
        tracked_paths = (
            list_tracked_files(root_path)
            if bool(getattr(self.args, "tracked_files", False))
            else None
        )

        if self.args.list_ignored:
            for rel_path, pattern in ignore_rules.list_ignored(root_path):
                print(f"{rel_path}  ({pattern})")
            return 0

        if emit_schema:
            from pakem.schemas import get_schema_text

            schema_text = get_schema_text(self.args.schema_format)
            Path(emit_schema).write_text(schema_text, encoding="utf-8")
            return 0

        packer = RepoPacker(
            root_dir=root_path,
            output_file=output_path,
            ignore_rules=ignore_rules,
            walker=FileWalker(
                root_path,
                ignore_rules,
                output_path=output_path,
                include_patterns=self.args.include,
                tracked_paths=tracked_paths,
            ),
            state_path=state_path,
            delta=self.args.delta,
            model=self.args.model,
            workers=self.args.workers,
            output_format=self.args.format,
            compression=self.args.compress,
            encryption_key=self.args.encrypt_key,
            encryption_cipher=self.args.cipher,
            distributed_shards=getattr(self.args, "distributed_shards", None),
            distributed_index=getattr(self.args, "distributed_index", None),
            dedup_chunks=bool(getattr(self.args, "dedup_chunks", False)),
            cache_mode=str(getattr(self.args, "cache_mode", "off")),
            signing_key=getattr(self.args, "sign_key", None),
            split_size=self.args.split_size,
            sensitive_report_out=sensitive_report_out,
            selection_report_out=selection_report_out,
            policy=PackagingPolicy(
                include_patterns=list(self.args.include or []),
                max_file_size=self.args.max_file_size,
                max_total_tokens=self.args.max_total_tokens,
                sensitive_data_policy=self.args.sensitive_data_policy,
                secret_scanner=getattr(self.args, "secret_scanner", "builtin"),
                focus_ranking=self.args.focus_ranking,
                dry_run=self.args.dry_run,
                semantic_chunking=bool(
                    getattr(self.args, "semantic_chunking", False)
                ),
                summary_mode=str(getattr(self.args, "summary_mode", "off")),
                tracked_files_mode=bool(
                    getattr(self.args, "tracked_files", False)
                ),
                git_metadata=bool(getattr(self.args, "git_metadata", False)),
            ),
        )
        return packer.pack()


class DiffCommand(BaseCommand):
    def execute(self) -> int:
        load_plugins(getattr(self.args, "plugin", None))

        root_path = _normalize_path(self.args.path) or str(Path(".").resolve())
        output_path = _normalize_path(self.args.out) or str(
            Path("repo").resolve()
        )
        state_path = _normalize_state_spec(self.args.state)
        ignore_file = _normalize_path(self.args.ignore_file)
        diff_out = _normalize_path(self.args.diff_out)
        html_diff_out = _normalize_path(
            getattr(self.args, "html_diff_out", None)
        )
        sensitive_report_out = _normalize_path(self.args.sensitive_report_out)
        selection_report_out = _normalize_path(self.args.selection_report_out)

        if state_path is None:
            raise ValueError("--state must be a valid path")

        ignores = self.args.ignore or []
        ignore_rules = IgnoreRules.from_defaults(
            root_path, ignores, extra_ignore_file=ignore_file
        )

        tracked_paths = (
            list_tracked_files(root_path)
            if bool(getattr(self.args, "tracked_files", False))
            else None
        )

        packer = RepoPacker(
            root_dir=root_path,
            output_file=output_path,
            ignore_rules=ignore_rules,
            walker=FileWalker(
                root_path,
                ignore_rules,
                output_path=output_path,
                include_patterns=self.args.include,
                tracked_paths=tracked_paths,
            ),
            state_path=state_path,
            delta=True,
            output_format=self.args.format,
            distributed_shards=getattr(self.args, "distributed_shards", None),
            distributed_index=getattr(self.args, "distributed_index", None),
            dedup_chunks=bool(getattr(self.args, "dedup_chunks", False)),
            cache_mode=str(getattr(self.args, "cache_mode", "off")),
            sensitive_report_out=sensitive_report_out,
            selection_report_out=selection_report_out,
            policy=PackagingPolicy(
                include_patterns=list(self.args.include or []),
                max_file_size=self.args.max_file_size,
                max_total_tokens=self.args.max_total_tokens,
                sensitive_data_policy=self.args.sensitive_data_policy,
                secret_scanner=getattr(self.args, "secret_scanner", "builtin"),
                focus_ranking=self.args.focus_ranking,
                dry_run=self.args.dry_run,
                semantic_chunking=bool(
                    getattr(self.args, "semantic_chunking", False)
                ),
                summary_mode=str(getattr(self.args, "summary_mode", "off")),
                tracked_files_mode=bool(
                    getattr(self.args, "tracked_files", False)
                ),
                git_metadata=bool(getattr(self.args, "git_metadata", False)),
            ),
        )
        code = packer.pack()
        if code != 0:
            return code
        diff_payload = packer.diff()
        if diff_out and not self.args.dry_run:
            write_text(
                diff_out, json.dumps(diff_payload, indent=2), encoding="utf-8"
            )
        if html_diff_out and not self.args.dry_run:
            write_text(
                html_diff_out,
                render_html_diff_report(diff_payload),
                encoding="utf-8",
            )
        return 0


class RestoreCommand(BaseCommand):
    def execute(self) -> int:
        input_file = _normalize_path(self.args.input_file)
        target_dir = _normalize_path(self.args.target)

        if input_file is None:
            raise ValueError("--in must be a valid path")
        if target_dir is None:
            raise ValueError("--target must be a valid path")

        ignore_rules = IgnoreRules.from_defaults(target_dir, None)
        packer = RepoPacker(
            root_dir=target_dir,
            output_file=input_file,
            ignore_rules=ignore_rules,
            walker=FileWalker(target_dir, ignore_rules),
            output_format=self.args.format,
            compression=self.args.compress,
            encryption_key=self.args.encrypt_key,
            encryption_cipher=self.args.cipher,
            verify_signature_key=getattr(
                self.args, "verify_signature_key", None
            ),
            legacy_mode=bool(getattr(self.args, "legacy_mode", False)),
        )
        return packer.restore(input_file, target_dir)


class ArchiveDiffCommand(BaseCommand):
    def execute(self) -> int:
        left = _normalize_path(self.args.left)
        right = _normalize_path(self.args.right)
        out = _normalize_path(self.args.out)

        if left is None or right is None:
            raise ValueError("--left and --right must be valid paths")

        payload = diff_archives(
            left,
            right,
            left_format=getattr(self.args, "left_format", None),
            right_format=getattr(self.args, "right_format", None),
        )

        if out:
            write_text(out, json.dumps(payload, indent=2), encoding="utf-8")
        else:
            print(json.dumps(payload, indent=2))

        html_out = _normalize_path(getattr(self.args, "html_out", None))
        if html_out:
            write_text(
                html_out, render_html_diff_report(payload), encoding="utf-8"
            )
        return 0


class ExploreCommand(BaseCommand):
    def execute(self) -> int:
        input_file = _normalize_path(getattr(self.args, "input_file", None))
        if input_file is None:
            raise ValueError("--in must be provided")
        return explore_archive(input_file, use_tui=bool(self.args.tui))


class SetupPrecommitCommand(BaseCommand):
    def execute(self) -> int:
        root = _normalize_path(getattr(self.args, "path", None)) or str(
            Path(".").resolve()
        )
        config = Path(root) / ".pre-commit-config.yaml"
        if config.exists() and not bool(getattr(self.args, "force", False)):
            print("Pre-commit config already exists. Use --force to overwrite.")
            return 0

        content = (
            "repos:\n"
            "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
            "    rev: v0.15.1\n"
            "    hooks:\n"
            "      - id: ruff\n"
            "      - id: ruff-format\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: pakem-check\n"
            "        name: pakem check\n"
            "        entry: poe check\n"
            "        language: system\n"
            "        pass_filenames: false\n"
        )
        config.write_text(content, encoding="utf-8")
        print(f"Created {config}")
        return 0
