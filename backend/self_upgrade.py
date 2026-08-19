"""
AL-BURAQ — Self-Upgrade Loop (propose/receipt mode)
====================================================
Adapted (clean-room, by COPY + attribution) from QADIR_CORE/core/self_learning_loop.py.

signal.jsonl -> rolling success eval -> regression/saturation detector ->
LoRA finetune TRIGGER RECEIPT (does NOT train here; records what it WOULD train).

Honest by design: on a buyer's laptop there is no training GPU, so this loop
runs in propose/receipt-only mode. It NEVER claims it trained. It writes an
auditable receipt explaining why a retrain WOULD fire, for a human/GPU box to act on.

Safety: idempotent, cost-gated (0 = local only), max triggers/day cap,
detects BOTH regression (got worse) and saturation (no refresh in N days).
"""
from __future__ import annotations
import json, time
from pathlib import Path
from datetime import datetime, timezone

MIN_NEW_SIGNAL = 5            # demo-sized; production ~200
REGRESSION_THRESH = 0.05     # 5% drop vs baseline
SATURATION_DAYS = 7
MAX_TRIGGER_PER_DAY = 2

class SelfUpgradeLoop:
    def __init__(self, data_dir: Path):
        self.data = Path(data_dir)
        self.signal = self.data / "logs" / "signal.jsonl"
        self.baseline = self.data / "baseline.json"
        self.triggers = self.data / "triggers"; self.triggers.mkdir(parents=True, exist_ok=True)
        self.log = self.data / "logs" / "self_upgrade_log.jsonl"
        self.log.parent.mkdir(parents=True, exist_ok=True)

    def _rows(self):
        if not self.signal.exists(): return []
        out=[]
        for ln in self.signal.read_text(encoding="utf-8").splitlines():
            ln=ln.strip()
            if not ln: continue
            try: out.append(json.loads(ln))
            except Exception: pass
        return out

    def _rolling_success(self, rows):
        turns = [r for r in rows if r.get("kind")=="turn" or "ok" in r]
        if not turns: return None, 0
        ok = sum(1 for r in turns if r.get("ok"))
        return round(ok/len(turns), 4), len(turns)

    def _triggers_today(self):
        today = time.strftime("%Y-%m-%d")
        return sum(1 for f in self.triggers.glob("*.json") if today in f.name)

    def run_once(self):
        t0=time.time()
        rows=self._rows()
        success, n = self._rolling_success(rows)
        base = {}
        if self.baseline.exists():
            try: base=json.loads(self.baseline.read_text(encoding="utf-8"))
            except Exception: base={}
        base_success = base.get("success")
        reason=None; fired=False
        if success is None or n < MIN_NEW_SIGNAL:
            reason = "insufficient_signal (need %d, have %d)" % (MIN_NEW_SIGNAL, n)
        elif base_success is not None and (base_success - success) >= REGRESSION_THRESH:
            reason = "regression: %.3f -> %.3f (>= %.2f drop)" % (base_success, success, REGRESSION_THRESH)
            fired=True
        else:
            last = base.get("last_trigger_ts")
            stale = True
            if last:
                try:
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days
                    stale = age >= SATURATION_DAYS
                except Exception: stale=True
            if stale and base_success is None:
                reason = "baseline_init (first cycle, establish baseline)"
            elif stale:
                reason = "saturation: no refresh in >= %d days" % SATURATION_DAYS
                fired=True
            else:
                reason = "healthy: success %.3f, no action" % success

        receipt_path=None
        if fired and self._triggers_today() < MAX_TRIGGER_PER_DAY:
            ts = time.strftime("%Y-%m-%dT%H-%M-%S")
            receipt = {"ts": ts, "mode": "propose_only",
                       "reason": reason, "rolling_success": success, "n_turns": n,
                       "would_train": "LoRA finetune on recent signal.jsonl",
                       "cost_usd_cap": 0.0, "note": "No training performed (no GPU on this device). Human/GPU box acts on this receipt."}
            receipt_path = str(self.triggers / ("trigger_"+ts+".json"))
            Path(receipt_path).write_text(json.dumps(receipt, indent=2), encoding="utf-8")

        # update baseline
        newbase = {"success": success, "n_turns": n,
                   "updated": datetime.now(timezone.utc).isoformat()}
        if fired: newbase["last_trigger_ts"] = datetime.now(timezone.utc).isoformat()
        elif base.get("last_trigger_ts"): newbase["last_trigger_ts"]=base["last_trigger_ts"]
        self.baseline.write_text(json.dumps(newbase, indent=2), encoding="utf-8")

        rec={"ts":time.strftime("%Y-%m-%dT%H:%M:%S%z"),"duration_s":round(time.time()-t0,3),
             "rolling_success":success,"n_turns":n,"baseline_success":base_success,
             "fired":fired,"reason":reason,"receipt":receipt_path}
        with open(self.log,"a",encoding="utf-8") as f: f.write(json.dumps(rec)+"\n")
        return rec

if __name__=="__main__":
    import sys
    d=sys.argv[1] if len(sys.argv)>1 else "data"
    print(json.dumps(SelfUpgradeLoop(Path(d)).run_once(), indent=2))
