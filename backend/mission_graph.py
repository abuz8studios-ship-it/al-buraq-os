"""
AL-BURAQ — Mission Graph (durable, resumable, human-approval)
=============================================================
LangGraph-lane concept (from the harvested strategy): tasks = nodes,
tool calls/outputs = edges, persisted to sqlite. Pause/resume. Approval
checkpoints before side-effectful/destructive steps.
Pure stdlib sqlite3 — ships anywhere.
"""
from __future__ import annotations
import json, sqlite3, time, uuid
from pathlib import Path

class MissionGraph:
    def __init__(self, data_dir: Path):
        self.db = Path(data_dir) / "missions.sqlite"
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _c(self):
        c = sqlite3.connect(str(self.db)); c.row_factory = sqlite3.Row; return c

    def _init(self):
        with self._c() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS missions(
                id TEXT PRIMARY KEY, title TEXT, status TEXT, created REAL, updated REAL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS nodes(
                id TEXT PRIMARY KEY, mission_id TEXT, seq INTEGER, kind TEXT,
                title TEXT, status TEXT, needs_approval INTEGER, payload TEXT, created REAL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS edges(
                id TEXT PRIMARY KEY, mission_id TEXT, from_node TEXT, to_node TEXT, label TEXT)""")

    def create(self, title, steps):
        mid = uuid.uuid4().hex[:12]; now = time.time()
        with self._c() as c:
            c.execute("INSERT INTO missions VALUES(?,?,?,?,?)", (mid, title, "active", now, now))
            prev = None
            for i, s in enumerate(steps):
                nid = uuid.uuid4().hex[:12]
                needs = 1 if s.get("needs_approval") else 0
                c.execute("INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?)",
                          (nid, mid, i, s.get("kind","task"), s.get("title",""),
                           "pending", needs, json.dumps(s.get("payload",{})), now))
                if prev:
                    c.execute("INSERT INTO edges VALUES(?,?,?,?,?)",
                              (uuid.uuid4().hex[:12], mid, prev, nid, "next"))
                prev = nid
        return self.get(mid)

    def get(self, mid):
        with self._c() as c:
            m = c.execute("SELECT * FROM missions WHERE id=?", (mid,)).fetchone()
            if not m: return None
            nodes = [dict(r) for r in c.execute("SELECT * FROM nodes WHERE mission_id=? ORDER BY seq",(mid,))]
            edges = [dict(r) for r in c.execute("SELECT * FROM edges WHERE mission_id=?",(mid,))]
        return {"mission": dict(m), "nodes": nodes, "edges": edges}

    def list(self):
        with self._c() as c:
            return [dict(r) for r in c.execute("SELECT * FROM missions ORDER BY updated DESC")]

    def advance(self, mid):
        """Run the next pending node. Stops at an unapproved approval gate (pause)."""
        with self._c() as c:
            n = c.execute("SELECT * FROM nodes WHERE mission_id=? AND status='pending' ORDER BY seq LIMIT 1",(mid,)).fetchone()
            if not n:
                c.execute("UPDATE missions SET status='complete', updated=? WHERE id=?",(time.time(),mid))
                return {"done": True, "paused": False}
            n = dict(n)
            if n["needs_approval"]:
                c.execute("UPDATE nodes SET status='awaiting_approval' WHERE id=?",(n["id"],))
                c.execute("UPDATE missions SET status='paused', updated=? WHERE id=?",(time.time(),mid))
                return {"done": False, "paused": True, "node": n, "needs_approval": True}
            c.execute("UPDATE nodes SET status='done' WHERE id=?",(n["id"],))
            c.execute("UPDATE missions SET updated=? WHERE id=?",(time.time(),mid))
            return {"done": False, "paused": False, "node": n}

    def approve(self, mid, node_id):
        with self._c() as c:
            c.execute("UPDATE nodes SET status='done' WHERE id=? AND mission_id=?",(node_id,mid))
            c.execute("UPDATE missions SET status='active', updated=? WHERE id=?",(time.time(),mid))
        return {"approved": node_id}
