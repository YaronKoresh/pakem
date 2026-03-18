from __future__ import annotations

import hashlib
import json
import mmap
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileState:
    rel_path: str
    mtime: float
    size: int
    sha256: str


@dataclass
class RepoState:
    files: dict[str, FileState]
    version: int = 2

    @classmethod
    def load(cls, path: str) -> RepoState:
        p = Path(path)
        if not p.exists():
            return cls(files={}, version=2)

        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return cls(files={}, version=2)

        version = int(data.get("version", 1))
        files: dict[str, FileState] = {}
        for rel_path, entry in data.get("files", {}).items():
            files[rel_path] = FileState(
                rel_path=rel_path,
                mtime=entry.get("mtime", 0.0),
                size=entry.get("size", 0),
                sha256=entry.get("sha256", ""),
            )
        return cls(files=files, version=version)

    def save(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "version": self.version,
                    "files": {k: asdict(v) for k, v in self.files.items()},
                },
                f,
                indent=2,
            )

    def compute_diff(
        self, new_state: RepoState
    ) -> tuple[
        dict[str, FileState], dict[str, FileState], dict[str, FileState]
    ]:
        added: dict[str, FileState] = {}
        modified: dict[str, FileState] = {}
        removed: dict[str, FileState] = {}

        for rel_path, new_entry in new_state.files.items():
            old_entry = self.files.get(rel_path)
            if old_entry is None:
                added[rel_path] = new_entry
                continue

            if old_entry.sha256 != new_entry.sha256:
                modified[rel_path] = new_entry

        for rel_path, old_entry in self.files.items():
            if rel_path not in new_state.files:
                removed[rel_path] = old_entry

        return added, modified, removed

    def diff_paths(
        self, new_state: RepoState
    ) -> tuple[list[str], list[str], list[str]]:
        added, modified, removed = self.compute_diff(new_state)
        return (
            sorted(added.keys()),
            sorted(modified.keys()),
            sorted(removed.keys()),
        )


def compute_file_hash(path: str, chunk_size: int = 8192) -> str:
    hasher = hashlib.sha256()
    file_path = Path(path)
    size = file_path.stat().st_size if file_path.exists() else 0
    with open(path, "rb") as f:
        if size >= 1024 * 1024:
            try:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    hasher.update(mm)
                    return hasher.hexdigest()
            except Exception:
                pass

        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
