from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from pakem.commands import (
    ArchiveDiffCommand,
    DiffCommand,
    ExploreCommand,
    PackCommand,
    RestoreCommand,
    SetupPrecommitCommand,
)

EXTENSIONS = {
    "xml": ".xml",
    "json": ".json",
    "proto": ".pb",
    "pakem": ".pakem",
    "llm-prompt": ".prompt.md",
}

BYTE_SIZE_RE = re.compile(r"^\s*(\d+)\s*([kmgt]?b?)?\s*$", re.IGNORECASE)


def parse_positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_byte_size(value: str) -> int:
    match = BYTE_SIZE_RE.match(str(value))
    if not match:
        raise argparse.ArgumentTypeError(
            "must be a byte size like 1024, 512KB, 10MB, or 1GB"
        )

    number = int(match.group(1))
    suffix = (match.group(2) or "").lower()
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")

    multipliers = {
        "": 1,
        "b": 1,
        "k": 1024,
        "kb": 1024,
        "m": 1024**2,
        "mb": 1024**2,
        "g": 1024**3,
        "gb": 1024**3,
        "t": 1024**4,
        "tb": 1024**4,
    }
    if suffix not in multipliers:
        raise argparse.ArgumentTypeError(
            "unsupported size suffix; use B, KB, MB, GB, or TB"
        )
    return number * multipliers[suffix]


def resolve_output_path(out: str | None, output_format: str) -> str:
    base = out or "repo"
    expected = EXTENSIONS.get(output_format, ".xml")
    if "://" in base:
        if base.endswith(expected):
            return base
        if base.endswith("/"):
            return f"{base.rstrip('/')}{expected}"
        return f"{base}{expected}"
    p = Path(base)
    if p.suffix:
        return str(p)
    return str(p.with_suffix(expected))


