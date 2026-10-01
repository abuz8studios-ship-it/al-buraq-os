"""
AL-BURAQ — bounded JSONL tail reading
=====================================
signal.jsonl and the audit logs grow without bound. Reading them whole on
every poll (/api/jobs, /api/signal/tail, harvest cycles) turns each call
into O(file-size) work. These helpers read only the TAIL of the file
(seek-based, one bounded chunk) so cost stays constant as history grows.

Law: never read an unbounded file when the caller only needs recent rows.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def tail_lines(path: Path, n: int, chunk: int = 262144) -> list[str]:
    """Return up to the last `n` non-empty lines of `path`, reading at most
    `chunk` bytes from the end of the file. Lines older than the chunk are
    simply not visible — callers of tail APIs accept that trade by design."""
    path = Path(path)
    if not path.exists() or n <= 0:
        return []
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size == 0:
        return []
    with open(path, "rb") as f:
        if size <= chunk:
            data = f.read()
        else:
            f.seek(size - chunk)
            data = f.read()
    lines = [ln for ln in data.decode("utf-8", errors="replace").splitlines() if ln.strip()]
    if size > chunk:
        # first line may be truncated mid-way by the seek — drop it
        lines = lines[1:]
    return lines[-n:]


def tail_jsonl(path: Path, n: int, chunk: int = 262144) -> list[dict[str, Any]]:
    """Parse up to the last `n` JSON objects of a .jsonl file (tail-bounded)."""
    out: list[dict[str, Any]] = []
    for ln in tail_lines(path, n, chunk):
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out
