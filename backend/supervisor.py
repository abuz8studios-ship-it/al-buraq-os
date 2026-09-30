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

import os
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any


class BrainSupervisor:
    def __init__(self, brain_dir: Path, port: int = 8099, ctx: int = 4096):
        self.brain_dir = Path(brain_dir)
        self.port = port
        self.ctx = ctx
        self.proc: subprocess.Popen[bytes] | None = None
        self.alive = False
        self.restarts = 0
        self.active_model: str | None = None  # explicit pack override (filename in brain_dir)
        self.last_start = 0.0
        self._stop = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _exe(self) -> Path | str | None:
        for n in ("llama-server.exe", "llama-server"):
            p = self.brain_dir / n
            if p.exists() and os.access(p, os.X_OK | os.R_OK):
                return p
            # check system PATH
            which = shutil.which(n)
            if which:
                return Path(which)
        return None

    def _model(self) -> Path | None:
        if self.active_model:
            p = self.brain_dir / self.active_model
            if p.exists():
                return p
        if self.brain_dir.exists():
            g = sorted(self.brain_dir.glob("*.gguf"))
            if g:
                return g[0]
        return None

    def list_packs(self) -> list[dict[str, Any]]:
        cur = self._model()
        if not self.brain_dir.exists():
            return []
        packs = []
        for p in sorted(self.brain_dir.glob("*.gguf")):
            try:
                size_gb = round(p.stat().st_size / 1e9, 2)
            except Exception:
                size_gb = 0.0
            packs.append({
                "file": p.name,
                "size_gb": size_gb,
                "active": (cur is not None and p.name == cur.name),
            })
        return packs

    def activate(self, filename: str) -> dict[str, Any]:
        p = self.brain_dir / filename
        if not p.exists():
            return {"ok": False, "error": f"pack not found: {filename}"}
        with self._lock:
            self.active_model = filename
            # kill current engine; watchdog respawns with the new model
            try:
                if self.proc and self.proc.poll() is None:
                    self.proc.terminate()
            except Exception:
                pass
            self.proc = None
            self.alive = False
        return {"ok": True, "activated": filename}

    def _healthy(self) -> bool:
        for path in ("/health", "/v1/models"):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=1.5) as r:
                    if r.status == 200:
                        return True
            except Exception:
                pass
        return False

    def _spawn(self) -> bool:
        exe, model = self._exe(), self._model()
        if not exe or not model:
            return False

        kwargs: dict[str, Any] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            self.proc = subprocess.Popen(
                [
                    str(exe),
                    "-m", str(model),
                    "--host", "127.0.0.1",
                    "--port", str(self.port),
                    "-c", str(self.ctx),
                    "--jinja",
                ],
                **kwargs,
            )
            self.last_start = time.time()
            return True
        except Exception:
            self.proc = None
            return False

    def _loop(self) -> None:
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
            # is our process dead or never started?
            if self.proc is None or self.proc.poll() is not None:
                if self._spawn():
                    self.restarts += 1
                    time.sleep(min(backoff, 30))
                    backoff = min(backoff * 2, 30)
                else:
                    # no engine or model present; keep checking periodically
                    time.sleep(5)
            else:
                time.sleep(2)  # process up but not answering yet (loading weights)

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop = False
            self._thread = threading.Thread(target=self._loop, daemon=True, name="brain-supervisor")
            self._thread.start()

    def stop(self) -> None:
        self._stop = True
        with self._lock:
            try:
                if self.proc and self.proc.poll() is None:
                    self.proc.terminate()
                    self.proc.wait(timeout=3)
            except Exception:
                pass
            self.alive = False

    def status(self) -> dict[str, Any]:
        cur_m = self._model()
        return {
            "alive": self.alive,
            "port": self.port,
            "restarts": self.restarts,
            "engine_present": self._exe() is not None,
            "model_present": cur_m is not None,
            "active_model": cur_m.name if cur_m else None,
        }
