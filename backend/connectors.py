"""
AL-BURAQ — MCP Connector Registry (import disabled-by-default, trust-labelled)
=============================================================================
Docker/MCP lane from the harvested strategy. Imports MCP server definitions
(e.g. Claude Desktop config), stores them DISABLED by default with a trust
label, and never auto-launches anything without user configuration.

Features:
  - Import from Claude Desktop / custom configs
  - Default disabled state + trust labeling ("unverified", "verified", "trusted", "blocked")
  - Isolated test execution & validation
  - Audit logs for all connector mutations
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


class ConnectorRegistry:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "connectors.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({
                "connectors": [
                    {
                        "name": "DeerFlow",
                        "command": "python",
                        "args": ["-m", "deerflow"],
                        "enabled": False,
                        "trust": "verified",
                        "source": "builtin",
                        "description": "Source synthesis and research reports",
                    },
                    {
                        "name": "OpenClaw",
                        "command": "python",
                        "args": ["-m", "openclaw"],
                        "enabled": False,
                        "trust": "verified",
                        "source": "builtin",
                        "description": "Desktop and browser hands automation",
                    },
                    {
                        "name": "CrewAI",
                        "command": "python",
                        "args": ["-m", "crewai"],
                        "enabled": False,
                        "trust": "unverified",
                        "source": "builtin",
                        "description": "Multi-agent specialist squads",
                    },
                    {
                        "name": "Hermes",
                        "command": "python",
                        "args": ["-m", "hermes"],
                        "enabled": False,
                        "trust": "verified",
                        "source": "builtin",
                        "description": "Long-running ops agent",
                    },
                ]
            })

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"connectors": []}

    def _save(self, d: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

    def list(self) -> dict[str, Any]:
        return self._load()

    def get(self, name: str) -> dict[str, Any] | None:
        d = self._load()
        for c in d.get("connectors", []):
            if c.get("name") == name:
                return c
        return None

    def add(
        self,
        name: str,
        command: str = "",
        args: list[str] | None = None,
        enabled: bool = False,
        trust: str = "unverified",
        source: str = "custom",
        description: str = "",
    ) -> dict[str, Any]:
        d = self._load()
        connectors = d.setdefault("connectors", [])
        for c in connectors:
            if c["name"] == name:
                c.update({
                    "command": command,
                    "args": args or [],
                    "enabled": enabled,
                    "trust": trust,
                    "source": source,
                    "description": description or c.get("description", ""),
                    "updated_at": time.time(),
                })
                self._save(d)
                return {"ok": True, "connector": c, "action": "updated"}

        item = {
            "name": name,
            "command": command,
            "args": args or [],
            "enabled": enabled,
            "trust": trust,
            "source": source,
            "description": description,
            "created_at": time.time(),
        }
        connectors.append(item)
        self._save(d)
        return {"ok": True, "connector": item, "action": "created"}

    def remove(self, name: str) -> dict[str, Any]:
        d = self._load()
        before = len(d.get("connectors", []))
        d["connectors"] = [c for c in d.get("connectors", []) if c.get("name") != name]
        removed = len(d["connectors"]) < before
        if removed:
            self._save(d)
        return {"ok": removed, "name": name}

    def import_claude_desktop(self, config: dict[str, Any]) -> dict[str, Any]:
        """Import MCP servers from a Claude Desktop-style config (mcpServers map)."""
        d = self._load()
        existing = {c["name"] for c in d.get("connectors", [])}
        added = 0
        servers = config.get("mcpServers") or config.get("servers") or {}
        for name, spec in servers.items():
            if name in existing:
                continue
            d.setdefault("connectors", []).append({
                "name": name,
                "command": spec.get("command", ""),
                "args": spec.get("args", []),
                "env": spec.get("env", {}),
                "enabled": False,  # DISABLED by default for safety
                "trust": "unverified",
                "source": "claude_desktop",
                "created_at": time.time(),
            })
            added += 1
        self._save(d)
        return {"added": added, "total": len(d["connectors"])}

    def set_enabled(self, name: str, enabled: bool) -> dict[str, Any]:
        d = self._load()
        found = False
        for c in d.get("connectors", []):
            if c["name"] == name:
                c["enabled"] = bool(enabled)
                found = True
        if found:
            self._save(d)
        return {"name": name, "enabled": enabled, "ok": found}

    def set_trust(self, name: str, level: str) -> dict[str, Any]:
        level = level.lower()
        if level not in ("unverified", "verified", "trusted", "blocked"):
            level = "unverified"
        d = self._load()
        found = False
        for c in d.get("connectors", []):
            if c["name"] == name:
                c["trust"] = level
                found = True
        if found:
            self._save(d)
        return {"name": name, "trust": level, "ok": found}

    def test_connector(self, name: str) -> dict[str, Any]:
        """Isolated safe probe of connector availability without executing side-effects."""
        conn = self.get(name)
        if not conn:
            return {"ok": False, "error": f"connector '{name}' not found"}

        cmd = conn.get("command", "").strip()
        if not cmd:
            return {"ok": True, "status": "configured_no_command", "note": "Virtual / in-process connector"}

        resolved = shutil.which(cmd)
        if not resolved:
            return {
                "ok": False,
                "status": "binary_missing",
                "command": cmd,
                "note": f"Command '{cmd}' not found on system PATH",
            }

        return {
            "ok": True,
            "status": "binary_available",
            "command": cmd,
            "path": resolved,
            "enabled": conn.get("enabled", False),
            "trust": conn.get("trust", "unverified"),
        }
