"""
AL-BURAQ — Layered Memory Store (L1 Flash, L2 Session, L3 Long-Term, L4 Vault)
==============================================================================
Provides sovereign, local memory persistence across 4 distinct cognitive layers:
  - L1: Flash / Working memory (short-lived, ephemeral fast cache)
  - L2: Session memory (conversation turns, active task context)
  - L3: Long-term memory (learned patterns, reflections, user preferences)
  - L4: Archive / Vault (durable records, audit logs, mission histories)

Pure stdlib sqlite3 + JSON fallback — zero external dependencies, 100% sovereign.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class MemoryStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "memory.sqlite"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _c(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self) -> None:
        with self._c() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id TEXT PRIMARY KEY,
                    layer TEXT NOT NULL,       -- L1, L2, L3, L4
                    key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,            -- JSON object
                    session_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_mem_layer ON memory_entries(layer)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_mem_key ON memory_entries(key)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_mem_session ON memory_entries(session_id)")

    def store(
        self,
        key: str,
        content: str,
        layer: str = "L3",
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        entry_id: str | None = None,
    ) -> dict[str, Any]:
        layer = layer.upper()
        if layer not in ("L1", "L2", "L3", "L4"):
            layer = "L3"
        now = time.time()
        title = title or key
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        eid = entry_id or f"mem_{int(now * 1000)}_{abs(hash(key)) % 10000:04d}"

        with self._c() as c:
            existing = c.execute("SELECT id FROM memory_entries WHERE id = ? OR (layer = ? AND key = ?)", (eid, layer, key)).fetchone()
            if existing:
                eid = existing["id"]
                c.execute(
                    """
                    UPDATE memory_entries
                    SET title = ?, content = ?, metadata = ?, session_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (title, content, meta_json, session_id, now, eid),
                )
            else:
                c.execute(
                    """
                    INSERT INTO memory_entries (id, layer, key, title, content, metadata, session_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (eid, layer, key, title, content, meta_json, session_id, now, now),
                )

        return {
            "id": eid,
            "layer": layer,
            "key": key,
            "title": title,
            "content": content,
            "metadata": metadata or {},
            "session_id": session_id,
            "updated_at": now,
        }

    def get(self, entry_id: str) -> dict[str, Any] | None:
        with self._c() as c:
            row = c.execute("SELECT * FROM memory_entries WHERE id = ?", (entry_id,)).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def get_by_key(self, key: str, layer: str | None = None) -> dict[str, Any] | None:
        with self._c() as c:
            if layer:
                row = c.execute("SELECT * FROM memory_entries WHERE key = ? AND layer = ? ORDER BY updated_at DESC LIMIT 1", (key, layer.upper())).fetchone()
            else:
                row = c.execute("SELECT * FROM memory_entries WHERE key = ? ORDER BY updated_at DESC LIMIT 1", (key,)).fetchone()
            if not row:
                return None
            return self._row_to_dict(row)

    def list_layer(self, layer: str, limit: int = 50) -> list[dict[str, Any]]:
        layer = layer.upper()
        with self._c() as c:
            rows = c.execute(
                "SELECT * FROM memory_entries WHERE layer = ? ORDER BY updated_at DESC LIMIT ?",
                (layer, limit),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def list_all(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._c() as c:
            rows = c.execute(
                "SELECT * FROM memory_entries ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = f"%{query.strip().lower()}%"
        with self._c() as c:
            rows = c.execute(
                """
                SELECT * FROM memory_entries
                WHERE LOWER(key) LIKE ? OR LOWER(title) LIKE ? OR LOWER(content) LIKE ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (q, q, q, limit),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def delete(self, entry_id: str) -> bool:
        with self._c() as c:
            res = c.execute("DELETE FROM memory_entries WHERE id = ?", (entry_id,))
            return res.rowcount > 0

    def stats(self) -> dict[str, Any]:
        with self._c() as c:
            counts = dict(c.execute("SELECT layer, COUNT(*) FROM memory_entries GROUP BY layer").fetchall())
            total = sum(counts.values())
        return {
            "total": total,
            "layers": {
                "L1": counts.get("L1", 0),
                "L2": counts.get("L2", 0),
                "L3": counts.get("L3", 0),
                "L4": counts.get("L4", 0),
            },
        }

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        try:
            d["metadata"] = json.loads(d["metadata"]) if d.get("metadata") else {}
        except Exception:
            d["metadata"] = {}
        return d
