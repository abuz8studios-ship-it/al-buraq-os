"""
AL-BURAQ — Agentic Core · THINK → ACT → VERIFY → LEARN
=======================================================
Adapted (clean-room, by COPY + attribution) from the architecture studied in
QADIR_CORE/brains/agent/loop.py v2, which itself credits Hermes (MIT) +
OpenClaw/pi-agent-core (MIT) + Anthropic Claude Agent SDK patterns.

Four pillars per turn:
  THINK  — assemble context, route to best reachable brain
  ACT    — execute any tool calls the brain requests (whitelisted, guarded)
  VERIFY — inspect results for errors; loop/duplicate/no-progress guardrails
  LEARN  — append the full experience to signal.jsonl (fuel for self-learning)

Design law:
  - Engine-agnostic: never force-load a model.
  - Never crash a turn — classify errors, degrade, report honestly.
  - Tools are local + safe; destructive actions require an approval flag.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ── tool registry (safe, local; extend in later phases) ────────────────────────
def _tool_now(_: dict) -> dict:
    return {"now": time.strftime("%Y-%m-%d %H:%M:%S")}

def _tool_device(_: dict) -> dict:
    import platform, shutil
    total, used, free = shutil.disk_usage(".")
    return {"os": platform.system(), "cpu": os.cpu_count(), "disk_free_gb": round(free/1e9, 1)}

def _tool_echo(args: dict) -> dict:
    return {"echo": args.get("text", "")}

TOOLS: dict[str, Callable[[dict], dict]] = {
    "now": _tool_now,
    "device_info": _tool_device,
    "echo": _tool_echo,
}

# ── guardrails (from Hermes patterns) ──────────────────────────────────────────
@dataclass
class Guard:
    seen_calls: list[str] = field(default_factory=list)
    failures: int = 0
    max_failures: int = 3
    max_steps: int = 8

    def duplicate(self, sig: str) -> bool:
        return self.seen_calls.count(sig) >= 2  # same call 3rd time = loop

    def trip(self) -> bool:
        return self.failures >= self.max_failures


# ── the loop ───────────────────────────────────────────────────────────────────
class AgentLoop:
    def __init__(self, brain_url: str, signal_path: Path):
        self.brain_url = brain_url.rstrip("/")
        self.signal_path = signal_path
        self.signal_path.parent.mkdir(parents=True, exist_ok=True)

    # THINK — call the brain (OpenAI-compatible), optionally asking for a tool
    def _think(self, messages: list[dict]) -> dict:
        payload = json.dumps({"messages": messages, "max_tokens": 1024,
                              "temperature": 0.3, "stream": False}).encode()
        req = urllib.request.Request(
            f"{self.brain_url}/v1/chat/completions", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        _m = data["choices"][0]["message"]
        return {"text": (_m.get("content") or _m.get("reasoning_content") or "")}

    # ACT — parse {{tool: name | json-args}} directives and run them
    def _act(self, text: str, guard: Guard) -> list[dict]:
        results = []
        import re
        for m in re.finditer(r"\{\{tool:\s*([a-z_]+)\s*(?:\|\s*(\{.*?\}))?\s*\}\}", text):
            name = m.group(1)
            try:
                args = json.loads(m.group(2)) if m.group(2) else {}
            except Exception:
                args = {}
            sig = f"{name}:{json.dumps(args, sort_keys=True)}"
            if guard.duplicate(sig):
                results.append({"tool": name, "error": "duplicate_call_blocked"})
                continue
            guard.seen_calls.append(sig)
            fn = TOOLS.get(name)
            if not fn:
                results.append({"tool": name, "error": "unknown_tool"})
                guard.failures += 1
                continue
            try:
                results.append({"tool": name, "result": fn(args)})
            except Exception as e:
                results.append({"tool": name, "error": str(e)[:160]})
                guard.failures += 1
        return results

    # VERIFY — did anything error / are we looping?
    def _verify(self, tool_results: list[dict], guard: Guard) -> dict:
        errs = [r for r in tool_results if "error" in r]
        return {"errors": len(errs), "tripped": guard.trip(),
                "ok": len(errs) == 0}

    # LEARN — append the experience (the fuel for P2/P3)
    def _learn(self, rec: dict) -> None:
        try:
            rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
            with open(self.signal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def run(self, user_msg: str, session_id: str | None = None) -> dict:
        """One full agentic turn. Returns the final reply + trace."""
        t0 = time.time()
        guard = Guard()
        trace = []
        system = ("You are Al-Buraq, a local sovereign agent OS. "
                  "To use a tool, write {{tool: NAME | {\"arg\":\"val\"}}}. "
                  "Available tools: now, device_info, echo. "
                  "After a tool result is given, answer the user directly.")
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user_msg}]

        final_text = ""
        for step in range(guard.max_steps):
            # THINK
            try:
                think = self._think(messages)
            except Exception as e:
                self._learn({"kind": "turn", "user": user_msg, "ok": False,
                             "error": f"think_failed: {e}"[:160], "session": session_id})
                return {"ok": False, "reply": f"Brain error: {e}", "trace": trace}
            text = think["text"]
            trace.append({"step": step, "think": text[:200]})

            # ACT
            tool_results = self._act(text, guard)
            if not tool_results:
                final_text = text
                break  # no tool requested -> this is the answer
            trace.append({"step": step, "tools": tool_results})

            # VERIFY
            v = self._verify(tool_results, guard)
            trace.append({"step": step, "verify": v})
            if v["tripped"]:
                final_text = text + "\n\n(stopped: guardrail tripped after repeated errors)"
                break

            # feed tool results back for the next THINK
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user",
                             "content": "Tool results: " + json.dumps(tool_results)})

        dt = round(time.time() - t0, 2)
        # LEARN
        self._learn({"kind": "turn", "user": user_msg, "ok": True,
                     "steps": len(trace), "reply_len": len(final_text),
                     "duration_s": dt, "session": session_id,
                     "used_tools": [t for tr in trace for t in tr.get("tools", [])][:10]})
        return {"ok": True, "reply": final_text or "(no reply)",
                "steps": len([t for t in trace if "think" in t]),
                "duration_s": dt, "trace": trace}
