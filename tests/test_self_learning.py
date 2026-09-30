"""
AL-BURAQ — Self-Learning & Skill Loop Tests
===========================================
Tests HARVEST -> PROPOSE -> INGEST -> EVALUATE -> PROMOTE/PRUNE cycle,
quality scoring, manual promotion/pruning, and audit logging.
"""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from self_learning import SelfLearningLoop


def test_self_learning_full_cycle(tmp_path):
    loop = SelfLearningLoop(tmp_path)

    # 1. Populate signal with repeated tool usage
    signal_file = tmp_path / "logs" / "signal.jsonl"
    signals = [
        {"kind": "turn", "ok": True, "used_tools": [{"tool": "now"}]},
        {"kind": "turn", "ok": True, "used_tools": [{"tool": "now"}]},
        {"kind": "turn", "ok": True, "used_tools": [{"tool": "now"}]},
        {"kind": "turn", "ok": True, "used_tools": [{"tool": "device_info"}]},
        {"kind": "turn", "ok": True, "used_tools": [{"tool": "device_info"}]},
    ]
    with open(signal_file, "w", encoding="utf-8") as f:
        for s in signals:
            f.write(json.dumps(s) + "\n")

    # 2. Run learning cycle
    cycle_res = loop.run_once()
    assert cycle_res["harvested_rows"] == 5
    assert cycle_res["proposed"] == 2
    assert cycle_res["ingested"] == 2
    assert cycle_res["promoted"] >= 1  # 'now' observed 3 times scores >= 0.66 threshold

    # 3. Check skills listing
    all_skills = loop.list_all()
    assert len(all_skills["promoted"]) >= 1

    # 4. Check audit log
    log_file = tmp_path / "logs" / "self_learning_log.jsonl"
    assert log_file.exists()
    assert len(log_file.read_text().splitlines()) == 1


def test_manual_promote_and_prune(tmp_path):
    loop = SelfLearningLoop(tmp_path)

    # Ingest a mock skill directly into proposed
    prop_path = tmp_path / "skills" / "proposed" / "auto_custom.json"
    prop_path.write_text(json.dumps({
        "id": "auto_custom",
        "trigger_tool": "custom",
        "observed_count": 1,
        "skill": "Custom skill test",
        "score": 0.5,
    }))

    # Promote
    prom_res = loop.promote("auto_custom")
    assert prom_res["ok"] is True
    assert (tmp_path / "skills" / "promoted" / "auto_custom.json").exists()

    # Prune
    prune_res = loop.prune("auto_custom")
    assert prune_res["ok"] is True
    assert (tmp_path / "skills" / "pruned" / "auto_custom.json").exists()
    assert not (tmp_path / "skills" / "promoted" / "auto_custom.json").exists()
