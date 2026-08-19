"""
AL-BURAQ — One-Click Bootstrap (the EXE entry point)
=====================================================
PyInstaller freezes THIS + all payload (backend, renderer, brain engine, gguf,
assets) into a single .exe. On launch:
  1. Show a console banner (onboarding).
  2. First run: ask where to install (folder pick) -> extract payload ONCE.
     (Payload = PyInstaller's _MEIPASS bundle, copied into the data folder so it
      persists after the app is deleted — the LM-Studio pattern.)
  3. Start the backend (which starts the never-die brain supervisor).
  4. Health-gate, then open the cinematic boot in the browser.
  5. Keep running; closing the window stops the OS (data folder stays).

The user moves NOTHING. One file. Double-click. It comes alive.
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, time, urllib.request, webbrowser
from pathlib import Path

APP_NAME = "Al-Buraq Agent OS"
EDITION = os.environ.get("ALBURAQ_EDITION", "Spark")
BACKEND_PORT = 8930
BRAIN_PORT = 8099

def _meipass() -> Path:
    """Where PyInstaller unpacked the bundled payload at runtime."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))

def _exe_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()

def banner():
    print("=" * 64)
    print("   " + APP_NAME + "  -  " + EDITION + " edition")
    print("   Sovereign, local-first, always-on. Your brain never dies.")
    print("   First run asks where to install. Then it just works.")
    print("=" * 64, flush=True)

def choose_install_dir() -> Path:
    env = os.environ.get("ALBURAQ_INSTALL")
    if env:
        d = Path(env); d.mkdir(parents=True, exist_ok=True); return d
    cfg = (_exe_dir() / "albuq_install.json")
    if not cfg.exists() and (Path.cwd()/"albuq_install.json").exists(): cfg = Path.cwd()/"albuq_install.json"
    if cfg.exists():
        try:
            d = Path(json.loads(cfg.read_text())["dir"]); 
            if d.exists(): return d
        except Exception: pass
    default = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ABUZ8" / ("AlBuraq-" + EDITION)
    chosen = None
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
        root = tk.Tk(); root.withdraw()
        messagebox.showinfo(APP_NAME, "Choose where to install " + APP_NAME + " (" + EDITION + ").\n"
                            "The brain and your data live here and stay even if you delete the app.")
        picked = filedialog.askdirectory(title="Install folder for " + APP_NAME)
        root.destroy()
        chosen = (Path(picked) / ("AlBuraq-" + EDITION)) if picked else default
    except Exception:
        try:
            a = input("Install folder [%s]: " % default).strip()
            chosen = Path(a) if a else default
        except Exception:
            chosen = default
    chosen.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"dir": str(chosen)}, indent=2))
    return chosen

def extract_payload(dest: Path):
    """Copy bundled payload (backend, renderer, brain, assets) into dest ONCE."""
    src = _meipass() / "payload"
    if not src.exists() and (Path.cwd() / "payload").exists():
        src = Path.cwd() / "payload"
    if not src.exists():
        src = Path(__file__).resolve().parent.parent
    marker = dest / ".extracted"
    if marker.exists():
        print("[Al-Buraq] Already installed at " + str(dest), flush=True); return
    print("[Al-Buraq] Installing to " + str(dest) + " (one-time)...", flush=True)
    for sub in ("backend", "renderer", "assets", "brain"):
        s = src / sub
        if s.exists():
            shutil.copytree(s, dest / sub, dirs_exist_ok=True)
            print("  + " + sub, flush=True)
    (dest / "data").mkdir(exist_ok=True)
    marker.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
    print("[Al-Buraq] Install complete.", flush=True)

def _port_up(port, path="/health"):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=2) as r:
            return r.status == 200
    except Exception:
        return False

def start_backend(install: Path):
    py = sys.executable
    server = install / "backend" / "server.py"
    # When frozen, sys.executable is the exe; run the server in-process instead.
    if getattr(sys, "frozen", False):
        # launch a child of ourselves in "server mode" via env flag
        env = dict(os.environ, ALBURAQ_DATA=str(install / "data"),
                   ALBURAQ_PORT=str(BACKEND_PORT), ALBURAQ_BRAIN_PORT=str(BRAIN_PORT),
                   ALBURAQ_ROOT=str(install), ALBURAQ_SERVER_MODE="1")
        return subprocess.Popen([sys.executable], env=env)
    return subprocess.Popen([py, str(server), "--port", str(BACKEND_PORT),
                             "--data-dir", str(install / "data"), "--brain-port", str(BRAIN_PORT)])

def health_gate(timeout=90):
    print("[Al-Buraq] Waking the brain (always-on supervisor)...", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_up(BACKEND_PORT):
            return True
        time.sleep(0.7)
    return False

def main():
    banner()
    install = choose_install_dir()
    extract_payload(install)
    backend = start_backend(install)
    if health_gate():
        url = "http://127.0.0.1:%d/app/boot.html" % BACKEND_PORT
        print("[Al-Buraq] LIVE -> " + url, flush=True)
        try: webbrowser.open(url)
        except Exception: pass
        print("[Al-Buraq] Running. Close this window to stop. Data stays at: " + str(install), flush=True)
    else:
        print("[Al-Buraq] Backend did not start in time. See data/logs.", flush=True)
    try:
        backend.wait()
    except KeyboardInterrupt:
        pass
    finally:
        try: backend.terminate()
        except Exception: pass

if __name__ == "__main__":
    # server-mode: when the frozen exe re-launches itself to BE the backend
    if os.environ.get("ALBURAQ_SERVER_MODE") == "1":
        root = Path(os.environ["ALBURAQ_ROOT"])
        sys.path.insert(0, str(root / "backend"))
        os.chdir(str(root))
        import uvicorn
        import server as srv
        uvicorn.run(srv.app, host="127.0.0.1", port=int(os.environ.get("ALBURAQ_PORT", "8930")), log_level="info")
    else:
        main()
