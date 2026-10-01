"""
AL-BURAQ — Self-Learning Skill Loop
====================================
Adapted (clean-room, by COPY + attribution) from the architecture studied in
QADIR_CORE/brains/agent/self_learning.py (G15) and skills/engine/eval_loop.py.

The cycle (runs on schedule, in background, NEVER blocks serving):

  HARVEST          PROPOSE              INGEST                EVALUATE
  read signal  →   detect repeated  →   write skill JSON  →   score; promote
  .jsonl turns     successful           to skills/proposed    (>=thresh) or
                   patterns                                   prune (<thresh)
                                                                  ↓
                                                       append self_learning_log

Design law:
  - Safety-gated: idempotent, never double-proposes the same skill, never blocks.
  - Honest: a skill is "promoted" only if it actually scores >= threshold.
  - No external deps; pure stdlib so it ships and runs anywhere.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

PROMOTE_THRESHOLD = 0.66       # score a proposed skill must reach
MIN_PATTERN_COUNT = 2          # a pattern must repeat this many times to propose
MAX_PROPOSALS_PER_CYCLE = 5
MAX_HARVEST_ROWS = 5000        # harvest reads only the recent tail — bounded cost


class SelfLearningLoop:
    def __init__(self, data_dir: Path | str):
        self.data = Path(data_dir)
        self.signal = self.data / "logs" / "signal.jsonl"
        self.proposed_dir = self.data / "skills" / "proposed"
        self.promoted_dir = self.data / "skills" / "promoted"
        self.pruned_dir = self.data / "skills" / "pruned"
        self.log = self.data / "logs" / "self_learning_log.jsonl"
        for d in (self.proposed_dir, self.promoted_dir, self.pruned_dir, self.log.parent):
            d.mkdir(parents=True, exist_ok=True)

    # ── HARVEST ────────────────────────────────────────────────────────────────
    def harvest(self) -> list[dict[str, Any]]:
        """Recent-tail harvest (bounded): pattern detection only needs recent
        behavior, and cost must not grow with history size."""
        from jsonl_io import tail_jsonl
        return tail_jsonl(self.signal, MAX_HARVEST_ROWS)

    def last_cycle_ts(self) -> str | None:
        """Timestamp of the last REAL learning cycle (from the audit log)."""
        from jsonl_io import tail_jsonl
        rows = tail_jsonl(self.log, 1)
        return rows[-1].get("ts") if rows else None

    # ── PROPOSE ────────────────────────────────────────────────────────────────
    def propose(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect repeated successful tool usage and intent patterns -> propose a skill."""
        tool_counter: Counter[str] = Counter()
        for r in rows:
            if not r.get("ok"):
                continue
            for t in (r.get("used_tools") or []):
                name = t.get("tool") if isinstance(t, dict) else str(t)
                if name:
                    tool_counter[name] += 1

        proposals: list[dict[str, Any]] = []
        for tool, n in tool_counter.most_common(MAX_PROPOSALS_PER_CYCLE):
            if n < MIN_PATTERN_COUNT:
                continue
            slug = f"auto_{tool}"
            proposals.append({
                "id": slug,
                "trigger_tool": tool,
                "observed_count": n,
                "skill": f"When the user's need matches '{tool}', call the {tool} tool directly.",
                "quality_score": min(1.0, round(n / 4.0, 3)),
            })
        return proposals

    # ── INGEST ─────────────────────────────────────────────────────────────────
    def ingest(self, proposals: list[dict[str, Any]]) -> dict[str, Any]:
        written, skipped = 0, 0
        for p in proposals:
            path = self.proposed_dir / f"{p['id']}.json"
            if path.exists() or (self.promoted_dir / f"{p['id']}.json").exists():
                skipped += 1
                continue
            p["proposed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            p["status"] = "proposed"
            path.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
            written += 1
        return {"written": written, "skipped_existing": skipped}

    # ── EVALUATE ───────────────────────────────────────────────────────────────
    def _score(self, proposal: dict[str, Any]) -> float:
        """Honest heuristic score: observation volume + real trigger tool validity."""
        n = proposal.get("observed_count", 0)
        base = min(1.0, n / 5.0)  # 5+ observations -> full confidence
        has_trigger = 1.0 if proposal.get("trigger_tool") else 0.0
        return round(0.5 * base + 0.5 * has_trigger, 3)

    def evaluate(self) -> dict[str, Any]:
        promoted, pruned, pending = 0, 0, 0
        promoted_ids: list[str] = []
        pruned_ids: list[str] = []

        for path in self.proposed_dir.glob("*.json"):
            try:
                p = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            score = self._score(p)
            p["score"] = score
            if score >= PROMOTE_THRESHOLD:
                p["status"] = "promoted"
                p["promoted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                (self.promoted_dir / path.name).write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
                path.unlink(missing_ok=True)
                promoted += 1
                promoted_ids.append(p.get("id", path.stem))
            elif score < 0.34:
                p["status"] = "pruned"
                p["pruned_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                (self.pruned_dir / path.name).write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
                path.unlink(missing_ok=True)
                pruned += 1
                pruned_ids.append(p.get("id", path.stem))
            else:
                p["status"] = "pending"
                path.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
                pending += 1

        return {
            "promoted": promoted,
            "pruned": pruned,
            "pending": pending,
            "promoted_ids": promoted_ids,
            "pruned_ids": pruned_ids,
        }

    def promote(self, skill_id: str) -> dict[str, Any]:
        """Manually promote a skill from proposed to promoted."""
        src = self.proposed_dir / f"{skill_id}.json"
        if not src.exists():
            return {"ok": False, "error": f"proposed skill '{skill_id}' not found"}
        p = json.loads(src.read_text(encoding="utf-8"))
        p["status"] = "promoted"
        p["promoted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        p["score"] = max(p.get("score", 0.0), PROMOTE_THRESHOLD)
        (self.promoted_dir / f"{skill_id}.json").write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
        src.unlink(missing_ok=True)
        return {"ok": True, "promoted": skill_id, "skill": p}

    def prune(self, skill_id: str) -> dict[str, Any]:
        """Manually prune a skill."""
        for d in (self.proposed_dir, self.promoted_dir):
            src = d / f"{skill_id}.json"
            if src.exists():
                p = json.loads(src.read_text(encoding="utf-8"))
                p["status"] = "pruned"
                p["pruned_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                (self.pruned_dir / f"{skill_id}.json").write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
                src.unlink(missing_ok=True)
                return {"ok": True, "pruned": skill_id}
        return {"ok": False, "error": f"skill '{skill_id}' not found"}

    def list_all(self) -> dict[str, list[dict[str, Any]]]:
        def _read_dir(d: Path) -> list[dict[str, Any]]:
            out = []
            if d.exists():
                for f in sorted(d.glob("*.json")):
                    try:
                        out.append(json.loads(f.read_text(encoding="utf-8")))
                    except Exception:
                        pass
            return out

        return {
            "proposed": _read_dir(self.proposed_dir),
            "promoted": _read_dir(self.promoted_dir),
            "pruned": _read_dir(self.pruned_dir),
        }

    # ── one full cycle ──────────────────────────────────────────────────────────
    def run_once(self) -> dict[str, Any]:
        t0 = time.time()
        rows = self.harvest()
        proposals = self.propose(rows)
        ing = self.ingest(proposals)
        ev = self.evaluate()
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "duration_s": round(time.time() - t0, 3),
            "harvested_rows": len(rows),
            "proposed": len(proposals),
            "ingested": ing["written"],
            "skipped_existing": ing["skipped_existing"],
            **ev,
        }
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "data"
    print(json.dumps(SelfLearningLoop(Path(d)).run_once(), indent=2))
