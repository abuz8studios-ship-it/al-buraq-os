"""
AL-BURAQ — Probe-Verified Regression Suite (2026-10-01 audit)
=============================================================
Every test here is a receipt: it encodes a defect that was PROBED live or in
code during the 2026-10-01 audit, then fixed. If one of these goes red, a
previously-cured defect has regressed.

Covered defects (probe numbers refer to REPORT.md §3):
  P2  nested JSON tool args parsed as {} by the ACT regex
  P3  quotes in user text corrupted offline tool directives (query lost)
  P3b bare-arithmetic trigger missed "128 * 4" style input; substring "time"
      over-triggered on words like "timeline"
  P4  approval-gated mission nodes with payloads never executed after approval
  P5  /api/jobs reported wrong last_run and re-harvested the whole signal file
  P6  /api/boot/report hardcoded every honesty gate True on an EMPTY data dir
  P7  unbounded full-file reads (signal tail, harvest, upgrade rows)
  P8  LEARNED.md injected stale head instead of fresh tail; grew unbounded
"""
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import server
from server import app
from agent_loop import AgentLoop, Guard, _extract_tool_directives, _directive
from jsonl_io import tail_jsonl, tail_lines
from mission_graph import MissionGraph
from self_learning import SelfLearningLoop
from self_upgrade import SelfUpgradeLoop


# ── P2: nested JSON tool args survive ACT parsing ─────────────────────────────
def test_nested_json_tool_args_parse(tmp_path):
    loop = AgentLoop(tmp_path)
    guard = Guard()
    txt = '{{tool: memory_store | {"key": "k1", "content": "v", "metadata": {"nested": {"deep": 1}}}}}'
    res = loop._act(txt, guard)
    assert len(res) == 1
    assert res[0]["result"].get("ok") is True, f"nested args must execute, got {res[0]}"
    # stored entry must exist with content intact
    from memory import MemoryStore
    item = MemoryStore(tmp_path).get_by_key("k1", layer="L3")
    assert item is not None and item["content"] == "v"


def test_directive_scanner_shapes():
    # argless, flat, nested, braces-in-strings, multiple per text
    txt = (
        "a {{tool: now}} b "
        '{{tool: echo | {"text": "hi"}}} c '
        '{{tool: memory_store | {"key": "k", "content": "v", "metadata": {"a": {"b": [1,2]}}}}} d '
        '{{tool: echo | {"text": "brace } in string"}}}'
    )
    found = _extract_tool_directives(txt)
    names = [n for n, _ in found]
    assert names == ["now", "echo", "memory_store", "echo"]
    nested = json.loads(found[2][1])
    assert nested["metadata"]["a"]["b"] == [1, 2]
    braced = json.loads(found[3][1])
    assert braced["text"] == "brace } in string"


# ── P3: quotes/backslashes in user text cannot corrupt directives ─────────────
def test_quoted_user_text_reaches_builders_book_tool(tmp_path):
    loop = AgentLoop(tmp_path)
    msg = 'what does the builders book say about "probes" and \'receipts\'?'
    res = loop.run(msg, session_id="p3_quotes")
    assert res["ok"] is True
    assert res["tools_called"] >= 1
    # the tool must have received the real query — not an empty {} fallback
    tool_entries = [t for tr in res["trace"] for t in tr.get("tools", [])]
    bb = [t for t in tool_entries if t["tool"] == "builders_book_query"]
    assert bb and bb[0].get("args", {}).get("query") == msg
    # chapter search on the quoted query still returns matches
    assert "Builders Book matches" in res["reply"] or "Chapter" in res["reply"]


def test_directive_builder_escapes_safely():
    evil = 'he said "hi" \\ then\nnewline'
    d = _directive("memory_recall", {"query": evil})
    parsed = _extract_tool_directives(d)
    assert parsed[0][0] == "memory_recall"
    assert json.loads(parsed[0][1])["query"] == evil


