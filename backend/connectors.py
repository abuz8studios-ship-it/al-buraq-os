"""
AL-BURAQ — MCP Connector Registry (import disabled-by-default, trust-labelled)
=============================================================================
Docker/MCP lane from the harvested strategy. Imports MCP server definitions
(e.g. Claude Desktop config), stores them DISABLED by default with a trust
label, and never auto-launches anything.
"""
from __future__ import annotations
import json
from pathlib import Path

class ConnectorRegistry:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "connectors.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"connectors": []}, indent=2), encoding="utf-8")

    def _load(self):
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception: return {"connectors": []}

    def _save(self, d): self.path.write_text(json.dumps(d, indent=2), encoding="utf-8")

    def list(self):
        return self._load()

    def import_claude_desktop(self, config: dict):
        """Import MCP servers from a Claude Desktop-style config (mcpServers map)."""
        d = self._load()
        existing = {c["name"] for c in d["connectors"]}
        added = 0
        for name, spec in (config.get("mcpServers") or {}).items():
            if name in existing: continue
            d["connectors"].append({
                "name": name, "command": spec.get("command",""),
                "args": spec.get("args",[]), "enabled": False,           # DISABLED by default
                "trust": "unverified", "source": "claude_desktop"})
            added += 1
        self._save(d)
        return {"added": added, "total": len(d["connectors"])}

    def set_enabled(self, name, enabled: bool):
        d = self._load()
        for c in d["connectors"]:
            if c["name"] == name: c["enabled"] = bool(enabled)
        self._save(d); return {"name": name, "enabled": enabled}

    def set_trust(self, name, level: str):
        d = self._load()
        for c in d["connectors"]:
            if c["name"] == name: c["trust"] = level
        self._save(d); return {"name": name, "trust": level}
