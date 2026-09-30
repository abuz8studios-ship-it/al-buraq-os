"""
AL-BURAQ — The Builders Book (Zero to Hero in Agentic Systems)
==============================================================
Ingrained canonical wisdom by Ahmad Odeh & Qadir · ABUZ8 LLC.
Every rule and pattern extracted from 9 months of real builds (2025-12 → 2026-08).

Provides:
  - Structured chapter & rule catalog
  - Dynamic semantic/keyword search with sanitized SQLite queries
  - System prompt axiomatic injection
  - Ingestion into Layered Memory (L4 Vault / L3 Principles)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

CHAPTERS = [
    {
        "number": 1,
        "title": "Foundations: The Law of the Probe",
        "summary": "Nothing is true until a probe says so. Verify from disk, not memory or docs. One canonical trunk.",
        "rules": [
            "Nothing is true until a probe says so.",
            "A 'finished' feature = the probe in the right column (curl route, run exe, hash artifact).",
            "Verify from disk, not from memory or docs. Trust Get-ChildItem/ls over stale goal documents.",
            "One canonical trunk, edited in place (ABUZ8_OS_DIST); avoid copy-fork sprawl.",
            "A new scoreboard, worktree, sibling folder, or audit HTML is a defect, not progress.",
            "Cheatcode: Before any state-changing command, ask 'what evidence supports THIS action?'",
            "Thinking models with low max_tokens finish early with length; allocate adequate token budget.",
        ],
    },
    {
        "number": 2,
        "title": "Serving Local AI Brains (llama.cpp mastery)",
        "summary": "Hard-won recipes for serving 27-30B multimodal brains on consumer GPUs.",
        "rules": [
            "-c is TOTAL context, not per-slot (-c 262144 --parallel 2 = 131k per agent).",
            "Pin the GPU explicitly (--device CUDA1) or llama.cpp defaults to GPU 0 and spills into other workloads.",
            "VRAM-ceiling spill is silent: keep >=2 GB VRAM headroom always to prevent 12 tok/s system memory spill.",
            "KV-cache quantization is model-specific: needle-probe after changing --cache-type-k/v.",
            "llama-server --list-devices FIRST: cublasLt64_13.dll must match cublas64_13 version exactly.",
            "Speculative decoding fails silently: check accept statistics, do not assume flags worked.",
            "Vision towers survive abliteration: borrow mmproj-*.gguf from sibling repos.",
            "Brain tournament: benchmark GSM8K/MMLU/tools at temp 0 before crowning models (UD-Q4_K_XL).",
            "Pin embedding models on GPU with OLLAMA_KEEP_ALIVE=-1 (50 ms vs 15 s recall).",
        ],
    },
    {
        "number": 3,
        "title": "Building Agents That Actually Execute",
        "summary": "Native tool calling, parameter aliases, FTS sanitization, socket naming, closed-loop learning.",
        "rules": [
            "Thinking models must use native tool-call format, not free-text JSON.",
            "Gate on the right field: reliable signal is agent_steps, not documented tool_call.",
            "Give tools argument aliases (filename vs path, text vs content); accept synonyms because models are sloppy.",
            "Strip unsupportedToolSchemaKeywords (pattern, format, minLength, maxItems) for local small models.",
            "Avoid envelope traps: always extract explicit keys and wrap display in safeText helpers.",
            "Sanitize/truncate FTS queries before hitting SQLite FTS5 (raw quotes crash MATCH).",
            "Never taskkill /f state databases: clean shutdown prevents recurring database corruption.",
            "One shared model socket id ('abuz8-brain'): swap underlying models with zero bot config changes.",
            "Closed-loop learning: corrections -> LEARNED.md -> injected into every system prompt.",
        ],
    },
    {
        "number": 4,
        "title": "Desktop Apps (Electron & Tauri)",
        "summary": "Cache busting, packaging huge payloads (>4GB), native modules, and DLL parity.",
        "rules": [
            "Electron cache trap: verify through the window, not curl; use no-store + session.clearCache() + bump APP_VERSION.",
            "NSIS cannot carry >4 GB: 5 GB brains ship as electron-builder --dir + 7z portable archive.",
            "PyInstaller-append is dead for huge payloads: use 7z SFX with bundled install.cmd for persistence.",
            "ELECTRON_RUN_AS_NODE=1 allows installed Electron apps to run node self-upgrade scripts.",
            "Native modules (node-pty) must live outside asar in resources/node_modules.",
            "llama-server.exe and ggml-cuda.dll must be from the exact SAME build or model crashes at warmup.",
            "Run build scripts with pwsh, not powershell 5.1.",
            "Tauri: pip install PyMCubes (not mcubes); use pure-python shims when toolchains fail.",
        ],
    },
    {
        "number": 5,
        "title": "Web Apps & Deploys",
        "summary": "Allowlist drift prevention, rebuild after every change, recipe documentation.",
        "rules": [
            "Deploy allowlists rot: probe that diffs deployed vs source directories.",
            "Rebuild after EVERY change so deployed artifact = HEAD.",
            "The redeploy recipe matters more than the build script: document it on day one.",
            "Email: DNS receive-only domains cannot transmit; verify outbound capability.",
        ],
    },
    {
        "number": 6,
        "title": "Media & Vision Pipelines",
        "summary": "ffmpeg probe, model hash validation, Kokoro TTS, keyframe character consistency, AGPL licensing check.",
        "rules": [
            "First probe of any media pipeline: ffmpeg -version.",
            "ComfyUI: verify model files by hash/behavior, not filename. Junction one model store.",
            "Kinect v2 requires pykinect2 SDK, not DirectShow.",
            "Piper TTS is robotic; Kokoro-82M on GPU delivers 28 human voices at 0.3s. Probe via TTS->ASR round-trip.",
            "Character consistency: keyframe-to-keyframe embedding cosine >= 0.7.",
            "License check BEFORE building on a repo: clean-room AGPL ideas; never fork restricted code.",
        ],
    },
    {
        "number": 7,
        "title": "Ops: Supervisors, Watchdogs, Schedulers",
        "summary": "True process supervision, lock files, log freshness probing, health-based restarts.",
        "rules": [
            "Processes spawned inside a background shell die on exit: use real supervisors and scheduled tasks.",
            "pwsh -WindowStyle Hidden self-duplicates: guard with single-instance lock file.",
            "Supervisors die silently: probe log freshness, keep task scheduler as revive.",
            "Watchdogs checking the wrong port pass forever: grep all watchdogs when moving ports.",
            "Health-based restart beats time-based restart: trigger on failed HTTP probes.",
        ],
    },
    {
        "number": 8,
        "title": "Security & Going Public",
        "summary": "Secrets purging, gitleaks, the Existential Six vulnerabilities, public ship gates.",
        "rules": [
            "Secrets purge: gitleaks scan -> filter-repo -> force-push -> mirror backup first.",
            "Never add a remote to a repo holding credentials (E:\\ABU stays remote-less).",
            "The Existential Six: unsigned self-update RCE, prompt-injection RCE, unjailed fs read, fake revenue, CSRF, plaintext keys.",
            "Ship gates: repo public only after secrets-clean + LICENSE + no >100MB files + signed installers.",
            "Config files ship as config.example.json.",
            "Hardcoded absolute paths are release-blockers; convert all paths to relative or CLI args.",
        ],
    },
    {
        "number": 9,
        "title": "Packaging & Selling (the missing muscle)",
        "summary": "Build -> Probe -> SELL -> Next. Inventory before building; services lead to products.",
        "rules": [
            "The 103-asset lesson: build -> probe -> SELL -> next. The sale is the next unit of work.",
            "Confirm bundle artifact before building (PWA zip vs Electron exe vs Tauri exe vs bootable ISO).",
            "Inventory before you build: don't start from scratch when installers already exist.",
            "Lead with services (builder-for-hire) when audience is cold; product sales is track two.",
            "Sell Early Access to warm buyers before public launch to front-run signing gates.",
        ],
    },
    {
        "number": 10,
        "title": "Working with Claude (the actual cheatcodes)",
        "summary": "Smallest change that turns probe green, read disk first, curl endpoints, persist every turn.",
        "rules": [
            "Smallest change that turns the probe green. Never rebuild a module with a live probe.",
            "Read the code you will touch before editing: one look at disk beats three assumptions.",
            "curl the endpoint before writing UI against it: verify real shape on disk.",
            "Background long jobs; probe short ones inline.",
            "One chat = one ticket to prevent scope creep and forks.",
            "Persist every turn: commit + redeploy + memory note.",
            "When a claim matters, demand its receipt: commit hash, port probe, file hash, measured tok/s.",
            "Name sockets, not implementations ('abuz8-brain' @ :8011).",
            "Child-process env is not your env: strip shadowed keys (ANTHROPIC_API_KEY).",
            "When two systems must merge, GLUE, don't rebuild.",
        ],
    },
    {
        "number": 11,
        "title": "The Meta-Patterns (what to train Jabaar on)",
        "summary": "Avoid the 6 failure patterns; execute the 6 success patterns relentlessly.",
        "rules": [
            "Avoid: Revenue-layer abandonment (rebuilding before selling).",
            "Avoid: Copy-fork sprawl (losing work in sibling copies).",
            "Avoid: Silent-degradation blindness (systems that look alive but fail measured probes).",
            "Avoid: Doc-trust over disk-trust (planning against stale documents).",
            "Avoid: New-scoreboard syndrome (making fresh audits instead of finishing tickets).",
            "Avoid: Iterate-by-copy (versioning in filenames instead of git).",
            "Execute: Probe-first debugging (--list-devices first).",
            "Execute: Measured tournaments (benchmark before crowning).",
            "Execute: In-place revival (fix launchers and configs, don't rewrite).",
            "Execute: Shared-socket architecture (one brain socket, many bots).",
            "Execute: Audit -> Close -> Verify (re-probe until 403 / green).",
            "Execute: Receipts culture (commits, hashes, measured numbers on every claim).",
        ],
    },
]


class BuildersBook:
    def __init__(self, data_dir: Path | str | None = None):
        self.data_dir = Path(data_dir) if data_dir else (ROOT / "data")
        self.doc_path = ROOT / "BUILDERS_BOOK.md"

    def list_chapters(self) -> list[dict[str, Any]]:
        return CHAPTERS

    def get_chapter(self, num: int) -> dict[str, Any] | None:
        for c in CHAPTERS:
            if c["number"] == num:
                return c
        return None

    def search(self, query: str) -> list[dict[str, Any]]:
        q = query.lower().strip()
        if not q:
            return []

        # Check for explicit chapter numbers (e.g. "chapter 1", "ch 1", "chapter 3")
        ch_match = re.search(r"\b(?:chapter|ch)\s*(\d+)\b", q, re.IGNORECASE)
        if ch_match:
            ch_num = int(ch_match.group(1))
            ch = self.get_chapter(ch_num)
            if ch:
                return [{
                    "chapter": ch["number"],
                    "title": ch["title"],
                    "summary": ch["summary"],
                    "matched_rules": ch["rules"],
                }]

        # Tokenize query words
        stopwords = {"the", "of", "in", "and", "a", "an", "to", "for", "is", "on", "that", "this", "it", "with", "look", "up", "builders", "book"}
        words = [w for w in re.findall(r"[a-zA-Z0-9_-]+", q) if w not in stopwords and len(w) > 1]
        if not words:
            words = [w for w in re.findall(r"[a-zA-Z0-9_-]+", q) if len(w) > 1]

        matches = []
        for c in CHAPTERS:
            c_text = f"{c['title']} {c['summary']} {' '.join(c['rules'])}".lower()
            matched_rules = []
            for r in c["rules"]:
                r_low = r.lower()
                if q in r_low or any(w in r_low for w in words):
                    matched_rules.append(r)

            if q in c_text or any(w in c_text for w in words):
                matches.append({
                    "chapter": c["number"],
                    "title": c["title"],
                    "summary": c["summary"],
                    "matched_rules": matched_rules or c["rules"][:2],
                })
        return matches

    def get_prompt_axioms(self) -> str:
        """Condensed high-leverage axioms for system prompt injection."""
        return (
            "THE BUILDERS LAWS (Ahmad Odeh & Qadir · ABUZ8 LLC):\n"
            "1. THE LAW OF THE PROBE: Nothing is true until a probe says so. Verify from disk, not memory or docs.\n"
            "2. RECEIPTS CULTURE: Demand verifiable receipts (measured tok/s, hashes, port probes) on every claim.\n"
            "3. TOLERANT TOOL CALLING: Accept argument synonyms (filename/path, text/content); models are sloppy.\n"
            "4. ONE CANONICAL TRUNK: Edit in place; never spawn copy-fork sprawl.\n"
            "5. SMALLEST CHANGE: Smallest change that turns the probe green. Never rebuild when you can glue.\n"
            "6. CLOSED-LOOP LEARNING: Extract corrections -> write to LEARNED.md -> inject into future turns.\n"
            "7. HONEST GATES: Never claim capability without adversarial end-to-end proof."
        )

    def ingest_into_memory(self, memory_store: Any) -> int:
        """Ingest all 11 chapters into L4 Archive / Vault and L3 Core Principles."""
        count = 0
        for c in CHAPTERS:
            key = f"builders_book_ch{c['number']:02d}"
            content = f"Chapter {c['number']}: {c['title']}\nSummary: {c['summary']}\n\nRules:\n" + "\n".join(f"- {r}" for r in c["rules"])
            memory_store.store(
                key=key,
                content=content,
                layer="L4",
                title=f"The Builders Book — Ch {c['number']}: {c['title']}",
                metadata={"chapter": c["number"], "source": "The Builders Book", "author": "Ahmad Odeh & Qadir"},
            )
            count += 1

        # Also store core axioms in L3 Long-Term Principles
        memory_store.store(
            key="core_builders_axioms",
            content=self.get_prompt_axioms(),
            layer="L3",
            title="The Builders Book — Core Axioms & Operating Laws",
            metadata={"source": "The Builders Book", "author": "Ahmad Odeh & Qadir"},
        )
        count += 1
        return count
