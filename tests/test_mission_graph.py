"""
AL-BURAQ — Mission Graph, Connectors & Layered Memory Tests
===========================================================
"""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from mission_graph import MissionGraph
from connectors import ConnectorRegistry
from memory import MemoryStore


def test_mission_graph_lifecycle(tmp_path):
    mg = MissionGraph(tmp_path)

    # 1. Create Mission
    steps = [
        {"title": "Step 1: Discover", "kind": "task", "payload": {"tool": "now"}},
        {"title": "Step 2: Human Checkpoint", "kind": "approval", "needs_approval": True},
        {"title": "Step 3: Deploy", "kind": "task", "payload": {"tool": "echo"}},
    ]
    m = mg.create("Deploy Pipeline", steps)
    mid = m["mission"]["id"]
    assert len(m["nodes"]) == 3
    assert len(m["edges"]) == 2

    # 2. Advance Step 1 -> done
    adv1 = mg.advance(mid)
    assert adv1["done"] is False
    assert adv1["paused"] is False
    assert adv1["node"]["seq"] == 0

    # 3. Advance Step 2 -> pauses on approval gate
    adv2 = mg.advance(mid)
    assert adv2["paused"] is True
    assert adv2["needs_approval"] is True
    assert adv2["node"]["seq"] == 1

    # 4. Attempt advance while paused without approval
    adv_try = mg.advance(mid)
    assert adv_try["paused"] is True

    # 5. Approve checkpoint
    appr = mg.approve(mid)
    assert appr["ok"] is True

    # 6. Advance Step 3 -> complete
    adv3 = mg.advance(mid)
    assert adv3["done"] is True
    assert adv3["mission_status"] == "complete"

    # 7. Trace Export
    trace = mg.export_trace(mid)
    assert trace["steps_completed"] == 3


def test_connector_registry(tmp_path):
    cr = ConnectorRegistry(tmp_path)

    # 1. Import Claude Desktop spec
    cfg = {
        "mcpServers": {
            "github_mcp": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]},
            "filesystem_mcp": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]},
        }
    }
    imp_res = cr.import_claude_desktop(cfg)
    assert imp_res["added"] == 2

    # Verify imported disabled by default
    gh = cr.get("github_mcp")
    assert gh["enabled"] is False
    assert gh["trust"] == "unverified"

    # Enable & Trust
    cr.set_enabled("github_mcp", True)
    cr.set_trust("github_mcp", "verified")
    gh_up = cr.get("github_mcp")
    assert gh_up["enabled"] is True
    assert gh_up["trust"] == "verified"


def test_memory_layers(tmp_path):
    store = MemoryStore(tmp_path)

    # Store in each layer
    m1 = store.store(key="active_task", content="Refactoring backend", layer="L1", title="Current Work")
    m2 = store.store(key="session_notes", content="Discussed architecture", layer="L2", title="Session Notes")
    m3 = store.store(key="user_guidelines", content="Always use dark gold palette", layer="L3", title="Design Law")
    m4 = store.store(key="audit_2026", content="Completed milestone", layer="L4", title="Archive")

    assert m1["layer"] == "L1"
    assert m4["layer"] == "L4"

    # List layers
    l1_items = store.list_layer("L1")
    assert len(l1_items) == 1
    assert l1_items[0]["key"] == "active_task"

    # Search
    search_res = store.search("gold")
    assert len(search_res) == 1
    assert search_res[0]["key"] == "user_guidelines"

    # Stats
    stats = store.stats()
    assert stats["total"] == 4
    assert stats["layers"]["L1"] == 1
    assert stats["layers"]["L3"] == 1
