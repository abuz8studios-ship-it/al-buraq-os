"""
AL-BURAQ Launcher / Provisioner (LM-Studio pattern)
====================================================
First run: ask where to provision -> create data folder (survives app deletion).
Every run: ensure brain present (fat: already bundled | lite: fetch) ->
start engine (llama-server) -> start backend -> health-gate -> open shell.

Honest: never claims a brain works until /health passes. Deleting the app
leaves the chosen data folder intact.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent      # AL_BURAQ/ (the app)
CFG = APP_DIR / "launcher" / "provision.json"
BRAIN_PORT = 8099
BACKEND_PORT = 8930

def _say(m: str) -> None:
    print("[Al-Buraq] " + m, flush=True)

def choose_data_dir() -> Path:
    """First-run: ask user where to provision (per Ahmad). Falls back to LOCALAPPDATA / ~/.alburaq."""
    if CFG.exists():
        try:
            d = Path(json.loads(CFG.read_text(encoding="utf-8"))["data_dir"])
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            pass

    default = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".alburaq"))) / "AlBuraq"
    try:
        # GUI folder picker if available; else prompt; else default
        import tkinter as tk
        from tkinter import filedialog, messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Al-Buraq", "Choose where Al-Buraq stores its brain and data.\nThis folder stays even if you delete the app.")
        picked = filedialog.askdirectory(title="Al-Buraq data folder")
        root.destroy()
        d = (Path(picked) / "AlBuraq") if picked else default
    except Exception:
        try:
            ans = input("Data folder [%s]: " % default).strip()
            d = Path(ans) if ans else default
        except Exception:
            d = default

    d.mkdir(parents=True, exist_ok=True)
    try:
        CFG.parent.mkdir(parents=True, exist_ok=True)
        CFG.write_text(json.dumps({"data_dir": str(d)}, indent=2), encoding="utf-8")
    except Exception:
        pass
    _say("Provisioned data folder: " + str(d))
    return d

def ensure_brain(data_dir: Path) -> Path | None:
    """Fat edition: brain ships in APP_DIR/brain. Lite: fetch into data_dir/brain."""
    for src in [APP_DIR / "brain", data_dir / "brain"]:
        if src.exists():
            ggufs = list(src.glob("*.gguf"))
            if ggufs:
                return ggufs[0]
    _say("No brain pack found. (Lite edition will point to " + str(data_dir / "brain") + ")")
    return None

def _port_up(port: int, path: str = "/health", timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False

def start_engine(brain_exe: Path | str, model: Path):
    if _port_up(BRAIN_PORT, "/health"):
        _say("Engine already up.")
        return None
    _say("Starting brain engine...")
    kwargs = {}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(
        [
            str(brain_exe),
            "-m", str(model),
            "--host", "127.0.0.1",
            "--port", str(BRAIN_PORT),
            "-c", "4096",
            "--jinja",
        ],
        **kwargs,
    )

def start_backend(data_dir: Path):
    _say("Starting backend...")
    py = sys.executable
    return subprocess.Popen([
        py,
        str(APP_DIR / "backend" / "server.py"),
        "--port", str(BACKEND_PORT),
        "--data-dir", str(data_dir),
        "--brain-port", str(BRAIN_PORT),
    ])

def health_gate(timeout: float = 60) -> bool:
    _say("Waiting for systems...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_up(BACKEND_PORT, "/health"):
            _say("Backend live.")
            return True
        time.sleep(0.7)
    _say("Backend did not come up in time.")
    return False

def main():
    _say("Al-Buraq booting (sovereign, local-first).")
    data = choose_data_dir()

    brain_exe = None
    for n in ("llama-server.exe", "llama-server"):
        p = APP_DIR / "brain" / n
        if p.exists():
            brain_exe = p
            break
        w = shutil.which(n)
        if w:
            brain_exe = Path(w)
            break

    model = ensure_brain(data)
    engine = None
    if model and brain_exe:
        engine = start_engine(brain_exe, model)
    else:
        _say("Engine/model missing — backend will run in sovereign offline mode (honest).")

    backend = start_backend(data)
    if health_gate():
        url = "http://127.0.0.1:%d/app/boot.html" % BACKEND_PORT
        _say("Al-Buraq is live at " + url + " — close this window to stop.")
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        backend.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in (engine, backend):
            try:
                if p:
                    p.terminate()
            except Exception:
                pass
        _say("Stopped. Your data folder remains: " + str(data))

if __name__ == "__main__":
    main()
