"""
AL-BURAQ — Self-Upgrade & LoRA Loop Tests
=========================================
Tests rolling success calculation, regression detection, saturation detection,
receipt generation, and audit logging.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from self_upgrade import SelfUpgradeLoop


def test_self_upgrade_insufficient_signal(tmp_path):
    loop = SelfUpgradeLoop(tmp_path)

    # 0 turns -> insufficient signal
    res = loop.run_once()
    assert res["fired"] is False
    assert "insufficient_signal" in res["reason"]


def test_self_upgrade_regression_trigger(tmp_path):
    loop = SelfUpgradeLoop(tmp_path)

    # Set baseline success = 0.95
    base_file = tmp_path / "baseline.json"
    base_file.write_text(json.dumps({
        "success": 0.95,
        "n_turns": 10,
        "last_trigger_ts": datetime.now(timezone.utc).isoformat(),
    }))

    # Write 6 turns with low success (e.g. 50% success -> 0.500)
    signal_file = tmp_path / "logs" / "signal.jsonl"
    signals = [
        {"kind": "turn", "ok": True},
        {"kind": "turn", "ok": True},
        {"kind": "turn", "ok": True},
        {"kind": "turn", "ok": False, "error": "timeout"},
        {"kind": "turn", "ok": False, "error": "tool_fail"},
        {"kind": "turn", "ok": False, "error": "brain_err"},
    ]
    with open(signal_file, "w", encoding="utf-8") as f:
        for s in signals:
            f.write(json.dumps(s) + "\n")

    # Run upgrade cycle -> Regression detected!
    res = loop.run_once()
    assert res["fired"] is True
    assert "regression" in res["reason"]
    assert res["receipt"] is not None
    assert Path(res["receipt"]).exists()

    # Verify receipt contents
    receipt_data = json.loads(Path(res["receipt"]).read_text())
    assert receipt_data["mode"] == "propose_only"
    assert "LoRA finetune" in receipt_data["would_train"]
    assert receipt_data["cost_usd_cap"] == 0.0


def test_self_upgrade_saturation_trigger(tmp_path):
    loop = SelfUpgradeLoop(tmp_path)

    # Set stale baseline from 10 days ago
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    base_file = tmp_path / "baseline.json"
    base_file.write_text(json.dumps({
        "success": 0.90,
        "n_turns": 10,
        "last_trigger_ts": stale_ts,
    }))

    # Write 6 healthy turns (success = 1.0)
    signal_file = tmp_path / "logs" / "signal.jsonl"
    signals = [{"kind": "turn", "ok": True} for _ in range(6)]
    with open(signal_file, "w", encoding="utf-8") as f:
        for s in signals:
            f.write(json.dumps(s) + "\n")

    # Run upgrade cycle -> Saturation detected!
    res = loop.run_once()
    assert res["fired"] is True
    assert "saturation" in res["reason"]
    assert res["receipt"] is not None
