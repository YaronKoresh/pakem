from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitFileMetadata:
    commit: str
    author: str
    date: str


def list_tracked_files(root_dir: str) -> set[str]:
    git_dir = _find_git_dir(root_dir)
    if git_dir is None:
        return set()

    index_path = git_dir / "index"
    if not index_path.exists():
        return set()

    try:
        return _parse_git_index(index_path)
    except Exception:
        return set()


def get_git_metadata_for_path(
    root_dir: str, rel_path: str
) -> GitFileMetadata | None:
    try:
        import dulwich.repo
        import dulwich.walk
    except Exception:
        return None

    root = Path(root_dir).resolve()
    try:
        repo = dulwich.repo.Repo.discover(str(root))
    except Exception:
        return None

    rel = rel_path.replace("\\", "/")
    try:
        walker = dulwich.walk.Walker(repo.object_store, [repo.head()])
    except Exception:
        return None

    for entry in walker:
        commit = entry.commit
        tree = repo.get_object(commit.tree)
        if _tree_contains_path(repo, tree, rel):
            author = commit.author.decode("utf-8", errors="replace")
            timestamp = str(commit.author_time)
            return GitFileMetadata(
                commit=commit.id.decode("ascii"),
                author=author,
                date=timestamp,
            )

    return None


def _find_git_dir(root_dir: str) -> Path | None:
    current = Path(root_dir).resolve()
    for candidate in [current, *current.parents]:
        dot_git = candidate / ".git"
        if dot_git.is_dir():
            return dot_git
        if dot_git.is_file():
            content = dot_git.read_text(encoding="utf-8", errors="replace")
            if content.startswith("gitdir:"):
                target = content.split(":", 1)[1].strip()
                return (candidate / target).resolve()
    return None


def _parse_git_index(index_path: Path) -> set[str]:
    data = index_path.read_bytes()
    if len(data) < 12 or data[:4] != b"DIRC":
        return set()

    version = int.from_bytes(data[4:8], "big")
    entries_count = int.from_bytes(data[8:12], "big")
    if version not in {2, 3, 4}:
        return set()

    tracked: set[str] = set()
    offset = 12

    for _ in range(entries_count):
        entry_start = offset
        if offset + 62 > len(data):
            break

        flags = int.from_bytes(data[offset + 60 : offset + 62], "big")
        name_len = flags & 0x0FFF
        offset += 62

        if version >= 3 and (flags & 0x4000):
            if offset + 2 > len(data):
                break
            offset += 2

        if name_len < 0x0FFF:
            if offset + name_len > len(data):
                break
            raw_name = data[offset : offset + name_len]
            offset += name_len
            if offset < len(data) and data[offset] == 0:
                offset += 1
        else:
            name_end = data.find(b"\x00", offset)
            if name_end == -1:
                break
            raw_name = data[offset:name_end]
            offset = name_end + 1

        rel = raw_name.decode("utf-8", errors="replace").replace("\\", "/")
        if rel:
            tracked.add(rel)

        while (offset - entry_start) % 8 != 0 and offset < len(data):
            offset += 1

    return tracked


def _tree_contains_path(repo, tree, rel_path: str) -> bool:
    parts = [part for part in rel_path.split("/") if part]
    if not parts:
        return False

    current = tree
    for index, part in enumerate(parts):
        part_bytes = part.encode("utf-8")
        try:
            mode, sha = current[part_bytes]
        except Exception:
            return False

        if index == len(parts) - 1:
            return True

        try:
            current = repo.get_object(sha)
        except Exception:
            return False

    return False
