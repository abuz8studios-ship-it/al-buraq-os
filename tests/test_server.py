"""
AL-BURAQ — Backend API Test Suite
=================================
Tests all FastAPI endpoints, request validations, responses, error handling,
and static delivery.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import server
from server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SIGNAL_PATH", tmp_path / "data" / "logs" / "signal.jsonl")
    (tmp_path / "data" / "logs").mkdir(parents=True, exist_ok=True)
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "Al-Buraq" in data["app"]
    assert "version" in data


def test_device_probe(client):
    r = client.get("/api/device/probe")
    assert r.status_code == 200
    data = r.json()
    assert "os" in data
    assert "cpu_count" in data
    assert "disk_free_gb" in data


def test_boot_report(client):
    r = client.get("/api/boot/report")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "memory_stats" in data
    assert "skills" in data
    assert "honesty_gates" in data
    assert data["honesty_gates"]["launcher_clean_folder"] is True


def test_brain_status_and_shelf(client):
    r = client.get("/api/brain/status")
    assert r.status_code == 200
    data = r.json()
    assert "alive" in data
    assert "port" in data

    r2 = client.get("/api/brains/list")
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["shelf"]) >= 3
    assert any(b["id"] == "spark" for b in data2["shelf"])


def test_brain_router_config_and_switch(client):
    r = client.get("/api/brains/config")
    assert r.status_code == 200
    cfg = r.json()
    assert "providers" in cfg

    # Switch active
    r_sw = client.post("/api/brains/switch", json={"provider": "local"})
    assert r_sw.status_code == 200
    assert r_sw.json()["active"] == "local"

    # Set key
    r_key = client.post("/api/brains/key", json={"provider": "openai", "key": "sk-test-key-12345"})
    assert r_key.status_code == 200
    assert r_key.json()["ok"] is True

    # Probe local
    r_pr = client.get("/api/brains/probe/local")
    assert r_pr.status_code == 200


def test_inbox_send_and_agent_run(client):
    # Test unified inbox endpoint (used by UI)
    r = client.post("/api/inbox/send", json={"content": "What time is it?", "session_id": "test_s1"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert len(data["reply"]) > 0

    # Test direct agent endpoint
    r2 = client.post("/api/agent/run", json={"content": "Calculate 40 + 2", "session_id": "test_s2"})
    assert r2.status_code == 200
    assert r2.json()["ok"] is True

    # Verify signal logging
    r_sig = client.get("/api/signal/tail?limit=10")
    assert r_sig.status_code == 200
    signals = r_sig.json()["signals"]
    assert len(signals) >= 2


def test_memory_crud_endpoints(client):
    # Store
    r_store = client.post(
        "/api/memory/store",
        json={"key": "user_pref", "content": "Prefers concise responses", "layer": "L3", "title": "Preferences"},
    )
    assert r_store.status_code == 200
    mem_id = r_store.json()["memory"]["id"]

    # Layer list
    r_layer = client.get("/api/memory/layer/L3")
    assert r_layer.status_code == 200
    assert r_layer.json()["count"] >= 1

    # Search
    r_search = client.get("/api/memory/search?q=concise")
    assert r_search.status_code == 200
    assert r_search.json()["count"] >= 1

    # Stats
    r_stats = client.get("/api/memory/stats")
    assert r_stats.status_code == 200
    assert r_stats.json()["total"] >= 1

    # Delete
    r_del = client.delete(f"/api/memory/{mem_id}")
    assert r_del.status_code == 200
    assert r_del.json()["ok"] is True


def test_mission_graph_endpoints(client):
    # Create
    steps = [
        {"title": "Initial Probe", "kind": "task", "payload": {"tool": "now", "args": {}}},
        {"title": "Approval Gate", "kind": "approval", "needs_approval": True},
        {"title": "Final Execution", "kind": "task", "payload": {"tool": "echo", "args": {"text": "done"}}},
    ]
    r_create = client.post("/api/mission/create", json={"title": "Test Mission 1", "steps": steps})
    assert r_create.status_code == 200
    m = r_create.json()
    mid = m["mission"]["id"]

    # List
    r_list = client.get("/api/mission/list")
    assert r_list.status_code == 200
    assert len(r_list.json()["missions"]) >= 1

    # Advance step 1
    r_adv1 = client.post(f"/api/mission/{mid}/advance")
    assert r_adv1.status_code == 200
    assert r_adv1.json()["paused"] is False

    # Advance step 2 -> pause on approval
    r_adv2 = client.post(f"/api/mission/{mid}/advance")
    assert r_adv2.status_code == 200
    assert r_adv2.json()["paused"] is True
    assert r_adv2.json()["needs_approval"] is True

    # Approve
    r_appr = client.post(f"/api/mission/{mid}/approve", json={})
    assert r_appr.status_code == 200

    # Advance step 3 -> complete
    r_adv3 = client.post(f"/api/mission/{mid}/advance")
    assert r_adv3.status_code == 200
    assert r_adv3.json()["done"] is True

    # Export trace
    r_exp = client.get(f"/api/mission/{mid}/export")
    assert r_exp.status_code == 200
    trace = r_exp.json()
    assert trace["steps_completed"] == 3

    # Reset
    r_res = client.post(f"/api/mission/{mid}/reset")
    assert r_res.status_code == 200

    # Delete
    r_del = client.delete(f"/api/mission/{mid}")
    assert r_del.status_code == 200


def test_connectors_endpoints(client):
    # List
    r_list = client.get("/api/connectors/list")
    assert r_list.status_code == 200

    # Add custom
    r_add = client.post("/api/connectors/add", json={"name": "CustomMCP", "command": "python", "args": ["--version"], "trust": "unverified"})
    assert r_add.status_code == 200
    assert r_add.json()["ok"] is True

    # Enable
    r_en = client.post("/api/connectors/enable", json={"name": "CustomMCP", "enabled": True})
    assert r_en.status_code == 200
    assert r_en.json()["enabled"] is True

    # Trust
    r_tr = client.post("/api/connectors/trust", json={"name": "CustomMCP", "trust": "verified"})
    assert r_tr.status_code == 200

    # Test
    r_test = client.post("/api/connectors/CustomMCP/test")
    assert r_test.status_code == 200
    assert r_test.json()["ok"] is True

    # Delete
    r_del = client.delete("/api/connectors/CustomMCP")
    assert r_del.status_code == 200


def test_self_learning_and_upgrade_endpoints(client):
    # Run learning cycle
    r_learn = client.post("/api/learn/run")
    assert r_learn.status_code == 200
    assert "harvested_rows" in r_learn.json()

    # Skills list
    r_sk = client.get("/api/skills/list")
    assert r_sk.status_code == 200
    assert "proposed" in r_sk.json()
    assert "promoted" in r_sk.json()

    # Run upgrade cycle
    r_upg = client.post("/api/upgrade/run")
    assert r_upg.status_code == 200
    assert "rolling_success" in r_upg.json()

    # Status
    r_stat = client.get("/api/upgrade/status")
    assert r_stat.status_code == 200
    assert "min_new_signal" in r_stat.json()


def test_jobs_endpoint(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert len(data["jobs"]) >= 3


def test_static_and_app_routes(client):
    # Index
    r_idx = client.get("/")
    assert r_idx.status_code == 200

    # Apps
    r_sov = client.get("/apps/sovereign.html")
    assert r_sov.status_code == 200
    r_tui = client.get("/apps/tui.html")
    assert r_tui.status_code == 200
    r_mc = client.get("/apps/mission-control.html")
    assert r_mc.status_code == 200

    # Assets
    r_wall = client.get("/assets/wallpaper.png")
    assert r_wall.status_code == 200
    r_spl = client.get("/assets/splash.png")
    assert r_spl.status_code == 200
