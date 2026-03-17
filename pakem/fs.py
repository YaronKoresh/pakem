from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from pakem.ignore import IgnoreRules


@dataclass(frozen=True)
class FileEntry:
    path: str
    rel_path: str
    is_dir: bool
    is_file: bool


class FileWalker:
    def __init__(
        self,
        root_dir: str,
        ignore_rules: IgnoreRules,
        output_path: str | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        self.root_dir = os.path.abspath(root_dir)
        self.ignore_rules = ignore_rules
        self.output_path = os.path.abspath(output_path) if output_path else None
        self.on_error = on_error

    def walk(self) -> Iterator[FileEntry]:
        yield from self._walk_dir(self.root_dir, "")

    def _walk_dir(
        self, current_path: str, rel_prefix: str
    ) -> Iterator[FileEntry]:
        try:
            entries = sorted(os.listdir(current_path))
        except Exception as exc:
            if self.on_error:
                self.on_error(current_path, exc)
            return

        for name in entries:
            full_path = os.path.join(current_path, name)
            rel_path = os.path.join(rel_prefix, name) if rel_prefix else name
            rel_path = rel_path.replace(os.sep, "/")

            if (
                self.output_path
                and os.path.abspath(full_path) == self.output_path
            ):
                continue

            if self.ignore_rules.should_ignore(full_path, self.root_dir):
                continue

            is_dir = os.path.isdir(full_path)
            is_file = os.path.isfile(full_path)

            yield FileEntry(
                path=full_path,
                rel_path=rel_path,
                is_dir=is_dir,
                is_file=is_file,
            )

            if is_dir:
                yield from self._walk_dir(full_path, rel_path)
