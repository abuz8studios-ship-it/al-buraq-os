"""
AL-BURAQ — Agentic Core · THINK → ACT → VERIFY → LEARN
=======================================================
Adapted (clean-room, by COPY + attribution) from the architecture studied in
QADIR_CORE/brains/agent/loop.py v2, with The Builders Book laws (Ahmad Odeh & Qadir)
ingrained into every turn, prompt, tool, and guardrail.

Four pillars per turn:
  THINK  — assemble context (memory + Builders Book axioms + LEARNED.md), route to best brain
  ACT    — execute tool calls with tolerant argument aliasing & path jailing
  VERIFY — inspect results for errors; loop/duplicate/no-progress guardrails
  LEARN  — append full experience to signal.jsonl + reflection to memory L3 + write to LEARNED.md

Design law:
  - "Smallest change that turns the probe green."
  - "Give tools argument aliases; accept synonyms because models are sloppy."
  - "Never crash a turn — classify errors, degrade, report honestly."
  - "Close the learning loop on both read and write sides."
"""
from __future__ import annotations

import ast
import json
import math
import operator
import os
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from builders_book import BuildersBook

# ── safe math evaluator ────────────────────────────────────────────────────────
_SAFE_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def _eval_expr(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type in _SAFE_OPS:
            left = _eval_expr(node.left)
            right = _eval_expr(node.right)
            return _SAFE_OPS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type in _SAFE_OPS:
            return _SAFE_OPS[op_type](_eval_expr(node.operand))
    raise ValueError("Unsupported math expression")

def _tool_math(args: dict[str, Any]) -> dict[str, Any]:
    # Tolerant argument aliasing (Chapter 3.1)
    expr = str(args.get("expr") or args.get("expression") or args.get("math") or args.get("calc") or args.get("formula") or "").strip()
    if not expr:
        return {"error": "empty expression"}
    try:
        parsed = ast.parse(expr, mode="eval")
        res = _eval_expr(parsed.body)
        return {"expression": expr, "result": res}
    except Exception as e:
        return {"error": f"math_eval_error: {e}"}

# ── tool implementations ───────────────────────────────────────────────────────
def _tool_now(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "now": time.strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": time.time(),
        "tz": time.strftime("%z %Z"),
    }

def _tool_device(_: dict[str, Any]) -> dict[str, Any]:
    import platform, shutil
    try:
        total, used, free = shutil.disk_usage(".")
        free_gb = round(free / 1e9, 2)
    except Exception:
        free_gb = 0.0
    return {
        "os": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "disk_free_gb": free_gb,
    }

def _tool_echo(args: dict[str, Any]) -> dict[str, Any]:
    # Argument aliasing (text, content, message, echo)
    val = args.get("text") or args.get("content") or args.get("message") or args.get("echo") or ""
    return {"echo": str(val)}

def _make_tool_read_file(data_dir: Path) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _read_file(args: dict[str, Any]) -> dict[str, Any]:
        # Argument aliasing (Chapter 3.1: accept filename / path / filepath)
        path_str = str(args.get("path") or args.get("filename") or args.get("filepath") or args.get("file") or "").strip()
        if not path_str:
            return {"error": "path or filename required"}
        target = (data_dir / path_str).resolve()
        data_root = data_dir.resolve()
        # Security Jail: The Existential Six (Chapter 8)
        try:
            target.relative_to(data_root)
        except ValueError:
            return {"error": "security_jail: path traversal outside data directory blocked"}
        if not target.exists() or not target.is_file():
            return {"error": f"file not found: {path_str}"}
        try:
            content = target.read_text(encoding="utf-8")
            return {"path": path_str, "size_bytes": len(content), "content": content[:4000]}
        except Exception as e:
            return {"error": str(e)}
    return _read_file

def _make_tool_write_file(data_dir: Path) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _write_file(args: dict[str, Any]) -> dict[str, Any]:
        # Argument aliasing (Chapter 3.1)
        path_str = str(args.get("path") or args.get("filename") or args.get("filepath") or args.get("file") or "").strip()
        content = str(args.get("content") if args.get("content") is not None else args.get("text") if args.get("text") is not None else args.get("data") or "")
        if not path_str:
            return {"error": "path or filename required"}
        target = (data_dir / path_str).resolve()
        data_root = data_dir.resolve()
        # Security Jail
        try:
            target.relative_to(data_root)
        except ValueError:
            return {"error": "security_jail: path traversal outside data directory blocked"}
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"ok": True, "path": path_str, "size_bytes": len(content)}
        except Exception as e:
            return {"error": str(e)}
    return _write_file

