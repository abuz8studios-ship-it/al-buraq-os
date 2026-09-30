"""
AL-BURAQ — Agentic Loop & Tool Suite Tests
==========================================
Tests the 4-pillar THINK -> ACT -> VERIFY -> LEARN loop, tool execution,
alias resolution, guardrails, and error recovery.
"""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from agent_loop import AgentLoop, Guard, _tool_math


def test_safe_math_tool():
    # Basic math
    res1 = _tool_math({"expr": "2 + 2"})
    assert res1["result"] == 4

    res2 = _tool_math({"expr": "100 / 4 * 3 + (15 - 5)"})
    assert res2["result"] == 85.0

    # Power & Modulo
    res3 = _tool_math({"expr": "2 ** 8 % 100"})
    assert res3["result"] == 56

    # Malicious code attempt blocked
    res_bad = _tool_math({"expr": "__import__('os').system('ls')"})
    assert "error" in res_bad


def test_tool_aliases_and_execution(tmp_path):
    loop = AgentLoop(tmp_path)

    # Test alias resolution
    assert loop._resolve_tool_name("time") == "now"
    assert loop._resolve_tool_name("datetime") == "now"
    assert loop._resolve_tool_name("calc") == "math"
    assert loop._resolve_tool_name("system") == "device_info"
    assert loop._resolve_tool_name("remember") == "memory_store"
    assert loop._resolve_tool_name("recall") == "memory_recall"

    # Test ACT pillar with aliases
    guard = Guard()
    act_res = loop._act("Let me check the time {{tool: time}} and calculate {{tool: calc | {\"expr\": \"12 * 12\"}}}", guard)
    assert len(act_res) == 2
    assert act_res[0]["tool"] == "now"
    assert "now" in act_res[0]["result"]
    assert act_res[1]["tool"] == "math"
    assert act_res[1]["result"]["result"] == 144


def test_loop_guardrails(tmp_path):
    loop = AgentLoop(tmp_path)
    guard = Guard()

    # Trigger same tool call twice
    text = "{{tool: echo | {\"text\": \"dup\"}}}"
    r1 = loop._act(text, guard)
    assert "error" not in r1[0]

    r2 = loop._act(text, guard)
    assert "error" not in r2[0]

    # 3rd identical call should be blocked by guardrail
    r3 = loop._act(text, guard)
    assert r3[0].get("error") == "duplicate_call_blocked"


def test_full_agent_turn_sovereign_offline(tmp_path):
    loop = AgentLoop(tmp_path)

    # Run agent query in offline mode
    res = loop.run("What time is it right now?", session_id="test_session_1")
    assert res["ok"] is True
    assert res["steps"] >= 1
    assert "trace" in res

    # Verify signal logging occurred
    signal_file = tmp_path / "logs" / "signal.jsonl"
    assert signal_file.exists()
    lines = [json.loads(ln) for ln in signal_file.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0]["ok"] is True
    assert lines[0]["session"] == "test_session_1"


def test_file_tools_sandboxing(tmp_path):
    loop = AgentLoop(tmp_path)

    # Create safe test file inside data dir
    safe_file = tmp_path / "test_doc.txt"
    safe_file.write_text("Sovereign Agent Content", encoding="utf-8")

    # Read inside data dir
    guard = Guard()
    res_ok = loop._act("{{tool: read_file | {\"path\": \"test_doc.txt\"}}}", guard)
    assert "content" in res_ok[0]["result"]
    assert "Sovereign Agent" in res_ok[0]["result"]["content"]

    # Traversal attempt blocked
    res_bad = loop._act("{{tool: read_file | {\"path\": \"../../etc/passwd\"}}}", guard)
    assert "error" in res_bad[0]["result"]
