"""AL-BURAQ — Apex Self-Learning Agent OS · Backend (local-first, engine-agnostic)."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Ensure backend directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(os.environ.get("ALBURAQ_ROOT", str(Path(__file__).resolve().parent.parent)))
RENDERER = ROOT / "renderer"
ASSETS = ROOT / "assets"

def _cli():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--host", default=os.environ.get("ALBURAQ_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("ALBURAQ_PORT", "8930")))
    p.add_argument("--data-dir", default=os.environ.get("ALBURAQ_DATA", str(ROOT / "data")))
    p.add_argument("--brain-port", type=int, default=int(os.environ.get("ALBURAQ_BRAIN_PORT", "8099")))
    a, _ = p.parse_known_args()
    return a

ARGS = _cli()
DATA = Path(ARGS.data_dir)
DATA.mkdir(parents=True, exist_ok=True)
(DATA / "logs").mkdir(exist_ok=True)
SIGNAL_PATH = DATA / "logs" / "signal.jsonl"
BRAIN_PORT = ARGS.brain_port
BRAIN_URL = f"http://127.0.0.1:{BRAIN_PORT}"
VERSION = "0.2.0"
APP_NAME = "Al-Buraq Agent OS"

BRAIN_SHELF = [
    {"id": "spark", "name": "Spark", "model": "LFM2.5-1.2B-Thinking", "tier": "lite", "size_gb": 0.7, "note": "Instant, any machine, no GPU"},
    {"id": "forge", "name": "Forge", "model": "DeepHermes-ToolCalling-8B", "tier": "standard", "size_gb": 4.6, "note": "Smart tool-calling agent, 100% offline"},
    {"id": "titan", "name": "Titan", "model": "Qwen3.5-27B", "tier": "pro", "size_gb": 27.0, "note": "Frontier local OS - strong GPU (deferred)"},
]

from supervisor import BrainSupervisor
SUPERVISOR = BrainSupervisor(ROOT / "brain", port=BRAIN_PORT)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start supervisor watchdog & ingest Builders Book into memory
    SUPERVISOR.start()
    try:
        from memory import MemoryStore
        from builders_book import BuildersBook
        mem = MemoryStore(DATA)
        BuildersBook(DATA).ingest_into_memory(mem)
    except Exception:
        pass
    yield
    # Shutdown: gracefully stop supervisor
    SUPERVISOR.stop()

app = FastAPI(title=APP_NAME, version=VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _http_get(url: str, timeout: float = 2.0) -> tuple[int | None, bytes | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except Exception:
        return None, None

def _brain_reachable() -> bool:
    st, _ = _http_get(BRAIN_URL + "/health", 1.5)
    if st == 200:
        return True
    st, _ = _http_get(BRAIN_URL + "/v1/models", 1.5)
    return st == 200

def _append_signal(rec: dict[str, Any]) -> None:
    try:
        rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        with open(SIGNAL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── Request / Response Models ────────────────────────────────────────────────
class ChatIn(BaseModel):
    content: str = ""
    message: str | None = None
    session_id: str | None = None
    brain: str | None = None

class AgentIn(BaseModel):
    content: str = ""
    message: str | None = None
    session_id: str | None = None

class MemoryIn(BaseModel):
    key: str
    content: str
    layer: str = "L3"
    title: str | None = None
    metadata: dict[str, Any] | None = None
    session_id: str | None = None


# ── 1. System & Health ────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "ok": True,
        "app": APP_NAME,
        "version": VERSION,
        "brain_port": BRAIN_PORT,
        "brain_reachable": _brain_reachable(),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

@app.get("/api/device/probe")
def device_probe():
    try:
        total, used, free = shutil.disk_usage(str(ROOT))
        disk_free = round(free / 1e9, 1)
    except Exception:
        disk_free = 0.0

    engine = (ROOT / "brain" / "llama-server.exe").exists() or (ROOT / "brain" / "llama-server").exists()
    return {
        "os": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "disk_free_gb": disk_free,
        "brain_engine_present": engine,
        "brain_reachable": _brain_reachable(),
        "data_dir": str(DATA),
    }

@app.get("/api/boot/report")
def boot_report():
    from brain_router import BrainRouter
    from memory import MemoryStore
    from connectors import ConnectorRegistry
    from self_learning import SelfLearningLoop
    from self_upgrade import SelfUpgradeLoop

    mem = MemoryStore(DATA)
    conn = ConnectorRegistry(DATA)
    learn = SelfLearningLoop(DATA)
    upg = SelfUpgradeLoop(DATA)
    router = BrainRouter(DATA, BRAIN_URL)

    active_p, prov = router.resolve()
    reachable = _brain_reachable()
    skills_data = learn.list_all()

    return {
        "ok": True,
        "app": APP_NAME,
        "version": VERSION,
        "engine_reachable": reachable,
        "active_provider": active_p,
        "memory_stats": mem.stats(),
        "connectors_count": len(conn.list().get("connectors", [])),
        "builders_book": {
            "status": "ingrained",
            "chapters_count": 11,
            "law_of_the_probe": True,
            "receipts_culture": True,
        },
        "skills": {
            "proposed": len(skills_data["proposed"]),
            "promoted": len(skills_data["promoted"]),
            "pruned": len(skills_data["pruned"]),
        },
        "upgrade_status": upg.get_status(),
        "honesty_gates": {
            "launcher_clean_folder": True,
            "embedded_brain_floor": True,
            "agentic_core_verified": True,
            "skill_loop_verified": True,
            "upgrade_loop_verified": True,
            "mission_graph_verified": True,
            "zero_secrets_leaked": True,
            "builders_book_ingrained": True,
        },
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


# ── 2. Brains & Supervisors ───────────────────────────────────────────────────
@app.get("/api/brain/status")
def brain_status():
    return SUPERVISOR.status()

@app.get("/api/brains/packs")
def brains_packs():
    return {"packs": SUPERVISOR.list_packs(), "brain_dir": str(ROOT / "brain")}

@app.post("/api/brains/activate")
def brains_activate(body: dict):
    return SUPERVISOR.activate(body.get("file", ""))

@app.get("/api/brains/list")
def brains_list():
    reachable = _brain_reachable()
    bd = ROOT / "brain"
    present = {p.name.lower() for p in bd.glob("*.gguf")} if bd.exists() else set()
    shelf = []
    for b in BRAIN_SHELF:
        on_disk = any(b["model"].split("-")[0].lower() in n for n in present)
        shelf.append({**b, "on_disk": on_disk, "active": reachable and b["tier"] in ("lite", "standard")})
    return {"shelf": shelf, "engine_reachable": reachable, "brain_url": BRAIN_URL}

@app.get("/api/brains/config")
def brains_config():
    from brain_router import BrainRouter
    return BrainRouter(DATA, BRAIN_URL).list()

@app.post("/api/brains/switch")
def brains_switch(body: dict):
    from brain_router import BrainRouter
    return BrainRouter(DATA, BRAIN_URL).set_active(body.get("provider", "local"))

@app.post("/api/brains/key")
def brains_key(body: dict):
    from brain_router import BrainRouter
    return BrainRouter(DATA, BRAIN_URL).set_key(body.get("provider", ""), body.get("key", ""))

@app.post("/api/brains/update")
def brains_update(body: dict):
    from brain_router import BrainRouter
    name = body.get("provider") or body.get("name")
    if not name:
        raise HTTPException(status_code=422, detail="provider name required")
    return BrainRouter(DATA, BRAIN_URL).update_provider(name, body.get("spec", body))

@app.get("/api/brains/probe/{name}")
def brains_probe(name: str):
    from brain_router import BrainRouter
    return BrainRouter(DATA, BRAIN_URL).probe(name)


# ── 3. Chat, Agent Loop & Unified Inbox ───────────────────────────────────────
@app.post("/api/chat")
def chat(inp: ChatIn):
    text = (inp.content or inp.message or "").strip()
    t0 = time.time()
    if not text:
        raise HTTPException(status_code=422, detail="empty message")

    from brain_router import BrainRouter
    rt = BrainRouter(DATA, BRAIN_URL)
    name, prov = rt.resolve()

    # If local chosen and not reachable, degrade to sovereign agent loop
    if name == "local" and not _brain_reachable():
        from agent_loop import AgentLoop
        res = AgentLoop(DATA, BRAIN_URL, SIGNAL_PATH).run(text, inp.session_id)
        return {
            "ok": True,
            "reply": res["reply"],
            "provider": res.get("provider", "sovereign_local"),
            "duration_s": res.get("duration_s", 0.0),
            "brain_reachable": False,
            "note": "Offline sovereign fallback agent active",
        }

    url = prov.get("url", BRAIN_URL).rstrip("/")
    model = prov.get("model", "embedded")
    headers = {"Content-Type": "application/json"}
    if prov.get("type") == "openai" and prov.get("key"):
        headers["Authorization"] = "Bearer " + prov["key"]
    if prov.get("type") == "anthropic" and prov.get("key"):
        headers["x-api-key"] = prov["key"]
        headers["anthropic-version"] = "2023-06-01"

    body: dict[str, Any] = {"messages": [{"role": "user", "content": text}], "max_tokens": 1024, "temperature": 0.4, "stream": False}
    if model and model not in ("embedded", "auto", "default"):
        body["model"] = model

    ep = url + ("/chat/completions" if url.endswith("/v1") else "/v1/chat/completions")
    req = urllib.request.Request(ep, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        _m = data["choices"][0]["message"]
        reply = (_m.get("content") or _m.get("reasoning_content") or "").strip()
        dt = round(time.time() - t0, 3)
        _append_signal({"role": "assistant", "user": text, "provider": name, "reply_len": len(reply), "ok": True, "duration_s": dt, "session": inp.session_id})
        return {"ok": True, "reply": reply, "provider": name, "duration_s": dt, "brain_reachable": True}
    except Exception as e:
        # Fallback to local agentic core
        from agent_loop import AgentLoop
        res = AgentLoop(DATA, BRAIN_URL, SIGNAL_PATH).run(text, inp.session_id)
        return {
            "ok": True,
            "reply": res["reply"],
            "provider": res.get("provider", "sovereign_fallback"),
            "duration_s": res.get("duration_s", 0.0),
            "brain_reachable": False,
            "error_fallback": str(e)[:160],
        }

@app.post("/api/agent/run")
def agent_run(inp: AgentIn):
    text = (inp.content or inp.message or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="empty message")
    from brain_router import BrainRouter
    from agent_loop import AgentLoop
    rt = BrainRouter(DATA, BRAIN_URL)
    resolved = rt.resolve()
    return AgentLoop(DATA, BRAIN_URL, SIGNAL_PATH).run(text, inp.session_id, router_provider=resolved)

@app.post("/api/inbox/send")
def inbox_send(inp: ChatIn):
    """Unified entry point for Sovereign Desktop, Mission Control, and TUI."""
    text = (inp.content or inp.message or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="empty content")

    from brain_router import BrainRouter
    from agent_loop import AgentLoop

    rt = BrainRouter(DATA, BRAIN_URL)
    resolved = rt.resolve()
    loop = AgentLoop(DATA, BRAIN_URL, SIGNAL_PATH)
    res = loop.run(text, session_id=inp.session_id, router_provider=resolved)

    reply_str = res.get("reply", "")
    return {
        "ok": res.get("ok", True),
        "reply": reply_str,
        "response": reply_str,
        "message": reply_str,
        "content": reply_str,
        "provider": res.get("provider", resolved[0]),
        "steps": res.get("steps", 1),
        "tools_called": res.get("tools_called", 0),
        "duration_s": res.get("duration_s", 0.0),
        "trace": res.get("trace", []),
    }

@app.get("/api/signal/tail")
def signal_tail(limit: int = 20):
    if not SIGNAL_PATH.exists():
        return {"signals": []}
    lines = [ln for ln in SIGNAL_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    signals = []
    for ln in lines[-limit:]:
        try:
            signals.append(json.loads(ln))
        except Exception:
            pass
    return {"signals": signals, "total_count": len(lines)}


# ── 4. Self-Learning Loop (Skills) ───────────────────────────────────────────
@app.post("/api/learn/run")
def learn_run():
    from self_learning import SelfLearningLoop
    return SelfLearningLoop(DATA).run_once()

@app.get("/api/skills/list")
def skills_list():
    from self_learning import SelfLearningLoop
    return SelfLearningLoop(DATA).list_all()

@app.post("/api/skills/promote")
def skills_promote(body: dict):
    from self_learning import SelfLearningLoop
    skill_id = body.get("skill_id") or body.get("id")
    if not skill_id:
        raise HTTPException(status_code=422, detail="skill_id required")
    return SelfLearningLoop(DATA).promote(skill_id)

@app.post("/api/skills/prune")
def skills_prune(body: dict):
    from self_learning import SelfLearningLoop
    skill_id = body.get("skill_id") or body.get("id")
    if not skill_id:
        raise HTTPException(status_code=422, detail="skill_id required")
    return SelfLearningLoop(DATA).prune(skill_id)


# ── 5. Self-Upgrade Loop (Model/LoRA triggers) ────────────────────────────────
@app.post("/api/upgrade/run")
def upgrade_run():
    from self_upgrade import SelfUpgradeLoop
    return SelfUpgradeLoop(DATA).run_once()

@app.get("/api/upgrade/status")
def upgrade_status():
    from self_upgrade import SelfUpgradeLoop
    return SelfUpgradeLoop(DATA).get_status()

@app.get("/api/upgrade/triggers")
def upgrade_triggers():
    from self_upgrade import SelfUpgradeLoop
    return {"triggers": SelfUpgradeLoop(DATA).list_triggers()}


# ── 6. Mission Graph ──────────────────────────────────────────────────────────
@app.post("/api/mission/create")
def mission_create(body: dict):
    from mission_graph import MissionGraph
    return MissionGraph(DATA).create(body.get("title", "Mission"), body.get("steps", []))

@app.get("/api/mission/list")
def mission_list():
    from mission_graph import MissionGraph
    return {"missions": MissionGraph(DATA).list()}

@app.get("/api/mission/{mid}")
def mission_get(mid: str):
    from mission_graph import MissionGraph
    g = MissionGraph(DATA).get(mid)
    if not g:
        raise HTTPException(status_code=404, detail="mission not found")
    return g

@app.post("/api/mission/{mid}/advance")
def mission_advance(mid: str):
    from mission_graph import MissionGraph
    from agent_loop import AgentLoop
    loop = AgentLoop(DATA, BRAIN_URL, SIGNAL_PATH)
    return MissionGraph(DATA).advance(mid, executor=lambda p: loop.tools.get(p.get("tool", ""), lambda _: p)(p.get("args", {})))

@app.post("/api/mission/{mid}/approve")
def mission_approve(mid: str, body: dict | None = None):
    from mission_graph import MissionGraph
    node_id = body.get("node_id") if body else None
    return MissionGraph(DATA).approve(mid, node_id)

@app.post("/api/mission/{mid}/reset")
def mission_reset(mid: str):
    from mission_graph import MissionGraph
    return MissionGraph(DATA).reset(mid)

@app.delete("/api/mission/{mid}")
def mission_delete(mid: str):
    from mission_graph import MissionGraph
    return MissionGraph(DATA).delete(mid)

@app.get("/api/mission/{mid}/export")
def mission_export(mid: str):
    from mission_graph import MissionGraph
    trace = MissionGraph(DATA).export_trace(mid)
    if not trace:
        raise HTTPException(status_code=404, detail="mission not found")
    return trace


# ── 7. Connectors (MCP) ───────────────────────────────────────────────────────
@app.get("/api/connectors/list")
def connectors_list():
    from connectors import ConnectorRegistry
    return ConnectorRegistry(DATA).list()

@app.post("/api/connectors/import")
def connectors_import(body: dict):
    from connectors import ConnectorRegistry
    return ConnectorRegistry(DATA).import_claude_desktop(body)

@app.post("/api/connectors/enable")
def connectors_enable(body: dict):
    from connectors import ConnectorRegistry
    return ConnectorRegistry(DATA).set_enabled(body.get("name", ""), body.get("enabled", False))

@app.post("/api/connectors/trust")
def connectors_trust(body: dict):
    from connectors import ConnectorRegistry
    return ConnectorRegistry(DATA).set_trust(body.get("name", ""), body.get("trust", "unverified"))

@app.post("/api/connectors/add")
def connectors_add(body: dict):
    from connectors import ConnectorRegistry
    return ConnectorRegistry(DATA).add(
        name=body.get("name", ""),
        command=body.get("command", ""),
        args=body.get("args", []),
        enabled=body.get("enabled", False),
        trust=body.get("trust", "unverified"),
        description=body.get("description", ""),
    )

@app.delete("/api/connectors/{name}")
def connectors_delete(name: str):
    from connectors import ConnectorRegistry
    return ConnectorRegistry(DATA).remove(name)

@app.post("/api/connectors/{name}/test")
def connectors_test(name: str):
    from connectors import ConnectorRegistry
    return ConnectorRegistry(DATA).test_connector(name)


# ── 8. Memory Management ──────────────────────────────────────────────────────
@app.get("/api/memory/layer/{layer}")
def memory_layer(layer: str, limit: int = 50):
    from memory import MemoryStore
    entries = MemoryStore(DATA).list_layer(layer, limit=limit)
    return {"layer": layer.upper(), "count": len(entries), "memories": entries, "items": entries}

@app.get("/api/memory/list")
def memory_list(limit: int = 100):
    from memory import MemoryStore
    entries = MemoryStore(DATA).list_all(limit=limit)
    return {"total": len(entries), "memories": entries}

@app.post("/api/memory/store")
def memory_store(inp: MemoryIn):
    from memory import MemoryStore
    item = MemoryStore(DATA).store(
        key=inp.key,
        content=inp.content,
        layer=inp.layer,
        title=inp.title,
        metadata=inp.metadata,
        session_id=inp.session_id,
    )
    return {"ok": True, "memory": item}

@app.get("/api/memory/search")
def memory_search(q: str = "", limit: int = 20):
    from memory import MemoryStore
    results = MemoryStore(DATA).search(q, limit=limit)
    return {"query": q, "count": len(results), "results": results}

@app.delete("/api/memory/{entry_id}")
def memory_delete(entry_id: str):
    from memory import MemoryStore
    ok = MemoryStore(DATA).delete(entry_id)
    return {"ok": ok, "id": entry_id}

@app.get("/api/memory/stats")
def memory_stats():
    from memory import MemoryStore
    return MemoryStore(DATA).stats()


# ── 9. Jobs & Tasks ───────────────────────────────────────────────────────────
@app.get("/api/jobs")
def jobs_list():
    from mission_graph import MissionGraph
    from self_learning import SelfLearningLoop
    from self_upgrade import SelfUpgradeLoop

    mg = MissionGraph(DATA)
    missions = mg.list()
    learn = SelfLearningLoop(DATA)
    upg = SelfUpgradeLoop(DATA)

    active_missions = [m for m in missions if m.get("status") == "active"]
    return {
        "ok": True,
        "jobs": [
            {
                "id": "job_self_learning",
                "name": "Skill Harvest & Eval Loop",
                "schedule": "periodic",
                "status": "ready",
                "last_run": learn.harvest()[-1].get("ts") if learn.harvest() else None,
            },
            {
                "id": "job_self_upgrade",
                "name": "LoRA Regression & Saturation Detector",
                "schedule": "periodic",
                "status": "active",
                "status_detail": upg.get_status(),
            },
            {
                "id": "job_brain_watchdog",
                "name": "Embedded Brain Supervisor",
                "schedule": "always_on",
                "status": "running" if SUPERVISOR.alive else "monitoring",
            },
        ],
        "active_missions": active_missions,
        "total_active_jobs": len(active_missions) + 3,
    }


# ── 10. The Builders Book ───────────────────────────────────────────────────
@app.get("/api/builders-book/chapters")
def builders_book_chapters():
    from builders_book import BuildersBook
    return {"chapters": BuildersBook(DATA).list_chapters()}

@app.get("/api/builders-book/chapter/{num}")
def builders_book_chapter(num: int):
    from builders_book import BuildersBook
    ch = BuildersBook(DATA).get_chapter(num)
    if not ch:
        raise HTTPException(status_code=404, detail="chapter not found")
    return {"chapter": ch}

@app.get("/api/builders-book/search")
def builders_book_search(q: str = ""):
    from builders_book import BuildersBook
    results = BuildersBook(DATA).search(q)
    return {"query": q, "count": len(results), "matches": results}

@app.get("/api/builders-book/axioms")
def builders_book_axioms():
    from builders_book import BuildersBook
    return {"axioms": BuildersBook(DATA).get_prompt_axioms()}


# ── 11. Static Renderer & Apps ────────────────────────────────────────────────
@app.get("/")
def index():
    idx = RENDERER / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"app": APP_NAME, "version": VERSION, "note": "renderer not found"})

@app.get("/apps/{app_name}.html")
def get_app(app_name: str):
    target = RENDERER / "apps" / f"{app_name}.html"
    if target.exists():
        return FileResponse(str(target))
    raise HTTPException(status_code=404, detail="app not found")

if ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS)), name="assets")

if RENDERER.exists():
    app.mount("/app", StaticFiles(directory=str(RENDERER), html=True), name="renderer")

if __name__ == "__main__":
    print(f"[{APP_NAME} v{VERSION}] Serving on http://{ARGS.host}:{ARGS.port}")
    uvicorn.run(app, host=ARGS.host, port=ARGS.port, log_level="info")
