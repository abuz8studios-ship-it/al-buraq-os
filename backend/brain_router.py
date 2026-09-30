"""
AL-BURAQ — Brain Router (local floor + optional cloud accelerators)
===================================================================
The embedded local brain is ALWAYS the floor (never dies). The user may add
cloud brains (OpenAI / Anthropic / OpenRouter / Ollama / custom) by key/url.
Routing: explicit choice -> cloud-if-configured-and-healthy -> local embedded.
Cloud keys live in the user data folder only. Local works with zero internet.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_PROVIDERS = {
    "local": {
        "type": "local",
        "url": "http://127.0.0.1:8099",
        "model": "embedded",
        "label": "Embedded (offline, never dies)",
        "enabled": True,
    },
    "openai": {
        "type": "openai",
        "url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "key": "",
        "label": "OpenAI",
        "enabled": True,
    },
    "anthropic": {
        "type": "anthropic",
        "url": "https://api.anthropic.com/v1",
        "model": "claude-3-5-sonnet",
        "key": "",
        "label": "Anthropic",
        "enabled": True,
    },
    "openrouter": {
        "type": "openai",
        "url": "https://openrouter.ai/api/v1",
        "model": "auto",
        "key": "",
        "label": "OpenRouter",
        "enabled": True,
    },
    "ollama": {
        "type": "openai",
        "url": "http://127.0.0.1:11434/v1",
        "model": "llama3.2",
        "key": "",
        "label": "Local Ollama",
        "enabled": True,
    },
}


class BrainRouter:
    def __init__(self, data_dir: Path, local_url: str = "http://127.0.0.1:8099"):
        self.cfg_path = Path(data_dir) / "brains.json"
        self.local_url = local_url.rstrip("/")
        self._ensure_init()

    def _ensure_init(self) -> None:
        if not self.cfg_path.exists():
            cfg = {
                "active": "local",
                "providers": {**DEFAULT_PROVIDERS},
            }
            cfg["providers"]["local"]["url"] = self.local_url
            self._save(cfg)
        else:
            # Sync local_url if changed
            d = self._load()
            if "local" in d.get("providers", {}):
                d["providers"]["local"]["url"] = self.local_url
                self._save(d)

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return {"active": "local", "providers": {**DEFAULT_PROVIDERS}}

    def _save(self, d: dict[str, Any]) -> None:
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg_path.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

    def list(self) -> dict[str, Any]:
        d = self._load()
        out = {"active": d.get("active", "local"), "providers": {}}
        for k, p in d.get("providers", {}).items():
            p_copy = dict(p)
            if p_copy.get("key"):
                p_copy["has_key"] = True
                p_copy["key"] = "***set***"
            else:
                p_copy["has_key"] = False
            out["providers"][k] = p_copy
        return out

    def get_provider(self, name: str) -> dict[str, Any] | None:
        d = self._load()
        return d.get("providers", {}).get(name)

    def set_active(self, name: str) -> dict[str, Any]:
        d = self._load()
        if name in d.get("providers", {}):
            d["active"] = name
            self._save(d)
            return {"ok": True, "active": name}
        return {"ok": False, "error": f"unknown provider '{name}'"}

    def set_key(self, name: str, key: str) -> dict[str, Any]:
        d = self._load()
        if name in d.get("providers", {}):
            d["providers"][name]["key"] = key.strip()
            self._save(d)
            return {"ok": True, "provider": name, "has_key": bool(key.strip())}
        return {"ok": False, "error": f"unknown provider '{name}'"}

    def update_provider(self, name: str, spec: dict[str, Any]) -> dict[str, Any]:
        d = self._load()
        provs = d.setdefault("providers", {})
        if name not in provs:
            provs[name] = {"type": "openai", "url": "", "model": "default", "label": name, "key": "", "enabled": True}

        for k in ("url", "model", "label", "type", "enabled"):
            if k in spec:
                provs[name][k] = spec[k]
        if "key" in spec:
            provs[name]["key"] = spec["key"].strip()

        self._save(d)
        return {"ok": True, "provider": name, "spec": provs[name]}

    def remove_provider(self, name: str) -> dict[str, Any]:
        if name == "local":
            return {"ok": False, "error": "cannot remove embedded local provider"}
        d = self._load()
        if name in d.get("providers", {}):
            del d["providers"][name]
            if d.get("active") == name:
                d["active"] = "local"
            self._save(d)
            return {"ok": True, "removed": name}
        return {"ok": False, "error": f"unknown provider '{name}'"}

    def probe(self, name: str) -> dict[str, Any]:
        """Probe provider reachability."""
        d = self._load()
        prov = d.get("providers", {}).get(name)
        if not prov:
            return {"ok": False, "error": f"unknown provider '{name}'"}

        url = prov.get("url", "").rstrip("/")
        if not url:
            return {"ok": False, "error": "no URL configured"}

        if prov.get("type") == "local":
            up = self._local_up()
            return {"ok": up, "provider": name, "reachable": up, "url": url}

        # Cloud provider probe
        headers = {"User-Agent": "AlBuraq-OS/0.1"}
        if prov.get("type") == "openai" and prov.get("key"):
            headers["Authorization"] = f"Bearer {prov['key']}"
        elif prov.get("type") == "anthropic" and prov.get("key"):
            headers["x-api-key"] = prov["key"]
            headers["anthropic-version"] = "2023-06-01"

        probe_url = url + ("/models" if url.endswith("/v1") else "/v1/models") if prov.get("type") == "openai" else url
        try:
            req = urllib.request.Request(probe_url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as r:
                return {"ok": r.status < 400, "status": r.status, "provider": name, "reachable": True}
        except urllib.error.HTTPError as e:
            # 401/403 means reachable but auth error, 200/404 means reachable
            reachable = e.code in (401, 403, 400, 404, 405)
            return {"ok": False, "status": e.code, "error": str(e), "reachable": reachable, "provider": name}
        except Exception as e:
            return {"ok": False, "error": str(e), "reachable": False, "provider": name}

    def _local_up(self) -> bool:
        try:
            with urllib.request.urlopen(self.local_url + "/health", timeout=1.5) as r:
                return r.status == 200
        except Exception:
            pass
        try:
            with urllib.request.urlopen(self.local_url + "/v1/models", timeout=1.5) as r:
                return r.status == 200
        except Exception:
            return False

    def resolve(self) -> tuple[str, dict[str, Any]]:
        """
        Which provider to actually use right now.
        Local floor never fails over to nothing.
        Cascade: Active -> Cloud (if valid key) -> Local -> Local floor spec.
        """
        d = self._load()
        active = d.get("active", "local")
        provs = d.get("providers", {})
        prov = provs.get(active, {})

        # If cloud provider chosen but has no key, cascade to local
        if prov.get("type") in ("openai", "anthropic") and not prov.get("key"):
            return "local", provs.get("local", DEFAULT_PROVIDERS["local"])

        # If local is selected, return local (supervisor handles starting)
        if active == "local":
            return "local", provs.get("local", DEFAULT_PROVIDERS["local"])

        return active, prov
