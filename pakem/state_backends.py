from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from pakem.state import FileState, RepoState

_MEMORY_STATE_STORE: dict[str, dict[str, object]] = {}


class StateBackend(Protocol):
    def load(self) -> RepoState:
        pass

    def save(self, state: RepoState) -> None:
        pass


class JsonFileStateBackend:
    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> RepoState:
        return RepoState.load(self.path)

    def save(self, state: RepoState) -> None:
        state.save(self.path)


class MemoryStateBackend:
    def __init__(self, key: str) -> None:
        self.key = key

    def load(self) -> RepoState:
        payload = _MEMORY_STATE_STORE.get(self.key)
        if not payload:
            return RepoState(files={}, version=2)
        return _repo_state_from_payload(payload)

    def save(self, state: RepoState) -> None:
        _MEMORY_STATE_STORE[self.key] = _repo_state_to_payload(state)


class SQLiteStateBackend:
    def __init__(self, database_path: str, state_key: str) -> None:
        self.database_path = database_path
        self.state_key = state_key

    def _connect(self) -> sqlite3.Connection:
        path = Path(self.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pakem_state (
                state_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """
        )
        conn.commit()
        return conn

    def load(self) -> RepoState:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM pakem_state WHERE state_key = ?",
                (self.state_key,),
            ).fetchone()
        if row is None:
            return RepoState(files={}, version=2)
        payload = json.loads(str(row[0]))
        return _repo_state_from_payload(payload)

    def save(self, state: RepoState) -> None:
        payload = json.dumps(_repo_state_to_payload(state), indent=2)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pakem_state (state_key, payload)
                VALUES (?, ?)
                ON CONFLICT(state_key) DO UPDATE SET payload = excluded.payload
                """,
                (self.state_key, payload),
            )
            conn.commit()


def _repo_state_to_payload(state: RepoState) -> dict[str, object]:
    return {
        "version": state.version,
        "files": {k: asdict(v) for k, v in state.files.items()},
    }


def _repo_state_from_payload(payload: dict[str, object]) -> RepoState:
    version = int(payload.get("version", 1))
    files_payload = payload.get("files", {})
    files: dict[str, FileState] = {}
    if isinstance(files_payload, dict):
        for rel_path, entry in files_payload.items():
            if not isinstance(entry, dict):
                continue
            files[rel_path] = FileState(
                rel_path=rel_path,
                mtime=float(entry.get("mtime", 0.0)),
                size=int(entry.get("size", 0)),
                sha256=str(entry.get("sha256", "")),
            )
    return RepoState(files=files, version=version)


def resolve_state_backend(spec: str) -> StateBackend:
    normalized = str(spec).strip()
    if normalized.startswith("memory://"):
        key = normalized[len("memory://") :].strip() or "default"
        return MemoryStateBackend(key)

    if normalized.startswith("sqlite://"):
        target = normalized[len("sqlite://") :].strip()
        state_key = "default"
        if "?" in target:
            db_path, query = target.split("?", 1)
            for chunk in query.split("&"):
                if not chunk:
                    continue
                if "=" not in chunk:
                    continue
                key, value = chunk.split("=", 1)
                if key == "key" and value:
                    state_key = value
        else:
            db_path = target
        if len(db_path) >= 3 and db_path[0] == "/" and db_path[2] == ":":
            db_path = db_path[1:]
        elif db_path.startswith("///"):
            db_path = db_path[2:]
        if not db_path:
            raise ValueError("sqlite state backend requires a database path")
        return SQLiteStateBackend(db_path, state_key)

    return JsonFileStateBackend(normalized)