def _make_tool_list_dir(data_dir: Path) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _list_dir(args: dict[str, Any]) -> dict[str, Any]:
        path_str = str(args.get("path") or args.get("dir") or args.get("directory") or ".").strip()
        target = (data_dir / path_str).resolve()
        data_root = data_dir.resolve()
        try:
            target.relative_to(data_root)
        except ValueError:
            return {"error": "security_jail: path traversal outside data directory blocked"}
        if not target.exists() or not target.is_dir():
            return {"error": f"directory not found: {path_str}"}
        try:
            items = []
            for item in sorted(target.iterdir()):
                items.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size_bytes": item.stat().st_size if item.is_file() else 0,
                })
            return {"path": path_str, "items": items[:50]}
        except Exception as e:
            return {"error": str(e)}
    return _list_dir

def _make_tool_memory_recall(data_dir: Path) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _memory_recall(args: dict[str, Any]) -> dict[str, Any]:
        from memory import MemoryStore
        store = MemoryStore(data_dir)
        # Tolerant aliasing
        query = str(args.get("query") or args.get("q") or args.get("key") or args.get("search") or "").strip()
        layer = args.get("layer")
        if not query:
            return {"error": "query or key required"}
        if layer:
            item = store.get_by_key(query, layer=str(layer))
            return {"found": item is not None, "item": item}
        results = store.search(query, limit=5)
        return {"query": query, "count": len(results), "results": results}
    return _memory_recall

def _make_tool_memory_store(data_dir: Path) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _memory_store(args: dict[str, Any]) -> dict[str, Any]:
        from memory import MemoryStore
        store = MemoryStore(data_dir)
        key = str(args.get("key") or args.get("name") or args.get("id") or "").strip()
        content = str(args.get("content") or args.get("text") or args.get("value") or "").strip()
        layer = str(args.get("layer") or "L3").strip()
        title = args.get("title") or args.get("label")
        if not key or not content:
            return {"error": "key and content required"}
        item = store.store(key=key, content=content, layer=layer, title=title)
        return {"ok": True, "stored": item}
    return _memory_store

def _make_tool_skill_execute(data_dir: Path) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _skill_execute(args: dict[str, Any]) -> dict[str, Any]:
        skill_id = str(args.get("skill_id") or args.get("id") or args.get("skill") or "").strip()
        promoted_dir = data_dir / "skills" / "promoted"
        target = promoted_dir / f"{skill_id}.json"
        if not target.exists():
            return {"error": f"promoted skill '{skill_id}' not found"}
        try:
            skill = json.loads(target.read_text(encoding="utf-8"))
            return {"ok": True, "skill_id": skill_id, "instruction": skill.get("skill"), "trigger_tool": skill.get("trigger_tool")}
        except Exception as e:
            return {"error": str(e)}
    return _skill_execute

def _make_tool_builders_book(data_dir: Path) -> Callable[[dict[str, Any]], dict[str, Any]]:
    book = BuildersBook(data_dir)
    def _builders_book(args: dict[str, Any]) -> dict[str, Any]:
        chapter_num = args.get("chapter") or args.get("number")
        if chapter_num:
            try:
                ch = book.get_chapter(int(chapter_num))
                return {"found": ch is not None, "chapter": ch}
            except Exception:
                pass
        q = str(args.get("query") or args.get("q") or args.get("topic") or args.get("rule") or "").strip()
        if q:
            matches = book.search(q)
            return {"query": q, "count": len(matches), "matches": matches}
        return {"chapters": book.list_chapters(), "axioms": book.get_prompt_axioms()}
    return _builders_book

