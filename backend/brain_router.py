"""
AL-BURAQ — Brain Router (local floor + optional cloud accelerators)
===================================================================
The embedded local brain is ALWAYS the floor (never dies). The user may add
cloud brains (OpenAI / Anthropic / OpenRouter / any OpenAI-compatible) by key.
Routing: explicit choice -> else cloud-if-configured-and-up -> else local.
Cloud keys live in the user data folder only. Local works with no key, offline.
"""
from __future__ import annotations
import json, urllib.request
from pathlib import Path

class BrainRouter:
    def __init__(self, data_dir: Path, local_url: str):
        self.cfg_path = Path(data_dir) / "brains.json"
        self.local_url = local_url.rstrip("/")
        if not self.cfg_path.exists():
            self.cfg_path.write_text(json.dumps({
                "active": "local",
                "providers": {
                    "local":     {"type": "local", "url": self.local_url, "model": "embedded", "label": "Embedded (offline, never dies)"},
                    "openai":    {"type": "openai", "url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "key": "", "label": "OpenAI"},
                    "anthropic": {"type": "anthropic", "url": "https://api.anthropic.com/v1", "model": "claude-3-5-sonnet", "key": "", "label": "Anthropic"},
                    "openrouter":{"type": "openai", "url": "https://openrouter.ai/api/v1", "model": "auto", "key": "", "label": "OpenRouter"}
                }}, indent=2), encoding="utf-8")

    def _load(self):
        return json.loads(self.cfg_path.read_text(encoding="utf-8"))
    def _save(self, d):
        self.cfg_path.write_text(json.dumps(d, indent=2), encoding="utf-8")

    def list(self):
        d = self._load()
        # mask keys
        for p in d["providers"].values():
            if p.get("key"): p["key"] = "***set***"
        return d

    def set_active(self, name):
        d = self._load()
        if name in d["providers"]:
            d["active"] = name; self._save(d); return {"active": name}
        return {"error": "unknown provider"}

    def set_key(self, name, key):
        d = self._load()
        if name in d["providers"]:
            d["providers"][name]["key"] = key; self._save(d); return {"ok": True, "provider": name}
        return {"error": "unknown provider"}

    def _local_up(self):
        try:
            with urllib.request.urlopen(self.local_url + "/health", timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def resolve(self):
        """Which provider to actually use right now. Local floor never fails over to nothing."""
        d = self._load()
        active = d.get("active", "local")
        prov = d["providers"].get(active, {})
        # cloud chosen but no key -> fall back to local (honest, never dead)
        if prov.get("type") in ("openai", "anthropic") and not prov.get("key"):
            return "local", d["providers"]["local"]
        if active == "local" and not self._local_up():
            return "local", d["providers"]["local"]  # supervisor will revive it
        return active, prov
