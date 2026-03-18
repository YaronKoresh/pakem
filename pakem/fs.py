from __future__ import annotations

import fnmatch
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
        include_patterns: list[str] | None = None,
        tracked_paths: set[str] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        self.root_dir = os.path.abspath(root_dir)
        self.ignore_rules = ignore_rules
        self.output_path = os.path.abspath(output_path) if output_path else None
        self.include_patterns = [
            pattern.strip()
            for pattern in (include_patterns or [])
            if str(pattern).strip()
        ]
        self.tracked_paths = set(tracked_paths or set())
        self.on_error = on_error

    def _matches_include_pattern(self, rel_path: str, pattern: str) -> bool:
        normalized_pattern = pattern.replace(os.path.sep, "/")
        normalized_rel = rel_path.replace(os.path.sep, "/")

        if normalized_pattern.endswith("/"):
            prefix = normalized_pattern.rstrip("/")
            return normalized_rel == prefix or normalized_rel.startswith(
                prefix + "/"
            )

        return (
            fnmatch.fnmatch(normalized_rel, normalized_pattern)
            or fnmatch.fnmatch(
                os.path.basename(normalized_rel), normalized_pattern
            )
            or normalized_rel.startswith(normalized_pattern.rstrip("/") + "/")
        )

    def _is_included(self, rel_path: str) -> bool:
        if not self.include_patterns:
            return True

        parent_paths = [rel_path]
        cursor = rel_path
        while "/" in cursor:
            cursor = cursor.rsplit("/", 1)[0]
            parent_paths.append(cursor)

        for pattern in self.include_patterns:
            if any(
                self._matches_include_pattern(candidate, pattern)
                for candidate in parent_paths
            ):
                return True
        return False

    def walk(self) -> Iterator[FileEntry]:
        yield from self._walk_dir(self.root_dir, "")

    def _is_tracked(self, rel_path: str, is_dir: bool) -> bool:
        if not self.tracked_paths:
            return True
        normalized = rel_path.replace(os.sep, "/")
        if normalized in self.tracked_paths:
            return True
        if is_dir:
            prefix = normalized.rstrip("/") + "/"
            return any(path.startswith(prefix) for path in self.tracked_paths)
        return False

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

            is_dir = os.path.isdir(full_path)
            is_file = os.path.isfile(full_path)

            if not self._is_tracked(rel_path, is_dir=is_dir):
                continue

            is_included = self._is_included(rel_path)
            if not is_included:
                continue

            if not self.include_patterns and self.ignore_rules.should_ignore(
                full_path, self.root_dir
            ):
                continue

            yield FileEntry(
                path=full_path,
                rel_path=rel_path,
                is_dir=is_dir,
                is_file=is_file,
            )

            if is_dir:
                yield from self._walk_dir(full_path, rel_path)
