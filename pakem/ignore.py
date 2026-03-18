from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

DEFAULT_PATTERNS: list[str] = [
    ".git",
    ".vscode",
    ".idea",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "venv",
    ".env",
    ".DS_Store",
    "*.lock",
    "*.log",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.svg",
    "*.ico",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.pdf",
    "*.bin",
    "*.exe",
    "*.pyc",
    "*.so",
    "*.dll",
    "*.class",
]


def _read_ignore_file(path: str) -> list[str]:
    if not os.path.exists(path):
        return []

    try:
        with open(path, encoding="utf-8") as f:
            return [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith("#")
            ]
    except Exception:
        return []


class IgnoreRules:
    def __init__(
        self, patterns: list[str], root_dir: str | None = None
    ) -> None:
        self.root_dir = root_dir
        self.patterns = patterns
        self._spec = self._build_spec(patterns)

    @classmethod
    def from_defaults(
        cls,
        root_dir: str,
        extra_patterns: Iterable[str] | None = None,
        extra_ignore_file: str | None = None,
    ) -> IgnoreRules:
        patterns: list[str] = list(DEFAULT_PATTERNS)
        patterns.extend(_read_ignore_file(os.path.join(root_dir, ".gitignore")))
        patterns.extend(
            _read_ignore_file(os.path.join(root_dir, ".dockerignore"))
        )
        if extra_patterns:
            patterns.extend(extra_patterns)

        if extra_ignore_file:
            patterns.extend(_read_ignore_file(extra_ignore_file))

        return cls(patterns, root_dir=root_dir)

    @staticmethod
    def _build_spec(patterns: list[str]):
        try:
            import pathspec

            return pathspec.PathSpec.from_lines(
                pathspec.patterns.GitIgnorePattern, patterns
            )
        except Exception:
            return None

    def should_ignore(self, path: str, root_dir: str) -> bool:
        rel_path = os.path.relpath(path, root_dir).replace(os.path.sep, "/")

        if self._spec is not None:
            return self._spec.match_file(rel_path)

        name = os.path.basename(path)
        for pattern in self.patterns:
            if self._matches(name, rel_path, pattern):
                return True
        return False

    def list_ignored(self, path: str) -> list[tuple[str, str]]:
        ignored: list[tuple[str, str]] = []
        for dirpath, dirnames, filenames in os.walk(path):
            for name in dirnames + filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, path).replace(os.path.sep, "/")
                if self.should_ignore(full, path):
                    ignored.append((rel, self._matching_pattern(full, path)))
        return ignored

    def _matching_pattern(self, path: str, root_dir: str) -> str:
        rel_path = os.path.relpath(path, root_dir).replace(os.path.sep, "/")
        for pattern in self.patterns:
            if self._matches(os.path.basename(path), rel_path, pattern):
                return pattern
        return ""

    @staticmethod
    def _matches(name: str, rel_path: str, pattern: str) -> bool:

        if pattern.endswith("/"):
            return fnmatch.fnmatch(rel_path + "/", pattern)

        return fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(
            rel_path, pattern
        )


import fnmatch