def _normalize_argv(argv: Iterable[str] | None) -> list[str]:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        return ["pack"]
    if values[0] in {
        "pack",
        "diff",
        "restore",
        "archive-diff",
        "explore",
        "setup-precommit",
        "-h",
        "--help",
    }:
        return values
    return ["pack", *values]


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pakem",
        description="Pack, diff, and restore repositories with optional compression and encryption.",
        epilog=(
            "Examples:\n"
            "  pakem pack --path . --format pakem --compress zlib --out archive\n"
            "  pakem diff --path . --state state.json --diff-out changes.json\n"
            "  pakem restore --in archive.pakem --target ./restored --compress zlib"
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    pack = subparsers.add_parser(
        "pack",
        help="Pack a repository into xml/json/proto/pakem output.",
        description="Scan a repository and serialize it to the selected output format.",
    )
    pack.add_argument(
        "--path",
        default=".",
        help="Repository root to pack. Supports relative or absolute paths.",
    )
    pack.add_argument(
        "--out",
        default="repo",
        help="Output path without extension or full output filename.",
    )
    pack.add_argument(
        "--ignore",
        nargs="*",
        help="Extra ignore patterns (glob-like) to apply in addition to defaults.",
    )
    pack.add_argument(
        "--include",
        nargs="*",
        help="Optional allowlist patterns; only matching paths are packed.",
    )
    pack.add_argument(
        "--tracked-files",
        action="store_true",
        help="Only process files tracked by git index in the current repository.",
    )
    pack.add_argument(
        "--git-metadata",
        action="store_true",
        help="Enrich file metadata with git commit, author, and date when available.",
    )
    pack.add_argument(
        "--semantic-chunking",
        action="store_true",
        help="Enable semantic chunk extraction preserving function/class boundaries.",
    )
    pack.add_argument(
        "--summary-mode",
        choices=["off", "basic"],
        default="off",
        help="Optional low-priority summarization mode.",
    )
    pack.add_argument(
        "--plugin",
        nargs="*",
        help="Optional plugin module paths loaded before execution.",
    )
    pack.add_argument(
        "--cache-mode",
        choices=["off", "local", "memory"],
        default="off",
        help="Multi-tier analysis cache mode.",
    )
    pack.add_argument(
        "--dedup-chunks",
        action="store_true",
        help="Enable chunk-level deduplication for pakem payloads.",
    )
    pack.add_argument(
        "--distributed-shards",
        type=parse_positive_int,
        help="Total number of distributed shards.",
    )
    pack.add_argument(
        "--distributed-index",
        type=int,
        help="Zero-based shard index for this runner.",
    )
    pack.add_argument(
        "--max-file-size",
        type=parse_byte_size,
        help="Maximum source file size to include (for example: 512KB, 10MB).",
    )
    pack.add_argument(
        "--max-total-tokens",
        type=parse_positive_int,
        help="Maximum total token budget across included files.",
    )
    pack.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and print stats without writing package, state, or report files.",
    )
    pack.add_argument(
        "--focus-ranking",
        choices=["off", "basic"],
        default="basic",
        help="Ranking strategy used when limits are set (off or basic).",
    )
    pack.add_argument(
        "--ignore-file",
        help="Path to an additional ignore file (same pattern style as .gitignore).",
    )
    pack.add_argument(
        "--state",
        help="Path to state file used for delta comparisons and state persistence.",
    )
    pack.add_argument(
        "--delta",
        action="store_true",
        help="Only include files changed since the previous state file.",
    )
    pack.add_argument(
        "--list-ignored",
        action="store_true",
        help="Print ignored paths and exit without creating an output file.",
    )
    pack.add_argument(
        "--model",
        help="Tokenizer model hint used by token counting.",
    )
    pack.add_argument(
        "--workers",
        type=parse_positive_int,
        help="Number of worker threads for file analysis.",
    )
    pack.add_argument(
        "--format",
        choices=["xml", "json", "proto", "pakem", "llm-prompt"],
        default="xml",
        help="Output format. Use pakem for binary pack/restore workflow.",
    )
    pack.add_argument(
        "--emit-schema",
        help="Write schema definition to this file and exit.",
    )
    pack.add_argument(
        "--schema-format",
        choices=["xml", "json", "proto"],
        default="xml",
        help="Schema format used by --emit-schema.",
    )
    pack.add_argument(
        "--compress",
        choices=["none", "zlib", "zstd", "lz4"],
        default="none",
        help="Payload compression mode.",
    )
    pack.add_argument(
        "--encrypt-key",
        help="Encryption key for payload encryption.",
    )
    pack.add_argument(
        "--cipher",
        choices=["none", "aes-gcm", "chacha20-poly1305", "legacy-xor"],
        default="aes-gcm",
        help="Encryption cipher profile used with --encrypt-key.",
    )
    pack.add_argument(
        "--sign-key",
        help="Optional provenance signing key for pakem archive signatures.",
    )
    pack.add_argument(
        "--split-size",
        type=parse_byte_size,
        help="Split output into parts of this size (for example: 1MB, 512KB).",
    )
    pack.add_argument(
        "--sensitive-data-policy",
        choices=["off", "warn", "redact", "block"],
        default="off",
        help="Sensitive data handling: off, warn, redact, or block before packaging.",
    )
    pack.add_argument(
        "--secret-scanner",
        choices=["builtin", "gitleaks", "trufflehog", "auto", "off"],
        default="builtin",
        help="Secret scanner integration mode.",
    )
    pack.add_argument(
        "--sensitive-report-out",
        help="Optional JSON path for sensitive-data findings report.",
    )
    pack.add_argument(
        "--selection-report-out",
        help="Optional JSON path for selected/skipped path report.",
    )

    diff = subparsers.add_parser(
        "diff",
        help="Build a delta package and optional diff summary against a prior state.",
        description="Compare current repository files against a saved state and produce delta output.",
    )
    diff.add_argument(
        "--path",
        default=".",
        help="Repository root to compare.",
    )
    diff.add_argument(
        "--state",
        required=True,
        help="Existing state file used as diff baseline.",
    )
    diff.add_argument(
        "--out",
        default="repo",
        help="Output path without extension or full output filename.",
    )
    diff.add_argument(
        "--diff-out",
        help="Optional JSON file path for added/modified/removed summary.",
    )
    diff.add_argument(
        "--html-diff-out",
        help="Optional HTML diff report output path.",
    )
    diff.add_argument(
        "--ignore",
        nargs="*",
        help="Extra ignore patterns (glob-like) to apply in addition to defaults.",
    )
    diff.add_argument(
        "--include",
        nargs="*",
        help="Optional allowlist patterns; only matching paths are packed.",
    )
    diff.add_argument(
        "--tracked-files",
        action="store_true",
        help="Only process files tracked by git index in the current repository.",
    )
    diff.add_argument(
        "--git-metadata",
        action="store_true",
        help="Enrich file metadata with git commit, author, and date when available.",
    )
    diff.add_argument(
        "--semantic-chunking",
        action="store_true",
        help="Enable semantic chunk extraction preserving function/class boundaries.",
    )
    diff.add_argument(
        "--summary-mode",
        choices=["off", "basic"],
        default="off",
        help="Optional low-priority summarization mode.",
    )
    diff.add_argument(
        "--plugin",
        nargs="*",
        help="Optional plugin module paths loaded before execution.",
    )
    diff.add_argument(
        "--cache-mode",
        choices=["off", "local", "memory"],
        default="off",
        help="Multi-tier analysis cache mode.",
    )
    diff.add_argument(
        "--dedup-chunks",
        action="store_true",
        help="Enable chunk-level deduplication for pakem payloads.",
    )
    diff.add_argument(
        "--distributed-shards",
        type=parse_positive_int,
        help="Total number of distributed shards.",
    )
    diff.add_argument(
        "--distributed-index",
        type=int,
        help="Zero-based shard index for this runner.",
    )
    diff.add_argument(
        "--max-file-size",
        type=parse_byte_size,
        help="Maximum source file size to include (for example: 512KB, 10MB).",
    )
    diff.add_argument(
        "--max-total-tokens",
        type=parse_positive_int,
        help="Maximum total token budget across included files.",
    )
    diff.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and print stats without writing package, state, diff, or report files.",
    )
    diff.add_argument(
        "--focus-ranking",
        choices=["off", "basic"],
        default="basic",
        help="Ranking strategy used when limits are set (off or basic).",
    )
    diff.add_argument(
        "--ignore-file",
        help="Path to an additional ignore file.",
    )
    diff.add_argument(
        "--format",
        choices=["xml", "json", "proto", "pakem", "llm-prompt"],
        default="xml",
        help="Output format for the generated delta package.",
    )
    diff.add_argument(
        "--sensitive-data-policy",
        choices=["off", "warn", "redact", "block"],
        default="off",
        help="Sensitive data handling: off, warn, redact, or block before packaging.",
    )
    diff.add_argument(
        "--secret-scanner",
        choices=["builtin", "gitleaks", "trufflehog", "auto", "off"],
        default="builtin",
        help="Secret scanner integration mode.",
    )
    diff.add_argument(
        "--sensitive-report-out",
        help="Optional JSON path for sensitive-data findings report.",
    )
    diff.add_argument(
        "--selection-report-out",
        help="Optional JSON path for selected/skipped path report.",
    )

    restore = subparsers.add_parser(
        "restore",
        help="Restore files from a pakem archive.",
        description="Extract and restore files from a pakem archive into a target directory.",
    )
    restore.add_argument(
        "--in",
        dest="input_file",
        required=True,
        help="Input pakem archive path.",
    )
    restore.add_argument(
        "--target",
        required=True,
        help="Destination directory for restored files.",
    )
    restore.add_argument(
        "--format",
        choices=["pakem"],
        default="pakem",
        help="Input archive format.",
    )
    restore.add_argument(
        "--compress",
        choices=["none", "zlib", "zstd", "lz4"],
        default="none",
        help="Compression mode used when the archive was created.",
    )
    restore.add_argument(
        "--encrypt-key",
        help="Decryption key used when the archive was created.",
    )
    restore.add_argument(
        "--cipher",
        choices=["none", "aes-gcm", "chacha20-poly1305", "legacy-xor"],
        default="aes-gcm",
        help="Preferred cipher profile for restore; archive metadata is authoritative.",
    )
    restore.add_argument(
        "--verify-signature-key",
        help="Optional key used to verify archive provenance signature.",
    )
    restore.add_argument(
        "--legacy-mode",
        action="store_true",
        help="Allow restore of legacy archives and ciphers.",
    )

    archive_diff = subparsers.add_parser(
        "archive-diff",
        help="Compare two existing archive artifacts.",
        description="Diff two archives directly without scanning a live repository.",
    )
    archive_diff.add_argument(
        "--left", required=True, help="Left archive path."
    )
    archive_diff.add_argument(
        "--right", required=True, help="Right archive path."
    )
    archive_diff.add_argument(
        "--left-format",
        choices=["xml", "json", "pakem", "proto"],
        help="Optional explicit format for left archive.",
    )
    archive_diff.add_argument(
        "--right-format",
        choices=["xml", "json", "pakem", "proto"],
        help="Optional explicit format for right archive.",
    )
    archive_diff.add_argument(
        "--out",
        help="Optional output path for diff JSON. If omitted, prints to stdout.",
    )
    archive_diff.add_argument(
        "--html-out",
        help="Optional output path for HTML report.",
    )

    explore = subparsers.add_parser(
        "explore",
        help="Explore archive contents in a terminal UI.",
        description="Inspect archive file entries via curses UI or plain output.",
    )
    explore.add_argument(
        "--in", dest="input_file", required=True, help="Archive file path."
    )
    explore.add_argument(
        "--tui",
        action="store_true",
        help="Use curses-based UI instead of plain output.",
    )

    setup_precommit = subparsers.add_parser(
        "setup-precommit",
        help="Create pre-commit configuration for pakem workflow.",
        description="Generate .pre-commit-config.yaml with ruff and pakem checks.",
    )
    setup_precommit.add_argument(
        "--path", default=".", help="Project root path."
    )
    setup_precommit.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing pre-commit config.",
    )

    args = parser.parse_args(_normalize_argv(argv))

    if args.command in {"pack", "diff"}:
        args.out = resolve_output_path(args.out, args.format)

    if args.command == "pack":
        return PackCommand(args).execute()

    if args.command == "diff":
        return DiffCommand(args).execute()

    if args.command == "restore":
        return RestoreCommand(args).execute()

    if args.command == "archive-diff":
        return ArchiveDiffCommand(args).execute()

    if args.command == "explore":
        return ExploreCommand(args).execute()

    if args.command == "setup-precommit":
        return SetupPrecommitCommand(args).execute()

    parser.print_help()
    return 2
