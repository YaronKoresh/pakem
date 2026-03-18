from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PackagingPolicy:
    include_patterns: list[str] = field(default_factory=list)
    max_file_size: int | None = None
    max_total_tokens: int | None = None
    sensitive_data_policy: str = "off"
    secret_scanner: str = "builtin"
    focus_ranking: str = "basic"
    dry_run: bool = False
    semantic_chunking: bool = False
    summary_mode: str = "off"
    tracked_files_mode: bool = False
    git_metadata: bool = False