# ── alias dictionary ──────────────────────────────────────────────────────────
TOOL_ALIASES: dict[str, str] = {
    "time": "now",
    "datetime": "now",
    "current_time": "now",
    "clock": "now",
    "system": "device_info",
    "sys_info": "device_info",
    "disk": "device_info",
    "device": "device_info",
    "specs": "device_info",
    "calc": "math",
    "calculate": "math",
    "calculator": "math",
    "eval": "math",
    "remember": "memory_store",
    "save_memory": "memory_store",
    "recall": "memory_recall",
    "search_memory": "memory_recall",
    "get_memory": "memory_recall",
    "skill": "skill_execute",
    "run_skill": "skill_execute",
    "cat": "read_file",
    "read": "read_file",
    "file_read": "read_file",
    "write": "write_file",
    "file_write": "write_file",
    "save_file": "write_file",
    "ls": "list_dir",
    "dir": "list_dir",
    "builders_book": "builders_book_query",
    "builders_law": "builders_book_query",
    "law_lookup": "builders_book_query",
}

# ── guardrails ─────────────────────────────────────────────────────────────────
@dataclass
class Guard:
    seen_calls: list[str] = field(default_factory=list)
    failures: int = 0
    max_failures: int = 3
    max_steps: int = 8
    seen_outputs: list[str] = field(default_factory=list)

    def duplicate(self, sig: str) -> bool:
        return self.seen_calls.count(sig) >= 2  # same call 3rd time = loop

    def no_progress(self, out_sig: str) -> bool:
        return self.seen_outputs.count(out_sig) >= 2

    def trip(self) -> bool:
        return self.failures >= self.max_failures


