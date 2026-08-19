"""
AL-BURAQ — onedir launcher (instant boot, no re-extract, no corruption)
=======================================================================
The exe lives in a folder beside: backend/ renderer/ assets/ brain/.
It reads them in place, starts the backend in-process, the never-die
supervisor wakes the brain from brain/, and the browser opens.
Nothing extracts. Nothing over 700MB. Copies to USB cleanly. Just works.
"""
import os, sys, threading, time, webbrowser, urllib.request
from pathlib import Path

def base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

BASE = base_dir()
os.environ["ALBURAQ_ROOT"] = str(BASE)

# data dir: prefer beside the exe (portable USB); fall back to LOCALAPPDATA if read-only
data = BASE / "data"
try:
    data.mkdir(exist_ok=True)
    t = data / ".wtest"; t.write_text("x"); t.unlink()
except Exception:
    data = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AlBuraq" / "data"
    data.mkdir(parents=True, exist_ok=True)
os.environ["ALBURAQ_DATA"] = str(data)
os.environ["ALBURAQ_PORT"] = "8930"
os.environ["ALBURAQ_BRAIN_PORT"] = "8099"

sys.path.insert(0, str(BASE / "backend"))

def _open_when_ready():
    for _ in range(180):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8930/health", timeout=2) as r:
                if r.status == 200:
                    webbrowser.open("http://127.0.0.1:8930/app/boot.html"); return
        except Exception:
            pass
        time.sleep(1)

print("=" * 60)
print("  AL-BURAQ AGENT OS  -  starting your sovereign AI...")
print("  A browser window opens in a few seconds. Keep this open.")
print("  Close this window to stop. Your data stays in this folder.")
print("=" * 60, flush=True)
threading.Thread(target=_open_when_ready, daemon=True).start()

import uvicorn
import server  # reads ALBURAQ_ROOT/DATA; supervisor auto-starts the brain
uvicorn.run(server.app, host="127.0.0.1", port=8930, log_level="warning")
