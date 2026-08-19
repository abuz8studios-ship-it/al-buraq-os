"""AL-BURAQ — Apex Self-Learning Agent OS · Backend (local-first, engine-agnostic)."""
from __future__ import annotations
import argparse, json, os, platform, shutil, sys, time, urllib.request, urllib.error
from pathlib import Path
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(os.environ.get("ALBURAQ_ROOT", str(Path(__file__).resolve().parent.parent)))
RENDERER = ROOT / "renderer"

def _cli():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--port", type=int, default=int(os.environ.get("ALBURAQ_PORT", "8930")))
    p.add_argument("--data-dir", default=os.environ.get("ALBURAQ_DATA", str(ROOT / "data")))
    p.add_argument("--brain-port", type=int, default=int(os.environ.get("ALBURAQ_BRAIN_PORT", "8099")))
    a, _ = p.parse_known_args(); return a

ARGS = _cli()
DATA = Path(ARGS.data_dir); DATA.mkdir(parents=True, exist_ok=True)
(DATA / "logs").mkdir(exist_ok=True)
SIGNAL_PATH = DATA / "logs" / "signal.jsonl"
BRAIN_PORT = ARGS.brain_port
BRAIN_URL = "http://127.0.0.1:" + str(BRAIN_PORT)
VERSION = "0.1.0"; APP_NAME = "Al-Buraq Agent OS"

BRAIN_SHELF = [
  {"id":"spark","name":"Spark","model":"LFM2.5-1.2B-Thinking","tier":"lite","size_gb":0.7,"note":"Instant, any machine, no GPU"},
  {"id":"forge","name":"Forge","model":"DeepHermes-ToolCalling-8B","tier":"standard","size_gb":4.6,"note":"Smart tool-calling agent, 100% offline"},
  {"id":"titan","name":"Titan","model":"Qwen3.5-27B","tier":"pro","size_gb":27.0,"note":"Frontier local OS - strong GPU (deferred)"},
]

