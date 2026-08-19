"""
AL-BURAQ — Never-Die Brain Supervisor
======================================
Keeps the embedded local brain (llama-server) ALWAYS ON.
Watchdog: if the engine dies, restart it. Exponential backoff, max retries reset
on healthy uptime. The embedded brain is the floor that never goes down — cloud
brains are optional accelerators layered on top via the router.

Runs in a daemon thread inside the backend; never blocks serving.
"""
from __future__ import annotations
import os, subprocess, threading, time, urllib.request
from pathlib import Path

class BrainSupervisor:
    def __init__(self, brain_dir: Path, port: int = 8099, ctx: int = 4096):
        self.brain_dir = Path(brain_dir)
        self.port = port
        self.ctx = ctx
        self.proc = None
        self.alive = False
        self.restarts = 0
        self.active_model = None  # explicit pack override (filename in brain_dir)
        self.last_start = 0
        self._stop = False
        self._thread = None

    def _exe(self):
        for n in ("llama-server.exe", "llama-server"):
            p = self.brain_dir / n
            if p.exists(): return p
        return None

    def _model(self):
        if self.active_model:
            p = self.brain_dir / self.active_model
            if p.exists(): return p
        g = sorted(self.brain_dir.glob("*.gguf"))
        return g[0] if g else None

    def list_packs(self):
        cur = self._model()
        return [{"file": p.name, "size_gb": round(p.stat().st_size/1e9, 2),
                 "active": (cur is not None and p.name == cur.name)}
                for p in sorted(self.brain_dir.glob("*.gguf"))]

    def activate(self, filename: str):
        p = self.brain_dir / filename
        if not p.exists(): return {"error": "pack not found: " + filename}
        self.active_model = filename
        # kill current engine; watchdog respawns with the new model
        try:
            if self.proc: self.proc.terminate()
        except Exception: pass
        self.proc = None
        return {"activated": filename}

    def _healthy(self) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def _spawn(self):
        exe, model = self._exe(), self._model()
        if not exe or not model:
            return False
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        self.proc = subprocess.Popen(
            [str(exe), "-m", str(model), "--host", "127.0.0.1",
             "--port", str(self.port), "-c", str(self.ctx), "--jinja"],
            creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.last_start = time.time()
        return True

    def _loop(self):
        backoff = 2
        while not self._stop:
            if self._healthy():
                self.alive = True
                if time.time() - self.last_start > 60:
                    backoff = 2  # healthy for a minute -> reset backoff
                time.sleep(5)
                continue
            # not healthy
            self.alive = False
            # is our process dead?
            if self.proc is None or self.proc.poll() is not None:
                if self._spawn():
                    self.restarts += 1
                    time.sleep(min(backoff, 30))
                    backoff = min(backoff * 2, 30)
                else:
                    time.sleep(10)  # no engine/model present; keep checking (honest: brain absent)
            else:
                time.sleep(3)  # process up but not answering yet (still loading)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True
        try:
            if self.proc: self.proc.terminate()
        except Exception:
            pass

    def status(self):
        return {"alive": self.alive, "port": self.port, "restarts": self.restarts,
                "engine_present": self._exe() is not None, "model_present": self._model() is not None}
