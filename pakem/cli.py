from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

from pakem.commands import DiffCommand, PackCommand, RestoreCommand

EXTENSIONS = {
    "xml": ".xml",
    "json": ".json",
    "proto": ".pb",
    "pakem": ".pakem",
}


def resolve_output_path(out: str | None, output_format: str) -> str:
    base = out or "repo"
    expected = EXTENSIONS.get(output_format, ".xml")
    p = Path(base)
    if p.suffix:
        return str(p)
    return str(p.with_suffix(expected))


def _normalize_argv(argv: Iterable[str] | None) -> list[str]:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        return ["pack"]
    if values[0] in {"pack", "diff", "restore", "-h", "--help"}:
        return values
    return ["pack", *values]


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pack, diff, and restore repositories."
    )
    subparsers = parser.add_subparsers(dest="command")

    pack = subparsers.add_parser("pack")
    pack.add_argument("--path", default=".")
    pack.add_argument("--out", default="repo")
    pack.add_argument("--ignore", nargs="*")
    pack.add_argument("--ignore-file")
    pack.add_argument("--state")
    pack.add_argument("--delta", action="store_true")
    pack.add_argument("--list-ignored", action="store_true")
    pack.add_argument("--model")
    pack.add_argument("--workers", type=int)
    pack.add_argument(
        "--format", choices=["xml", "json", "proto", "pakem"], default="xml"
    )
    pack.add_argument("--emit-schema")
    pack.add_argument(
        "--schema-format", choices=["xml", "json", "proto"], default="xml"
    )
    pack.add_argument("--compress", choices=["none", "zlib"], default="none")
    pack.add_argument("--encrypt-key")
    pack.add_argument("--split-size", type=int)

    diff = subparsers.add_parser("diff")
    diff.add_argument("--path", default=".")
    diff.add_argument("--state", required=True)
    diff.add_argument("--out", default="repo")
    diff.add_argument("--diff-out")
    diff.add_argument("--ignore", nargs="*")
    diff.add_argument("--ignore-file")
    diff.add_argument(
        "--format", choices=["xml", "json", "proto", "pakem"], default="xml"
    )

    restore = subparsers.add_parser("restore")
    restore.add_argument("--in", dest="input_file", required=True)
    restore.add_argument("--target", required=True)
    restore.add_argument("--format", choices=["pakem"], default="pakem")
    restore.add_argument("--compress", choices=["none", "zlib"], default="none")
    restore.add_argument("--encrypt-key")

    args = parser.parse_args(_normalize_argv(argv))
    if args.command in {"pack", "diff"}:
        args.out = resolve_output_path(args.out, args.format)

    if args.command == "pack":
        return PackCommand(args).execute()
    if args.command == "diff":
        return DiffCommand(args).execute()
    if args.command == "restore":
        return RestoreCommand(args).execute()
    parser.print_help()
    return 2
