from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path

from pakem.tokenizer import DEFAULT_TOKEN_COUNTER, TokenCounter


@dataclass(frozen=True)
class FileMetadata:
    size: int
    mtime: str
    tokens: int
    lines: int
    extension: str
    sha256: str | None = None
    status: str | None = None
    git_commit: str | None = None
    git_author: str | None = None
    git_date: str | None = None
    summary: str | None = None


def count_tokens(text: str | None, model: str | None = None) -> int:

    if not text:
        return 0

    return DEFAULT_TOKEN_COUNTER.count(text, model=model)


def is_binary(file_path: str, chunk_size: int = 1024) -> bool:
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(chunk_size)
            return b"\0" in chunk
    except Exception:
        return True


def get_file_info(path: str) -> FileMetadata:
    stats = os.stat(path)
    return FileMetadata(
        size=stats.st_size,
        mtime=datetime.datetime.fromtimestamp(stats.st_mtime).isoformat(),
        tokens=0,
        lines=0,
        extension=Path(path).suffix.lower(),
    )


def analyze_text(
    path: str,
    token_counter: TokenCounter | None = None,
    model: str | None = None,
) -> FileMetadata:
    info = get_file_info(path)

    with open(path, encoding="utf-8", errors="replace") as f:
        content = f.read()

    counter = token_counter or DEFAULT_TOKEN_COUNTER
    tokens = counter.count(content, model=model)
    lines = len(content.splitlines())

    return FileMetadata(
        size=info.size,
        mtime=info.mtime,
        tokens=tokens,
        lines=lines,
        extension=info.extension,
        sha256=None,
        status=None,
    )
