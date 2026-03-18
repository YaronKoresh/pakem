from __future__ import annotations

from pakem.analyze import count_tokens, is_binary
from pakem.ignore import IgnoreRules
from pakem.packer import RepoPacker


def get_ignore_patterns(root_dir: str, user_ignores: list[str] | None):

    rules = IgnoreRules.from_defaults(root_dir, user_ignores)
    return rules.patterns


def should_ignore(path: str, root_dir: str, patterns: list[str]) -> bool:

    rules = IgnoreRules(patterns)
    return rules.should_ignore(path, root_dir)
