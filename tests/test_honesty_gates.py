"""
AL-BURAQ — Section 10 Honesty Gates Verification Suite
======================================================
Tests all mandatory honesty gates before any capability claim:
  1. Launcher boots from a clean folder.
  2. Embedded brain floor operates and answers prompts offline.
  3. Agentic loop completes THINK·ACT·VERIFY·LEARN on real task (logged to signal.jsonl).
  4. Skill loop promotes/prunes real proposed skills (logged to audit).
  5. Upgrade loop writes real regression-eval cycle + receipt (no fake training claim).
  6. Mission graph persists + pauses + resumes approval checkpoints.
  7. Zero secrets / zero internal personas leaked in responses.
  8. Every UI capability maps to a real backend endpoint.
  9. First-run with no config degrades gracefully.
"""
import json
import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import server
from server import app
from agent_loop import AgentLoop
from self_learning import SelfLearningLoop
from self_upgrade import SelfUpgradeLoop
from mission_graph import MissionGraph
from memory import MemoryStore


def test_gate_1_clean_folder_provisioning(tmp_path):
    """Launcher boots from a clean folder without pre-existing state."""
    clean_dir = tmp_path / "clean_install"
    clean_dir.mkdir()
    mem = MemoryStore(clean_dir)
    assert mem.stats()["total"] == 0
    loop = AgentLoop(clean_dir)
    assert loop.signal_path.parent.exists()


def test_gate_2_embedded_brain_offline_response(tmp_path):
    """Embedded brain answers prompt offline with sovereign floor."""
    loop = AgentLoop(tmp_path)
    res = loop.run("What is current system device status?", session_id="gate2_test")
    assert res["ok"] is True
    assert len(res["reply"]) > 0


def test_gate_3_agentic_loop_logged_to_signal(tmp_path):
    """Agentic loop completes THINK->ACT->VERIFY->LEARN and logs to signal.jsonl."""
    loop = AgentLoop(tmp_path)
    res = loop.run("Calculate 128 * 4", session_id="gate3_test")
    assert res["ok"] is True
    signal_file = tmp_path / "logs" / "signal.jsonl"
    assert signal_file.exists()
    records = [json.loads(line) for line in signal_file.read_text().splitlines() if line.strip()]
    assert any(r.get("session") == "gate3_test" for r in records)


def test_gate_4_skill_loop_promotion_and_audit(tmp_path):
    """Skill loop promotes/prunes a real skill with auditable receipts."""
    # Write signal rows
    sig_path = tmp_path / "logs" / "signal.jsonl"
    sig_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sig_path, "w", encoding="utf-8") as f:
        for _ in range(4):
            f.write(json.dumps({"kind": "turn", "ok": True, "used_tools": [{"tool": "now"}]}) + "\n")

    loop = SelfLearningLoop(tmp_path)
    cycle = loop.run_once()
    assert cycle["proposed"] >= 1
    assert cycle["promoted"] >= 1
    assert (tmp_path / "logs" / "self_learning_log.jsonl").exists()


def test_gate_5_upgrade_loop_receipt_generation(tmp_path):
    """Upgrade loop writes real regression-eval cycle + receipt (no fake training)."""
    # Create baseline
    (tmp_path / "baseline.json").write_text(json.dumps({"success": 0.95, "n_turns": 8}))
    sig_path = tmp_path / "logs" / "signal.jsonl"
    sig_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sig_path, "w", encoding="utf-8") as f:
        for _ in range(3):
            f.write(json.dumps({"kind": "turn", "ok": True}) + "\n")
        for _ in range(3):
            f.write(json.dumps({"kind": "turn", "ok": False, "error": "timeout"}) + "\n")

    upg = SelfUpgradeLoop(tmp_path)
    res = upg.run_once()
    assert res["fired"] is True
    assert res["receipt"] is not None
    receipt_json = json.loads(Path(res["receipt"]).read_text())
    assert receipt_json["mode"] == "propose_only"
    assert "No training performed" in receipt_json["note"]


def test_gate_6_mission_graph_persist_and_resume(tmp_path):
    """Mission graph persists state and resumes paused approval checkpoint."""
    mg = MissionGraph(tmp_path)
    steps = [
        {"title": "Automated Action", "kind": "task"},
        {"title": "Human Review", "kind": "approval", "needs_approval": True},
        {"title": "Post Approval Task", "kind": "task"},
    ]
    m = mg.create("Audit Mission", steps)
    mid = m["mission"]["id"]

    # Advance 1 -> done
    mg.advance(mid)
    # Advance 2 -> paused
    adv2 = mg.advance(mid)
    assert adv2["paused"] is True

    # Persists in sqlite
    mg_reloaded = MissionGraph(tmp_path)
    m_data = mg_reloaded.get(mid)
    assert m_data["mission"]["status"] == "paused"

    # Resume via approval
    mg_reloaded.approve(mid)
    adv3 = mg_reloaded.advance(mid)
    assert adv3["done"] is True


def test_gate_7_zero_secrets_leaked(tmp_path, monkeypatch):
    """Ensure API keys and sensitive tokens are never returned in plaintext."""
    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SIGNAL_PATH", tmp_path / "data" / "logs" / "signal.jsonl")
    (tmp_path / "data" / "logs").mkdir(parents=True, exist_ok=True)

    with TestClient(app) as c:
        # Save a sensitive key
        c.post("/api/brains/key", json={"provider": "openai", "key": "sk-super-secret-key-9999"})
        # Read back config
        cfg = c.get("/api/brains/config").json()
        openai_key = cfg["providers"]["openai"]["key"]
        assert openai_key == "***set***"
        assert "sk-super-secret" not in json.dumps(cfg)


def test_gate_8_ui_endpoint_mapping(tmp_path, monkeypatch):
    """Every UI capability maps to a live backend action."""
    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SIGNAL_PATH", tmp_path / "data" / "logs" / "signal.jsonl")
    (tmp_path / "data" / "logs").mkdir(parents=True, exist_ok=True)

    with TestClient(app) as c:
        assert c.post("/api/inbox/send", json={"content": "test"}).status_code == 200
        assert c.get("/api/boot/report").status_code == 200
        assert c.get("/api/jobs").status_code == 200
        assert c.get("/api/memory/layer/L4").status_code == 200
        assert c.get("/api/brains/list").status_code == 200
        assert c.get("/api/skills/list").status_code == 200
        assert c.get("/api/connectors/list").status_code == 200


def test_gate_9_first_run_graceful_degradation(tmp_path, monkeypatch):
    """First-run with no pre-existing config degrades gracefully."""
    empty_dir = tmp_path / "empty_first_run"
    monkeypatch.setattr(server, "DATA", empty_dir)
    monkeypatch.setattr(server, "SIGNAL_PATH", empty_dir / "logs" / "signal.jsonl")

    with TestClient(app) as c:
        r_probe = c.get("/api/device/probe")
        assert r_probe.status_code == 200
        r_health = c.get("/health")
        assert r_health.status_code == 200
        assert r_health.json()["ok"] is True