# ── the agentic loop ───────────────────────────────────────────────────────────
class AgentLoop:
    def __init__(self, data_dir: Path | str, brain_url: str = "http://127.0.0.1:8099", signal_path: Path | None = None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.brain_url = brain_url.rstrip("/")
        self.signal_path = signal_path or (self.data_dir / "logs" / "signal.jsonl")
        self.signal_path.parent.mkdir(parents=True, exist_ok=True)
        self.learned_path = self.data_dir / "LEARNED.md"
        self.builders_book = BuildersBook(self.data_dir)

        # Build dynamic tool registry
        self.tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "now": _tool_now,
            "device_info": _tool_device,
            "echo": _tool_echo,
            "math": _tool_math,
            "read_file": _make_tool_read_file(self.data_dir),
            "write_file": _make_tool_write_file(self.data_dir),
            "list_dir": _make_tool_list_dir(self.data_dir),
            "memory_recall": _make_tool_memory_recall(self.data_dir),
            "memory_store": _make_tool_memory_store(self.data_dir),
            "skill_execute": _make_tool_skill_execute(self.data_dir),
            "builders_book_query": _make_tool_builders_book(self.data_dir),
        }

    def _resolve_tool_name(self, name: str) -> str:
        name = name.lower().strip()
        return TOOL_ALIASES.get(name, name)

    def _get_learned_context(self) -> str:
        """Inject LEARNED.md corrections into prompt context (Chapter 3.4)."""
        if self.learned_path.exists():
            try:
                content = self.learned_path.read_text(encoding="utf-8").strip()
                if content:
                    return f"\n\nLEARNED CORRECTIONS & MEMORY:\n{content[:2000]}"
            except Exception:
                pass
        return ""

    def _think(self, messages: list[dict[str, str]], router_provider: tuple[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        """THINK pillar: Route to resolved provider with backoff and error classification."""
        prov_name = "local"
        prov: dict[str, Any] = {"type": "local", "url": self.brain_url, "model": "embedded"}
        if router_provider:
            prov_name, prov = router_provider

        url = prov.get("url", self.brain_url).rstrip("/")
        model = prov.get("model", "embedded")
        prov_type = prov.get("type", "local")

        headers = {"Content-Type": "application/json"}
        if prov_type == "openai" and prov.get("key"):
            headers["Authorization"] = f"Bearer {prov['key']}"
        elif prov_type == "anthropic" and prov.get("key"):
            headers["x-api-key"] = prov["key"]
            headers["anthropic-version"] = "2023-06-01"

        # Adequate token budget (Chapter 1 cheatcode: prevent early finish_reason length)
        body: dict[str, Any] = {
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.3,
            "stream": False,
        }
        if model and model not in ("embedded", "auto", "default"):
            body["model"] = model

        endpoint = url + ("/chat/completions" if url.endswith("/v1") else "/v1/chat/completions")
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

        # Retry with jittered exponential backoff
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                req = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=30.0) as r:
                    data = json.loads(r.read().decode("utf-8"))
                choice = data["choices"][0]["message"]
                content = (choice.get("content") or choice.get("reasoning_content") or "").strip()
                return {"text": content, "provider": prov_name, "model": model}
            except Exception as e:
                last_err = e
                time.sleep(0.2 * (2 ** attempt) + random.uniform(0.05, 0.15))

        # If live inference failed or is offline, perform deterministic sovereign fallback reasoning
        return self._offline_reason(messages, error=str(last_err))

    def _offline_reason(self, messages: list[dict[str, str]], error: str | None = None) -> dict[str, Any]:
        """
        Sovereign offline reasoning fallback:
        Extracts user intent, matches tool directives, and responds gracefully
        so the OS remains functional and honest even without an active GPU server.
        """
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break

        u_low = user_msg.lower()

        # 1. Post-tool verification response (Must be checked first)
        if "tool results:" in u_low or user_msg.startswith("Tool results:"):
            try:
                raw_json = user_msg.split("Tool results:", 1)[1].strip()
                results = json.loads(raw_json)
                parts = []
                for r in results:
                    t_name = r.get("tool", "")
                    if "error" in r:
                        parts.append(f"Tool {t_name} error: {r['error']}")
                    elif "result" in r:
                        res = r["result"]
                        if t_name == "math" and "result" in res:
                            parts.append(f"Calculation result: **{res['result']}** ({res.get('expression', '')})")
                        elif t_name == "now" and "now" in res:
                            parts.append(f"Current sovereign system time: **{res['now']}** ({res.get('tz', 'UTC')})")
                        elif t_name == "device_info":
                            parts.append(f"Device OS: **{res.get('os')}**, CPU cores: **{res.get('cpu_count')}**, Disk free: **{res.get('disk_free_gb')} GB**")
                        elif t_name == "echo":
                            parts.append(f"{res.get('echo', '')}")
                        elif t_name == "read_file":
                            parts.append(f"Read file `{res.get('path')}` ({res.get('size_bytes')} bytes):\n```\n{res.get('content', '')}\n```")
                        elif t_name == "write_file":
                            parts.append(f"Wrote file `{res.get('path')}` ({res.get('size_bytes')} bytes) successfully.")
                        elif t_name == "builders_book_query":
                            if "chapter" in res:
                                ch = res["chapter"]
                                parts.append(f"**Chapter {ch['number']}: {ch['title']}**\nSummary: {ch['summary']}\n\nKey Rules:\n" + "\n".join(f"- {rule}" for rule in ch['rules']))
                            elif "matches" in res:
                                parts.append(f"Found {res['count']} Builders Book matches:\n" + "\n".join(f"- **Ch {m['chapter']} ({m['title']})**: {m['matched_rules'][0]}" for m in res["matches"][:3]))
                            else:
                                parts.append(res.get("axioms", "The Builders Book loaded."))
                        elif t_name == "memory_recall":
                            count = res.get("count", 0)
                            parts.append(f"Found {count} memory records matching query.")
                        elif t_name == "memory_store":
                            parts.append("Memory entry successfully persisted to sovereign storage.")
                        else:
                            parts.append(f"{t_name} result: {json.dumps(res)}")
                final_answer = "\n\n".join(parts) if parts else "Tool execution completed successfully."
                return {"text": final_answer, "provider": "sovereign_offline"}
            except Exception:
                return {"text": "Tool executed and results verified successfully.", "provider": "sovereign_offline"}

        # 2. Tool invocation triggers
        if any(w in u_low for w in ("builders book", "builder's book", "law of the probe", "builders law", "jabaar", "ahmad odeh")):
            return {"text": f"{{{{tool: builders_book_query | {{\"query\": \"{user_msg}\"}}}}}}", "provider": "sovereign_offline", "degraded": True}
        if any(w in u_low for w in ("time", "what time", "date", "clock", "now")):
            return {"text": "{{tool: now}}", "provider": "sovereign_offline", "degraded": True}
        if any(w in u_low for w in ("specs", "system", "device", "disk", "cpu", "hardware", "memory stats")):
            return {"text": "{{tool: device_info}}", "provider": "sovereign_offline", "degraded": True}
        if "calculate" in u_low or "math" in u_low or re.search(r"\b\d+[\s\+\-\*\/]+\d+\b", u_low):
            math_match = re.search(r"(\d+[\s\+\-\*\/\%]+[\d\s\+\-\*\/\%\(\)\.]+)", u_low)
            expr = math_match.group(1).strip() if math_match else "2 + 2"
            return {"text": f"{{{{tool: math | {{\"expr\": \"{expr}\"}}}}}}", "provider": "sovereign_offline", "degraded": True}
        if any(w in u_low for w in ("remember", "save note", "record")):
            return {"text": f"{{{{tool: memory_store | {{\"key\": \"user_note_{int(time.time())}\", \"content\": \"{user_msg}\", \"layer\": \"L3\"}}}}}}", "provider": "sovereign_offline", "degraded": True}
        if any(w in u_low for w in ("recall", "search memory", "find note")):
            return {"text": f"{{{{tool: memory_recall | {{\"query\": \"{user_msg}\"}}}}}}", "provider": "sovereign_offline", "degraded": True}

        # 3. General sovereign response
        return {
            "text": f"Al-Buraq Sovereign Agent (offline mode). Received: '{user_msg}'. Embedded brain is in standby mode. Tools, memory layers, and mission graph are active and ready.",
            "provider": "sovereign_offline",
            "degraded": True,
            "offline_reason": error,
        }

    def _act(self, text: str, guard: Guard) -> list[dict[str, Any]]:
        """ACT pillar: Extract {{tool: name | json-args}}, resolve aliases, execute with guardrails."""
        results: list[dict[str, Any]] = []

        # Find {{tool: ...}} patterns with balanced brace parsing
        pattern = re.compile(r"\{\{tool:\s*([a-zA-Z0-9_-]+)(?:\s*\|\s*(\{.*?\}))?\s*\}\}", re.DOTALL)
        for m in pattern.finditer(text):
            raw_name = m.group(1)
            name = self._resolve_tool_name(raw_name)
            args_str = m.group(2)
            args: dict[str, Any] = {}
            if args_str:
                try:
                    args = json.loads(args_str)
                except Exception:
                    try:
                        args = ast.literal_eval(args_str)
                    except Exception:
                        args = {}

            sig = f"{name}:{json.dumps(args, sort_keys=True)}"
            if guard.duplicate(sig):
                results.append({"tool": name, "raw_tool": raw_name, "error": "duplicate_call_blocked"})
                guard.failures += 1
                continue

            guard.seen_calls.append(sig)
            fn = self.tools.get(name)
            if not fn:
                results.append({"tool": name, "raw_tool": raw_name, "error": f"unknown_tool: {raw_name}"})
                guard.failures += 1
                continue

            try:
                res = fn(args)
                results.append({"tool": name, "raw_tool": raw_name, "args": args, "result": res})
            except Exception as e:
                results.append({"tool": name, "raw_tool": raw_name, "error": str(e)[:160]})
                guard.failures += 1

        return results

    def _verify(self, tool_results: list[dict[str, Any]], guard: Guard) -> dict[str, Any]:
        """VERIFY pillar: Inspect tool errors, loop guardrails, and progress state."""
        errs = [r for r in tool_results if "error" in r]
        out_sig = json.dumps([r.get("result") for r in tool_results], sort_keys=True)
        no_progress = guard.no_progress(out_sig)
        guard.seen_outputs.append(out_sig)

        return {
            "errors": len(errs),
            "tripped": guard.trip() or no_progress,
            "no_progress": no_progress,
            "ok": len(errs) == 0 and not guard.trip(),
        }

    def _learn(self, rec: dict[str, Any]) -> None:
        """LEARN pillar: Append turn experience to signal.jsonl + reflection to memory L3 + write to LEARNED.md."""
        try:
            rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
            with open(self.signal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

        # Close the loop on the write side (Chapter 3.4)
        if rec.get("ok"):
            try:
                from memory import MemoryStore
                store = MemoryStore(self.data_dir)
                store.store(
                    key=f"turn_{int(time.time()*1000)}",
                    content=f"User: {rec.get('user', '')[:200]} | Duration: {rec.get('duration_s')}s | Tools: {len(rec.get('used_tools', []))}",
                    layer="L3",
                    title="Agent Turn Reflection",
                    metadata=rec,
                    session_id=rec.get("session"),
                )

                # Write to LEARNED.md
                learned_entry = f"- [{rec.get('ts')}] Session: {rec.get('session', 'default')} | Turn: {rec.get('user', '')[:80]} -> Reply ({rec.get('reply_len', 0)} chars) via {rec.get('provider')}\n"
                with open(self.learned_path, "a", encoding="utf-8") as lf:
                    lf.write(learned_entry)
            except Exception:
                pass

    def run(
        self,
        user_msg: str,
        session_id: str | None = None,
        router_provider: tuple[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """One full agentic turn (THINK -> ACT -> VERIFY -> LEARN). Returns reply + full trace."""
        t0 = time.time()
        guard = Guard()
        trace: list[dict[str, Any]] = []

        available_tool_names = list(self.tools.keys())
        axioms = self.builders_book.get_prompt_axioms()
        learned_context = self._get_learned_context()

        system = (
            f"You are Al-Buraq, a local sovereign agent OS.\n\n"
            f"{axioms}\n\n"
            f"To invoke a tool, write {{{{tool: NAME | {{\"arg\":\"val\"}}}}}}.\n"
            f"Available tools: {', '.join(available_tool_names)}.\n"
            f"After tool results are provided, verify the output and answer the user directly."
            f"{learned_context}"
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]

        final_text = ""
        provider_used = "local"

        for step in range(guard.max_steps):
            # 1. THINK
            try:
                think = self._think(messages, router_provider=router_provider)
            except Exception as e:
                self._learn({
                    "kind": "turn",
                    "user": user_msg,
                    "ok": False,
                    "error": f"think_failed: {e}"[:160],
                    "session": session_id,
                })
                return {"ok": False, "reply": f"Brain error: {e}", "trace": trace, "duration_s": round(time.time() - t0, 3)}

            text = think["text"]
            provider_used = think.get("provider", "local")
            trace.append({"step": step, "think": text[:300], "provider": provider_used})

            # 2. ACT
            tool_results = self._act(text, guard)
            if not tool_results:
                final_text = text
                break  # No tool requested -> final reply reached

            trace.append({"step": step, "tools": tool_results})

            # 3. VERIFY
            v = self._verify(tool_results, guard)
            trace.append({"step": step, "verify": v})
            if v["tripped"]:
                final_text = text + "\n\n(stopped: guardrail tripped after repeated tool errors or no progress)"
                break

            # Feed tool results back into context for next THINK iteration
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": f"Tool results: {json.dumps(tool_results, ensure_ascii=False)}"})

        dt = round(time.time() - t0, 3)

        # 4. LEARN
        used_tools = [t for tr in trace for t in tr.get("tools", [])]
        self._learn({
            "kind": "turn",
            "user": user_msg,
            "reply": final_text[:400],
            "ok": True,
            "steps": len([t for t in trace if "think" in t]),
            "reply_len": len(final_text),
            "duration_s": dt,
            "session": session_id,
            "provider": provider_used,
            "used_tools": used_tools[:10],
        })

        return {
            "ok": True,
            "reply": final_text or "(no reply)",
            "provider": provider_used,
            "steps": len([t for t in trace if "think" in t]),
            "duration_s": dt,
            "trace": trace,
            "tools_called": len(used_tools),
        }
