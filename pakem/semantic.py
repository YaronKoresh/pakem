from __future__ import annotations

import ast
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticChunk:
    kind: str
    name: str
    start_line: int
    end_line: int
    content: str


def extract_semantic_chunks(
    file_path: str,
    content: str,
    extension: str,
) -> list[SemanticChunk]:
    ext = extension.lower()
    if ext == ".py":
        chunks = _extract_python_chunks(content)
        if chunks:
            return chunks
    if ext in {".js", ".ts", ".jsx", ".tsx"}:
        chunks = _extract_js_like_chunks(content)
        if chunks:
            return chunks

    lines = content.splitlines()
    return [
        SemanticChunk(
            kind="file",
            name=file_path,
            start_line=1,
            end_line=max(1, len(lines)),
            content=content,
        )
    ]


def summarize_chunks_low_priority(chunks: list[SemanticChunk]) -> str:
    if not chunks:
        return "No semantic chunks extracted."

    kind_counts: dict[str, int] = {}
    names: list[str] = []
    for chunk in chunks:
        kind_counts[chunk.kind] = kind_counts.get(chunk.kind, 0) + 1
        if chunk.name and chunk.name not in names:
            names.append(chunk.name)

    summary_parts = [
        f"{kind}={count}" for kind, count in sorted(kind_counts.items())
    ]
    top_names = ", ".join(names[:6]) if names else "none"
    return (
        f"Semantic summary: {'; '.join(summary_parts)}. Symbols: {top_names}."
    )


def _extract_python_chunks(content: str) -> list[SemanticChunk]:
    try:
        tree = ast.parse(content)
    except Exception:
        return []

    lines = content.splitlines()
    chunks: list[SemanticChunk] = []

    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            start = int(getattr(node, "lineno", 1))
            end = int(getattr(node, "end_lineno", start))
            start = max(1, start)
            end = min(len(lines), max(start, end))
            body = "\n".join(lines[start - 1 : end])
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            chunks.append(
                SemanticChunk(
                    kind=kind,
                    name=str(getattr(node, "name", "unknown")),
                    start_line=start,
                    end_line=end,
                    content=body,
                )
            )

    chunks.sort(key=lambda c: (c.start_line, c.end_line, c.name))
    return chunks


def _extract_js_like_chunks(content: str) -> list[SemanticChunk]:
    lines = content.splitlines()
    joined = "\n".join(lines)
    patterns = [
        ("function", re.compile(r"(?m)^\s*function\s+([A-Za-z0-9_]+)\s*\(")),
        ("class", re.compile(r"(?m)^\s*class\s+([A-Za-z0-9_]+)\b")),
        (
            "function",
            re.compile(
                r"(?m)^\s*(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\([^\)]*\)\s*=>"
            ),
        ),
    ]

    chunks: list[SemanticChunk] = []
    for kind, pattern in patterns:
        for match in pattern.finditer(joined):
            name = match.group(1)
            line_no = joined.count("\n", 0, match.start()) + 1
            end_line = min(len(lines), line_no + 80)
            body = "\n".join(lines[line_no - 1 : end_line])
            chunks.append(
                SemanticChunk(
                    kind=kind,
                    name=name,
                    start_line=line_no,
                    end_line=end_line,
                    content=body,
                )
            )

    dedup: dict[tuple[str, int], SemanticChunk] = {}
    for chunk in chunks:
        dedup[(chunk.name, chunk.start_line)] = chunk

    ordered = sorted(dedup.values(), key=lambda c: (c.start_line, c.name))
    return ordered
