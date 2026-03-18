from __future__ import annotations

import json
from pathlib import Path


class AnalysisCache:
    def __init__(self, root_dir: str, enabled: bool = True) -> None:
        self.enabled = enabled
        self.path = Path(root_dir) / ".pakem-cache" / "analysis-cache.json"
        self._memory: dict[str, dict[str, object]] = {}
        if self.enabled:
            self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._memory = {
                    str(k): v for k, v in data.items() if isinstance(v, dict)
                }
        except Exception:
            self._memory = {}

    def get(self, key: str) -> dict[str, object] | None:
        if not self.enabled:
            return None
        value = self._memory.get(key)
        if not isinstance(value, dict):
            return None
        return value

    def put(self, key: str, value: dict[str, object]) -> None:
        if not self.enabled:
            return
        self._memory[key] = value

    def flush(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._memory, indent=2),
            encoding="utf-8",
        )
