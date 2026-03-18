from __future__ import annotations

import abc
import json
from argparse import Namespace
from pathlib import Path

from pakem.fs import FileWalker
from pakem.ignore import IgnoreRules
from pakem.packer import RepoPacker


class BaseCommand(abc.ABC):
    def __init__(self, args: Namespace) -> None:
        self.args = args

    @abc.abstractmethod
    def execute(self) -> int:
        raise RuntimeError("abstract")


class PackCommand(BaseCommand):
    def execute(self) -> int:
        ignores = self.args.ignore or []
        ignore_rules = IgnoreRules.from_defaults(
            self.args.path, ignores, extra_ignore_file=self.args.ignore_file
        )

        if self.args.list_ignored:
            for rel_path, pattern in ignore_rules.list_ignored(self.args.path):
                print(f"{rel_path}  ({pattern})")
            return 0

        if self.args.emit_schema:
            from pakem.schemas import get_schema_text

            schema_text = get_schema_text(self.args.schema_format)
            Path(self.args.emit_schema).write_text(
                schema_text, encoding="utf-8"
            )
            return 0

        packer = RepoPacker(
            root_dir=self.args.path,
            output_file=self.args.out,
            ignore_rules=ignore_rules,
            walker=FileWalker(
                self.args.path, ignore_rules, output_path=self.args.out
            ),
            state_path=self.args.state,
            delta=self.args.delta,
            model=self.args.model,
            workers=self.args.workers,
            output_format=self.args.format,
            compression=self.args.compress,
            encryption_key=self.args.encrypt_key,
            split_size=self.args.split_size,
        )
        return packer.pack()


class DiffCommand(BaseCommand):
    def execute(self) -> int:
        ignores = self.args.ignore or []
        ignore_rules = IgnoreRules.from_defaults(
            self.args.path, ignores, extra_ignore_file=self.args.ignore_file
        )

        packer = RepoPacker(
            root_dir=self.args.path,
            output_file=self.args.out,
            ignore_rules=ignore_rules,
            walker=FileWalker(
                self.args.path, ignore_rules, output_path=self.args.out
            ),
            state_path=self.args.state,
            delta=True,
            output_format=self.args.format,
        )
        code = packer.pack()
        if code != 0:
            return code
        diff_payload = packer.diff()
        if self.args.diff_out:
            Path(self.args.diff_out).write_text(
                json.dumps(diff_payload, indent=2), encoding="utf-8"
            )
        return 0


class RestoreCommand(BaseCommand):
    def execute(self) -> int:
        ignore_rules = IgnoreRules.from_defaults(self.args.target, None)
        packer = RepoPacker(
            root_dir=self.args.target,
            output_file=self.args.input_file,
            ignore_rules=ignore_rules,
            walker=FileWalker(self.args.target, ignore_rules),
            output_format=self.args.format,
            compression=self.args.compress,
            encryption_key=self.args.encrypt_key,
        )
        return packer.restore(self.args.input_file, self.args.target)