def _http_get(url, timeout=2.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r: return r.status, r.read()
    except Exception: return None, None

def _brain_reachable():
    st,_ = _http_get(BRAIN_URL+"/health",1.5)
    if st==200: return True
    st,_ = _http_get(BRAIN_URL+"/v1/models",1.5)
    return st==200

def _append_signal(rec):
    try:
        rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        with open(SIGNAL_PATH,"a",encoding="utf-8") as f: f.write(json.dumps(rec,ensure_ascii=False)+"\n")
    except Exception: pass

app = FastAPI(title=APP_NAME, version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── never-die brain supervisor (always-on, auto-restart) ──
from supervisor import BrainSupervisor
SUPERVISOR = BrainSupervisor(ROOT / "brain", port=BRAIN_PORT)
@app.on_event("startup")
def _boot_supervisor():
    SUPERVISOR.start()

@app.get("/api/brain/status")
def brain_status():
    return SUPERVISOR.status()

@app.get("/api/brains/packs")
def brains_packs():
    return {"packs": SUPERVISOR.list_packs(), "brain_dir": str(ROOT / "brain")}

@app.post("/api/brains/activate")
def brains_activate(body: dict):
    return SUPERVISOR.activate(body.get("file",""))


class ChatIn(BaseModel):
    content: str = ""; message: str | None = None; session_id: str | None = None; brain: str | None = None
class AgentIn(BaseModel):
    content: str = ""; message: str | None = None; session_id: str | None = None

@app.get("/health")
def health():
    return {"ok":True,"app":APP_NAME,"version":VERSION,"brain_port":BRAIN_PORT,
            "brain_reachable":_brain_reachable(),"ts":time.strftime("%Y-%m-%dT%H:%M:%S%z")}

@app.get("/api/device/probe")
def device_probe():
    total,used,free = shutil.disk_usage(str(ROOT))
    engine = (ROOT/"brain"/"llama-server.exe").exists() or (ROOT/"brain"/"llama-server").exists()
    return {"os":platform.system(),"release":platform.release(),"machine":platform.machine(),
            "python":platform.python_version(),"cpu_count":os.cpu_count(),
            "disk_free_gb":round(free/1e9,1),"brain_engine_present":engine,
            "brain_reachable":_brain_reachable(),"data_dir":str(DATA)}

@app.get("/api/brains/list")
def brains_list():
    reachable = _brain_reachable()
    bd = ROOT/"brain"
    present = {p.name.lower() for p in bd.glob("*.gguf")} if bd.exists() else set()
    shelf=[]
    for b in BRAIN_SHELF:
        on_disk = any(b["model"].split("-")[0].lower() in n for n in present)
        shelf.append({**b,"on_disk":on_disk,"active":reachable and b["tier"] in ("lite","standard")})
    return {"shelf":shelf,"engine_reachable":reachable,"brain_url":BRAIN_URL}

@app.post("/api/chat")
def chat(inp: ChatIn):
    text = (inp.content or inp.message or "").strip(); t0=time.time()
    if not text: raise HTTPException(status_code=422, detail="empty message")
    from brain_router import BrainRouter
    rt = BrainRouter(DATA, BRAIN_URL)
    name, prov = rt.resolve()
    url = prov.get("url", BRAIN_URL).rstrip("/")
    model = prov.get("model", "embedded")
    headers = {"Content-Type":"application/json"}
    if prov.get("type")=="openai" and prov.get("key"): headers["Authorization"]="Bearer "+prov["key"]
    if prov.get("type")=="anthropic" and prov.get("key"):
        headers["x-api-key"]=prov["key"]; headers["anthropic-version"]="2023-06-01"
    # local floor: if local chosen and not up, supervisor is reviving it -> honest message
    if name=="local" and not _brain_reachable():
        _append_signal({"role":"user","content":text,"ok":False,"error":"brain_starting","session":inp.session_id})
        return JSONResponse({"ok":False,"reply":"Embedded brain is starting (never-die supervisor reviving it). Try again in a few seconds.","brain_reachable":False})
    body={"messages":[{"role":"user","content":text}],"max_tokens":1024,"temperature":0.4,"stream":False}
    if model and model not in ("embedded","auto"): body["model"]=model
    ep = url + ("/chat/completions" if url.endswith("/v1") else "/v1/chat/completions")
    req = urllib.request.Request(ep, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req,timeout=120) as r: data=json.loads(r.read())
        _m = data["choices"][0]["message"]
        reply = (_m.get("content") or _m.get("reasoning_content") or "").strip(); dt=round(time.time()-t0,2)
        _append_signal({"role":"assistant","user":text,"provider":name,"reply_len":len(reply),"ok":True,"duration_s":dt,"session":inp.session_id})
        return {"ok":True,"reply":reply,"provider":name,"duration_s":dt,"brain_reachable":True}
    except Exception as e:
        _append_signal({"role":"assistant","user":text,"provider":name,"ok":False,"error":str(e)[:200],"session":inp.session_id})
        return JSONResponse({"ok":False,"reply":"Brain error ("+name+"): "+str(e),"brain_reachable":True})

@app.post("/api/agent/run")
def agent_run(inp: AgentIn):
    text = (inp.content or inp.message or "").strip()
    if not text: raise HTTPException(status_code=422, detail="empty message")
    if not _brain_reachable():
        return JSONResponse({"ok":False,"reply":"Brain offline on :"+str(BRAIN_PORT)+".","brain_reachable":False})
    from agent_loop import AgentLoop
    return AgentLoop(BRAIN_URL, SIGNAL_PATH).run(text, inp.session_id)

@app.post("/api/learn/run")
def learn_run():
    from self_learning import SelfLearningLoop
    return SelfLearningLoop(DATA).run_once()

@app.get("/api/skills/list")
def skills_list():
    def _read(d):
        out=[]; p=DATA/"skills"/d
        if p.exists():
            for f in p.glob("*.json"):
                try: out.append(json.loads(f.read_text(encoding="utf-8")))
                except Exception: pass
        return out
    return {"proposed":_read("proposed"),"promoted":_read("promoted")}

@app.post("/api/upgrade/run")
def upgrade_run():
    from self_upgrade import SelfUpgradeLoop
    return SelfUpgradeLoop(DATA).run_once()

@app.post("/api/mission/create")
def mission_create(body: dict):
    from mission_graph import MissionGraph
    return MissionGraph(DATA).create(body.get("title","Mission"), body.get("steps",[]))

@app.get("/api/mission/list")
def mission_list():
    from mission_graph import MissionGraph
    return {"missions": MissionGraph(DATA).list()}

@app.get("/api/mission/{mid}")
def mission_get(mid: str):
    from mission_graph import MissionGraph
    g = MissionGraph(DATA).get(mid)
    if not g: raise HTTPException(status_code=404, detail="not found")
    return g

@app.post("/api/mission/{mid}/advance")
def mission_advance(mid: str):
    from mission_graph import MissionGraph
    return MissionGraph(DATA).advance(mid)

@app.post("/api/mission/{mid}/approve")
def mission_approve(mid: str, body: dict):
    from mission_graph import MissionGraph
    return MissionGraph(DATA).approve(mid, body.get("node_id"))

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
    return ConnectorRegistry(DATA).set_enabled(body.get("name"), body.get("enabled", False))

@app.get("/api/brains/config")
def brains_config():
    from brain_router import BrainRouter
    return BrainRouter(DATA, BRAIN_URL).list()

@app.post("/api/brains/switch")
def brains_switch(body: dict):
    from brain_router import BrainRouter
    return BrainRouter(DATA, BRAIN_URL).set_active(body.get("provider","local"))

@app.post("/api/brains/key")
def brains_key(body: dict):
    from brain_router import BrainRouter
    return BrainRouter(DATA, BRAIN_URL).set_key(body.get("provider"), body.get("key",""))

@app.get("/")
def index():
    idx = RENDERER/"index.html"
    if idx.exists(): return FileResponse(str(idx))
    return JSONResponse({"app":APP_NAME,"version":VERSION,"note":"renderer not found"})

if RENDERER.exists():
    app.mount("/app", StaticFiles(directory=str(RENDERER), html=True), name="renderer")

if __name__ == "__main__":
    print("["+APP_NAME+" v"+VERSION+"] :"+str(ARGS.port))
    uvicorn.run(app, host="127.0.0.1", port=ARGS.port, log_level="info")
