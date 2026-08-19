"""
AL-BURAQ — Self-Learning Skill Loop
====================================
Adapted (clean-room, by COPY + attribution) from the architecture studied in
QADIR_CORE/brains/agent/self_learning.py (G15) and skills/engine/eval_loop.py.

The cycle (runs on schedule, in background, NEVER blocks serving):

  HARVEST          PROPOSE              INGEST                EVALUATE
  read signal  →   detect repeated  →   write skill YAML  →   score; promote
  .jsonl turns     successful           to skills/proposed    (>=thresh) or
                   patterns                                   prune (fails)
                                                                  ↓
                                                       append self_learning_log

Design law:
  - Safety-gated: idempotent, never double-proposes the same skill, never blocks.
  - Honest: a skill is "promoted" only if it actually scores >= threshold.
  - No external deps; pure stdlib so it ships and runs anywhere.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path

PROMOTE_THRESHOLD = 0.66       # score a proposed skill must reach
MIN_PATTERN_COUNT = 2          # a pattern must repeat this many times to propose
MAX_PROPOSALS_PER_CYCLE = 5


class SelfLearningLoop:
    def __init__(self, data_dir: Path):
        self.data = Path(data_dir)
        self.signal = self.data / "logs" / "signal.jsonl"
        self.proposed_dir = self.data / "skills" / "proposed"
        self.promoted_dir = self.data / "skills" / "promoted"
        self.log = self.data / "logs" / "self_learning_log.jsonl"
        for d in (self.proposed_dir, self.promoted_dir, self.log.parent):
            d.mkdir(parents=True, exist_ok=True)

    # ── HARVEST ────────────────────────────────────────────────────────────────
    def harvest(self) -> list[dict]:
        if not self.signal.exists():
            return []
        rows = []
        for line in self.signal.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows

    # ── PROPOSE ────────────────────────────────────────────────────────────────
    def propose(self, rows: list[dict]) -> list[dict]:
        """Detect repeated successful tool usage -> propose a skill."""
        tool_counter = Counter()
        for r in rows:
            if not r.get("ok"):
                continue
            for t in (r.get("used_tools") or []):
                name = t.get("tool") if isinstance(t, dict) else str(t)
                if name:
                    tool_counter[name] += 1
        proposals = []
        for tool, n in tool_counter.most_common(MAX_PROPOSALS_PER_CYCLE):
            if n < MIN_PATTERN_COUNT:
                continue
            slug = f"auto_{tool}"
            proposals.append({
                "id": slug, "trigger_tool": tool, "observed_count": n,
                "skill": f"When the user's need matches '{tool}', call the {tool} tool directly.",
            })
        return proposals

    # ── INGEST ─────────────────────────────────────────────────────────────────
    def ingest(self, proposals: list[dict]) -> dict:
        written, skipped = 0, 0
        for p in proposals:
            path = self.proposed_dir / f"{p['id']}.json"
            if path.exists():
                skipped += 1
                continue
            p["proposed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            p["status"] = "proposed"
            path.write_text(json.dumps(p, indent=2), encoding="utf-8")
            written += 1
        return {"written": written, "skipped_existing": skipped}

    # ── EVALUATE ───────────────────────────────────────────────────────────────
    def _score(self, proposal: dict) -> float:
        """Honest heuristic score: more observations + a real trigger = higher.
        (In the GPU build this calls a real eval harness; here it's deterministic.)"""
        n = proposal.get("observed_count", 0)
        base = min(1.0, n / 5.0)            # 5+ observations -> full confidence
        has_trigger = 1.0 if proposal.get("trigger_tool") else 0.0
        return round(0.5 * base + 0.5 * has_trigger, 3)

    def evaluate(self) -> dict:
        promoted, pruned, pending = 0, 0, 0
        for path in self.proposed_dir.glob("*.json"):
            try:
                p = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            score = self._score(p)
            p["score"] = score
            if score >= PROMOTE_THRESHOLD:
                p["status"] = "promoted"
                (self.promoted_dir / path.name).write_text(json.dumps(p, indent=2), encoding="utf-8")
                path.unlink(missing_ok=True)
                promoted += 1
            elif score < 0.34:
                p["status"] = "pruned"
                path.unlink(missing_ok=True)
                pruned += 1
            else:
                p["status"] = "pending"
                path.write_text(json.dumps(p, indent=2), encoding="utf-8")
                pending += 1
        return {"promoted": promoted, "pruned": pruned, "pending": pending}

    # ── one full cycle ──────────────────────────────────────────────────────────
    def run_once(self) -> dict:
        t0 = time.time()
        rows = self.harvest()
        proposals = self.propose(rows)
        ing = self.ingest(proposals)
        ev = self.evaluate()
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "duration_s": round(time.time() - t0, 3),
               "harvested_rows": len(rows), "proposed": len(proposals),
               "ingested": ing["written"], "skipped_existing": ing["skipped_existing"],
               **ev}
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "data"
    print(json.dumps(SelfLearningLoop(Path(d)).run_once(), indent=2))