def test_math_trigger_without_keyword_and_no_false_time(tmp_path):
    loop2 = AgentLoop(tmp_path)
    out = loop2._offline_reason([{"role": "user", "content": "what is 128 * 4"}])
    assert out["text"].startswith("{{tool: math"), out["text"]
    # word-boundary: "timeline" must not trigger the clock tool
    out2 = loop2._offline_reason([{"role": "user", "content": "show me the project timeline status"}])
    assert out2["text"] != "{{tool: now}}"


# ── P4: approval gates execute their payload after approval ───────────────────
def test_approved_gate_executes_payload(tmp_path):
    mg = MissionGraph(tmp_path)
    m = mg.create("gate exec", [
        {"title": "Gated side effect", "kind": "approval", "needs_approval": True,
         "payload": {"tool": "echo", "args": {"text": "SIDE_EFFECT_RAN"}}},
    ])
    mid = m["mission"]["id"]
    adv1 = mg.advance(mid, executor=lambda p: {"ran": p.get("args", {}).get("text")})
    assert adv1["paused"] is True

    mg.approve(mid)
    # node is 'approved', not silently 'done'
    node = mg.get(mid)["nodes"][0]
    assert node["status"] == "approved"

    adv2 = mg.advance(mid, executor=lambda p: {"ran": p.get("args", {}).get("text")})
    assert adv2["done"] is True
    assert adv2["node"]["result"] == {"ran": "SIDE_EFFECT_RAN"}


def test_payloadless_approval_gate_still_completes(tmp_path):
    """Existing contract preserved: a pure checkpoint (no payload) is done on approve."""
    mg = MissionGraph(tmp_path)
    m = mg.create("checkpoint", [
        {"title": "task", "kind": "task", "payload": {"tool": "now"}},
        {"title": "checkpoint", "kind": "approval", "needs_approval": True},
        {"title": "after", "kind": "task", "payload": {"tool": "echo"}},
    ])
    mid = m["mission"]["id"]
    mg.advance(mid)
    assert mg.advance(mid)["paused"] is True
    mg.approve(mid)
    adv = mg.advance(mid)
    assert adv["done"] is True
    assert mg.export_trace(mid)["steps_completed"] == 3


