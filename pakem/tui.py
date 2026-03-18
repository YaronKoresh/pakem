from __future__ import annotations

import json
import struct
from pathlib import Path


def explore_archive(path: str, use_tui: bool = True) -> int:
    entries = _list_entries(path)
    if not use_tui:
        for item in entries:
            print(item)
        return 0

    try:
        import curses
    except Exception:
        for item in entries:
            print(item)
        return 0

    def _run(stdscr):
        curses.curs_set(0)
        position = 0
        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, "pakem explorer (q to quit)")
            h, w = stdscr.getmaxyx()
            start = max(0, position - (h - 3))
            visible = entries[start : start + max(1, h - 2)]
            for idx, text in enumerate(visible, start=start):
                marker = "> " if idx == position else "  "
                stdscr.addstr(
                    idx - start + 1, 0, (marker + text)[: max(1, w - 1)]
                )
            stdscr.refresh()
            key = stdscr.getch()
            if key in (ord("q"), 27):
                break
            if key in (curses.KEY_DOWN, ord("j")):
                position = min(len(entries) - 1, position + 1)
            if key in (curses.KEY_UP, ord("k")):
                position = max(0, position - 1)

    curses.wrapper(_run)
    return 0


def _list_entries(path: str) -> list[str]:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".json":
        payload = json.loads(p.read_text(encoding="utf-8"))
        return [str(item.get("path", "")) for item in payload.get("files", [])]
    if suffix == ".pakem":
        data = p.read_bytes()
        if len(data) < 9 or data[:4] != b"PAKM":
            return ["invalid archive"]
        header_len = struct.unpack(">I", data[5:9])[0]
        meta = json.loads(data[9 : 9 + header_len].decode("utf-8"))
        return [str(item.get("path", "")) for item in meta.get("files", [])]
    return [
        line
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
