from __future__ import annotations

import html


def render_html_diff_report(payload: dict[str, list[str]]) -> str:
    added = payload.get("added", [])
    modified = payload.get("modified", [])
    removed = payload.get("removed", [])

    def section(title: str, items: list[str], css: str) -> str:
        rows = "".join(f"<li>{html.escape(item)}</li>" for item in items)
        if not rows:
            rows = "<li><em>none</em></li>"
        return (
            f"<section class='{css}'>"
            f"<h2>{html.escape(title)} ({len(items)})</h2>"
            f"<ul>{rows}</ul>"
            "</section>"
        )

    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>pakem archive diff</title>"
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;background:#f5f7fb;color:#17202a;padding:24px;}"
        "h1{margin:0 0 16px 0;}"
        "main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;}"
        "section{background:white;border-radius:10px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.08);}"
        "h2{margin-top:0;font-size:1.05rem;}"
        ".added h2{color:#0a7c2f;}.modified h2{color:#9a6700;}.removed h2{color:#a10f2b;}"
        "ul{padding-left:20px;margin:0;}"
        "</style></head><body>"
        "<h1>pakem Diff Report</h1>"
        "<main>"
        f"{section('Added', list(added), 'added')}"
        f"{section('Modified', list(modified), 'modified')}"
        f"{section('Removed', list(removed), 'removed')}"
        "</main></body></html>"
    )