# ── P5: /api/jobs semantics ────────────────────────────────────────────────────
def test_jobs_last_run_reflects_real_learn_cycle(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SIGNAL_PATH", tmp_path / "data" / "logs" / "signal.jsonl")
    (tmp_path / "data" / "logs").mkdir(parents=True, exist_ok=True)

    with TestClient(app) as c:
        j0 = c.get("/api/jobs").json()
        learn_job = [x for x in j0["jobs"] if x["id"] == "job_self_learning"][0]
        assert learn_job["last_run"] is None  # no cycle has run yet

        r = c.post("/api/learn/run")
        assert r.status_code == 200
        j1 = c.get("/api/jobs").json()
        learn_job = [x for x in j1["jobs"] if x["id"] == "job_self_learning"][0]
        assert learn_job["last_run"] is not None  # real cycle ts from audit log


# ── P6: boot report honesty gates are COMPUTED, never hardcoded ───────────────
def test_boot_report_gates_honest_on_fresh_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SIGNAL_PATH", tmp_path / "data" / "logs" / "signal.jsonl")
    (tmp_path / "data" / "logs").mkdir(parents=True, exist_ok=True)

    with TestClient(app) as c:
        b = c.get("/api/boot/report").json()
        gates = b["honesty_gates"]
        ev = b["honesty_evidence"]
        # fresh dir, zero agent turns -> agentic core NOT yet verified (honest)
        assert gates["agentic_core_verified"] is False
        # structural gates remain true (enforced in code + proven by test suite)
        assert gates["launcher_clean_folder"] is True
        assert gates["zero_secrets_leaked"] is True
        assert "structural" in ev["launcher_clean_folder"]
        # no engine on CI -> embedded brain floor honestly False, floor explained
        assert gates["embedded_brain_floor"] is False
        assert "sovereign deterministic floor" in ev["embedded_brain_floor"]
        assert b["honesty_all_green"] is False

        # now generate real receipts and watch the gates flip green
        r = c.post("/api/inbox/send", json={"content": "What time is it?", "session_id": "p6"})
        assert r.status_code == 200
        c.post("/api/learn/run")
        c.post("/api/upgrade/run")
        c.post("/api/mission/create", json={"title": "p6", "steps": [{"title": "s"}]})

        b2 = c.get("/api/boot/report").json()
        g2 = b2["honesty_gates"]
        assert g2["agentic_core_verified"] is True
        assert g2["skill_loop_verified"] is True
        assert g2["upgrade_loop_verified"] is True
        assert g2["mission_graph_verified"] is True
        assert g2["builders_book_ingrained"] is True  # lifespan ingested 11 chapters
        assert b2["builders_book"]["status"] == "ingrained"


# ── P7: bounded reads ──────────────────────────────────────────────────────────
def test_tail_jsonl_is_bounded_and_ordered(tmp_path):
    p = tmp_path / "big.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for i in range(50000):
            f.write(json.dumps({"i": i}) + "\n")
    rows = tail_jsonl(p, 10)
    assert len(rows) == 10
    assert rows[0]["i"] == 49990 and rows[-1]["i"] == 49999


def test_signal_tail_endpoint_on_large_file(tmp_path, monkeypatch):
    sig = tmp_path / "data" / "logs" / "signal.jsonl"
    sig.parent.mkdir(parents=True, exist_ok=True)
    with open(sig, "w", encoding="utf-8") as f:
        for i in range(60000):
            f.write(json.dumps({"kind": "turn", "i": i, "pad": "x" * 40}) + "\n")
    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SIGNAL_PATH", sig)

    with TestClient(app) as c:
        t0 = time.time()
        r = c.get("/api/signal/tail?limit=20")
        dt = time.time() - t0
        assert r.status_code == 200
        body = r.json()
        assert len(body["signals"]) == 20
        assert body["signals"][-1]["i"] == 59999
        assert body["total_count_is_exact"] is False  # large file: honest lower-bound mode
        assert dt < 2.0, f"tail read must stay bounded, took {dt:.2f}s"


def test_harvest_bounded():
    loop = SelfLearningLoop.__new__(SelfLearningLoop)
    import tempfile
    d = Path(tempfile.mkdtemp())
    loop2 = SelfLearningLoop(d)
    sig = d / "logs" / "signal.jsonl"
    with open(sig, "w", encoding="utf-8") as f:
        for i in range(7000):
            f.write(json.dumps({"kind": "turn", "ok": True, "i": i}) + "\n")
    rows = loop2.harvest()
    assert len(rows) == 5000  # MAX_HARVEST_ROWS cap
    assert rows[-1]["i"] == 6999  # tail = most recent


# ── P8: LEARNED.md freshness + rotation ────────────────────────────────────────
def test_learned_md_injects_tail_and_rotates(tmp_path):
    loop = AgentLoop(tmp_path)
    learned = tmp_path / "LEARNED.md"
    # > 2000 chars of history so the stale head falls outside the tail window
    learned.write_text("OLD-STALE-ENTRY\n" + ("filler line with some length to it\n" * 200) + "\nFRESH-CORRECTION-LAST\n", encoding="utf-8")
    ctx = loop._get_learned_context()
    assert "FRESH-CORRECTION-LAST" in ctx
    assert "OLD-STALE-ENTRY" not in ctx

    # rotation: oversized file collapses to the newest 300 entries
    learned.write_text("".join(f"- entry {i}\n" for i in range(6000)), encoding="utf-8")
    loop._learn({"kind": "turn", "user": "rotate me", "ok": True, "session": "rot",
                 "reply_len": 1, "provider": "test", "duration_s": 0.01})
    after = learned.read_text(encoding="utf-8")
    assert after.count("\n") < 400
    assert "rotate me" in after
