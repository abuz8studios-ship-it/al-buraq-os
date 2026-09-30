"""
AL-BURAQ — Mission Graph (durable, resumable, human-approval)
=============================================================
LangGraph-lane concept (from the harvested strategy): tasks = nodes,
tool calls/outputs = edges, persisted to sqlite. Pause/resume. Approval
checkpoints before side-effectful/destructive steps.
Pure stdlib sqlite3 — ships anywhere, zero external dependencies.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Callable


class MissionGraph:
    def __init__(self, data_dir: Path):
        self.db = Path(data_dir) / "missions.sqlite"
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _c(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.db))
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._c() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS missions(
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created REAL NOT NULL,
                    updated REAL NOT NULL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS nodes(
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    needs_approval INTEGER NOT NULL,
                    payload TEXT,
                    result TEXT,
                    created REAL NOT NULL,
                    completed_at REAL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS edges(
                    id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    from_node TEXT NOT NULL,
                    to_node TEXT NOT NULL,
                    label TEXT
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_mission_nodes ON nodes(mission_id, seq)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_mission_edges ON edges(mission_id)")

    def create(self, title: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
        mid = uuid.uuid4().hex[:12]
        now = time.time()
        with self._c() as c:
            c.execute("INSERT INTO missions VALUES(?,?,?,?,?)", (mid, title or "Mission", "active", now, now))
            prev = None
            for i, s in enumerate(steps):
                nid = uuid.uuid4().hex[:12]
                needs = 1 if s.get("needs_approval") else 0
                payload_str = json.dumps(s.get("payload", {}), ensure_ascii=False)
                c.execute(
                    """
                    INSERT INTO nodes (id, mission_id, seq, kind, title, status, needs_approval, payload, result, created, completed_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (nid, mid, i, s.get("kind", "task"), s.get("title", f"Step {i+1}"), "pending", needs, payload_str, None, now, None),
                )
                if prev:
                    c.execute(
                        "INSERT INTO edges VALUES(?,?,?,?,?)",
                        (uuid.uuid4().hex[:12], mid, prev, nid, s.get("edge_label", "next")),
                    )
                prev = nid
        res = self.get(mid)
        assert res is not None
        return res

    def get(self, mid: str) -> dict[str, Any] | None:
        with self._c() as c:
            m = c.execute("SELECT * FROM missions WHERE id=?", (mid,)).fetchone()
            if not m:
                return None
            nodes = [self._node_dict(r) for r in c.execute("SELECT * FROM nodes WHERE mission_id=? ORDER BY seq", (mid,))]
            edges = [dict(r) for r in c.execute("SELECT * FROM edges WHERE mission_id=?", (mid,))]
        return {"mission": dict(m), "nodes": nodes, "edges": edges}

    def list(self) -> list[dict[str, Any]]:
        with self._c() as c:
            missions = [dict(r) for r in c.execute("SELECT * FROM missions ORDER BY updated DESC")]
            for m in missions:
                mid = m["id"]
                n_count = c.execute("SELECT COUNT(*) as cnt FROM nodes WHERE mission_id=?", (mid,)).fetchone()["cnt"]
                done_count = c.execute("SELECT COUNT(*) as cnt FROM nodes WHERE mission_id=? AND status='done'", (mid,)).fetchone()["cnt"]
                m["total_nodes"] = n_count
                m["completed_nodes"] = done_count
            return missions

    def advance(self, mid: str, executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
        """Run the next pending node. Stops at an unapproved approval gate (pause)."""
        now = time.time()
        with self._c() as c:
            n = c.execute(
                "SELECT * FROM nodes WHERE mission_id=? AND status IN ('pending', 'awaiting_approval') ORDER BY seq LIMIT 1",
                (mid,),
            ).fetchone()

            if not n:
                c.execute("UPDATE missions SET status='complete', updated=? WHERE id=?", (now, mid))
                return {"done": True, "paused": False, "mission_id": mid, "status": "complete"}

            node = self._node_dict(n)
            if node["needs_approval"] and node["status"] != "approved":
                c.execute("UPDATE nodes SET status='awaiting_approval' WHERE id=?", (node["id"],))
                c.execute("UPDATE missions SET status='paused', updated=? WHERE id=?", (now, mid))
                node["status"] = "awaiting_approval"
                return {"done": False, "paused": True, "node": node, "needs_approval": True}

            # Execute action if an executor is provided and payload has action
            result = None
            if executor and node.get("payload"):
                try:
                    result = executor(node["payload"])
                except Exception as e:
                    result = {"error": str(e)}

            result_str = json.dumps(result, ensure_ascii=False) if result is not None else None
            c.execute(
                "UPDATE nodes SET status='done', result=?, completed_at=? WHERE id=?",
                (result_str, now, node["id"]),
            )

            # Check if remaining nodes exist
            remaining = c.execute(
                "SELECT COUNT(*) as cnt FROM nodes WHERE mission_id=? AND status NOT IN ('done')",
                (mid,),
            ).fetchone()["cnt"]

            new_mission_status = "complete" if remaining == 0 else "active"
            c.execute("UPDATE missions SET status=?, updated=? WHERE id=?", (new_mission_status, now, mid))

            node["status"] = "done"
            node["result"] = result
            node["completed_at"] = now
            return {"done": remaining == 0, "paused": False, "node": node, "mission_status": new_mission_status}

    def approve(self, mid: str, node_id: str | None = None) -> dict[str, Any]:
        now = time.time()
        with self._c() as c:
            if node_id:
                c.execute(
                    "UPDATE nodes SET status='done', completed_at=? WHERE id=? AND mission_id=?",
                    (now, node_id, mid),
                )
            else:
                # Approve first awaiting_approval node
                n = c.execute(
                    "SELECT id FROM nodes WHERE mission_id=? AND status='awaiting_approval' ORDER BY seq LIMIT 1",
                    (mid,),
                ).fetchone()
                if n:
                    node_id = n["id"]
                    c.execute(
                        "UPDATE nodes SET status='done', completed_at=? WHERE id=?",
                        (now, node_id),
                    )

            c.execute("UPDATE missions SET status='active', updated=? WHERE id=?", (now, mid))

        return {"ok": True, "approved": node_id, "mission_id": mid}

    def reset(self, mid: str) -> dict[str, Any]:
        now = time.time()
        with self._c() as c:
            c.execute("UPDATE nodes SET status='pending', result=NULL, completed_at=NULL WHERE mission_id=?", (mid,))
            c.execute("UPDATE missions SET status='active', updated=? WHERE id=?", (now, mid))
        res = self.get(mid)
        return {"ok": True, "mission": res}

    def delete(self, mid: str) -> dict[str, Any]:
        with self._c() as c:
            c.execute("DELETE FROM edges WHERE mission_id=?", (mid,))
            c.execute("DELETE FROM nodes WHERE mission_id=?", (mid,))
            c.execute("DELETE FROM missions WHERE id=?", (mid,))
        return {"ok": True, "deleted": mid}

    def export_trace(self, mid: str) -> dict[str, Any] | None:
        """Export full run trace for audit and skill cards (OpenAI SDK pattern)."""
        m = self.get(mid)
        if not m:
            return None
        return {
            "mission_id": mid,
            "title": m["mission"]["title"],
            "status": m["mission"]["status"],
            "created_at": m["mission"]["created"],
            "updated_at": m["mission"]["updated"],
            "steps_total": len(m["nodes"]),
            "steps_completed": sum(1 for n in m["nodes"] if n["status"] == "done"),
            "trace": m["nodes"],
            "topology": m["edges"],
        }

    def _node_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        try:
            d["payload"] = json.loads(d["payload"]) if d.get("payload") else {}
        except Exception:
            d["payload"] = {}
        try:
            d["result"] = json.loads(d["result"]) if d.get("result") else None
        except Exception:
            pass
        return d
