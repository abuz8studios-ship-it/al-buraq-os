# AL-BURAQ — Apex Self-Learning Agent OS · Design Spec v1
**Date:** 2026-06-07 · **Author:** Qadir/Cowork · **Status:** AWAITING AHMAD APPROVAL
**Build target:** `E:\ABU\AL_BURAQ` ONLY. Read-only on all existing builds; reuse by COPY + attribution, never edit source trees.
**Hard rule:** Nothing is "working" or sellable until proven real end-to-end (adversarial, no fake-green). No selling language until the honesty gates pass.

---

## 0. ONE-LINE
Al-Buraq is a local-first, self-learning, self-upgrading desktop agent OS: one click → cinematic boot → an embedded brain wakes → a THINK·ACT·VERIFY·LEARN loop that turns its own usage into new skills and, when it measurably regresses, retrains itself — all offline, all sovereign, all auditable.

## 1. PRINCIPLES (non-negotiable)
1. **Always a useful local brain.** Frameworks/cloud are optional, never required for first launch.
2. **Engine-agnostic.** Never force-load a model. Use what's chosen/loaded; default state = OPEN.
3. **Honesty gate.** A capability ships only if an adversarial pass proves it real. Otherwise it shows an honest "not available" state. No fabricated metrics, ever.
4. **Self-improvement is safety-gated.** Learning/retraining never blocks serving, always writes audit receipts, is cost-capped and idempotent.
5. **Data sovereignty.** All memory/logs/workspaces live in a product-owned folder the user chooses; deleting the app leaves the data folder intact.
6. **Visual law.** Light+dark Islamic-blue cinematic (lapis #0a1628 + gold #c9a84c + turquoise #1a8a7a), seizure-safe.

## 2. SYSTEM ARCHITECTURE (layers)
```
┌──────────────────────────────────────────────────────────────┐
│  LAUNCHER (one-click .exe)                                     │
│   cinematic splash → first-run permission + folder pick →     │
│   provision (fat: unpack brain | lite: fetch brain) →         │
│   health-gate (engine + backend) → open cinematic OS shell    │
├──────────────────────────────────────────────────────────────┤
│  SHELL (renderer) — the 3 wired cinematic UIs                 │
│   Sovereign Desktop · Mission Control · Masterful TUI         │
│   all bound live to the backend; honest empty states          │
├──────────────────────────────────────────────────────────────┤
│  BACKEND (FastAPI, local)  :PORT                              │
│   /api/chat  /api/device/probe  /api/brains/*  /api/mission/* │
│   /api/skills/*  /api/learn/*  /api/connectors/*  /health     │
├──────────────────────────────────────────────────────────────┤
│  AGENTIC CORE — THINK → ACT → VERIFY → LEARN                  │
│   brain router · tool executor+guardrails · error recovery   │
│   mission graph (durable/resumable/approval)                 │
├──────────────────────────────────────────────────────────────┤
│  SELF-IMPROVEMENT (background, scheduled, gated)             │
│   skill loop: HARVEST→PROPOSE→INGEST→EVALUATE→promote/prune  │
│   upgrade loop: signal→eval→regression→LoRA trigger+receipt  │
├──────────────────────────────────────────────────────────────┤
│  BRAIN SHELF (engine-agnostic, llama.cpp CPU-safe)           │
│   Spark LFM2.5-1.2B · Forge DeepHermes-8B · Titan 27B(defer) │
├──────────────────────────────────────────────────────────────┤
│  DATA FOLDER (user-chosen, survives app deletion)            │
│   brain ggufs · state.sqlite · minds · skills · logs · evals │
└──────────────────────────────────────────────────────────────┘
```

## 3. THE AGENTIC LOOP (harvested from QADIR_CORE loop.py v2)
Every turn runs four pillars:
- **THINK** — assemble context (recent turns + relevant memory + device capability), route to best available brain (router → ollama-native → prompt-based fallback cascade).
- **ACT** — execute tool calls; alias-resolve tool names; capture errors structurally.
- **VERIFY** — inspect tool results for errors; detect loops (duplicate-call / no-progress / failure-threshold guardrails); validate output before returning.
- **LEARN** — append the experience to `signal.jsonl` and a reflection (behavior delta) to memory. This is the data both self-improvement loops consume.
Error recovery: classified errors → recovery hints (retry / rotate / fallback / compress), jittered exponential backoff. Never crash the turn; degrade and report.

## 4. SELF-LEARNING (skill loop — harvested from self_learning.py G15)
Runs on a schedule, in the background, never blocking chat:
1. **HARVEST** — pull recent tool/turn history (loop buffer → sqlite → in-memory fallback).
2. **PROPOSE** — n-gram/pattern detect repeated successful behavior → draft a skill (YAML) via SkillCreator.
3. **INGEST** — write to `skills/proposed/` (disabled by default) via SkillCurator.
4. **EVALUATE** — EvalLoop scores each proposed skill on quality/reliability/cost against the eval suite; **auto-promote** ≥ threshold, **auto-prune** persistent failures; write signal back to the router so it prefers promoted skills.
Every cycle appends one line to `self_learning_log.jsonl` (audit trail).

## 5. SELF-UPGRADING (model loop — harvested from self_learning_loop.py)
1. Each turn auto-logs to `signal.jsonl`.
2. Background cycle: when ≥ MIN_NEW_SIGNAL fresh turns, run the eval suite → compute rolling success.
3. **Regression detector:** if rolling success drops ≥ REGRESSION_THRESH vs baseline → fire a LoRA finetune trigger. **Saturation detector:** if no training in N days → fire one refresh.
4. Every trigger writes a **receipt** (`training/triggers/<ts>.json`) explaining why — human-auditable.
5. Safety: cost-gated (local-GPU default, $0 cap), idempotent (no double-fire), max-trigger/day cap, never runs during active serving load.
*(Note: actual LoRA training needs the GPU box; on a buyer's laptop this loop runs in "propose-only/receipt-only" mode — it records what it WOULD train, honestly, without claiming it trained.)*

## 6. MISSION GRAPH (harvested from strategy — LangGraph lane)
- Tasks = nodes; tool calls + outputs = edges; persisted to sqlite.
- Pause/resume; human-approval checkpoints before any side-effectful or destructive action.
- Exportable run traces for review (the "tracing/skill-card" lane from OpenAI SDK).

## 7. CONNECTORS (harvested from strategy — Docker/MCP lane)
- Import MCP connectors (Claude Desktop config, Docker MCP when present).
- Imported **disabled by default**; trust labels; secrets audit; per-connector test button; isolated launch.

## 8. BOOT / DELIVERY (the LM-Studio pattern, per Ahmad)
- **Fat exe (USB/offline):** contains the brain; click → unpack into chosen folder → boot. Zero internet.
- **Lite exe (download):** small; first run asks permission, downloads brain into chosen folder, boots. Internet first-run only.
- **First run** asks the user where to provision the data folder. Deleting the app leaves it.
- Editions = brain drop-in: **Spark (1.2B, ~1.5GB)**, **Forge (8B, ~5.5GB)**. Titan (27B) deferred (needs engine-streams-model architecture; documented, not promised).

## 9. CINEMATIC (ComfyUI — splash + theme, per Ahmad)
- **Boot splash:** short cinematic "powering on" sequence generated in local ComfyUI (:8188), played at launch.
- **Theme set:** wallpapers, panel backgrounds, login art, icon set — cohesive cinematic skin wired into the 3 UIs.
- Generated at build time, baked in. NOT generated on the buyer's machine.

## 10. HONESTY GATES (must all pass before any claim/price)
- [ ] Launcher boots from a CLEAN folder (not the dev tree).
- [ ] Embedded brain answers a prompt offline (proven, like the :8099 test already passed).
- [ ] Agentic loop completes THINK·ACT·VERIFY·LEARN on a real task (logged to signal.jsonl).
- [ ] Skill loop promotes/prunes at least one real proposed skill (logged).
- [ ] Upgrade loop writes a real regression-eval cycle + receipt (no fake training claim).
- [ ] Mission graph persists + resumes a paused run.
- [ ] Zero secrets / zero internal persona names in customer-facing surface.
- [ ] Every UI capability maps to a backend action; unmapped = honest "not available".
- [ ] First-run with no config degrades gracefully.

## 11. BUILD PHASES (after approval — each phase verified before next)
- **P0 Skeleton:** AL_BURAQ folder structure + copy the wired shell (3 UIs) + a minimal FastAPI backend with /health, /api/device/probe, /api/brains/list, /api/chat. Prove: boots, brain answers. 
- **P1 Agentic core:** copy+adapt loop.py (THINK·ACT·VERIFY·LEARN) + guardrails + error recovery. Prove: a real multi-step task with a tool call + signal.jsonl entry.
- **P2 Self-learning:** copy+adapt the skill loop + eval loop. Prove: one skill proposed→evaluated→promoted/pruned, logged.
- **P3 Self-upgrade:** copy+adapt the signal→eval→regression loop in propose/receipt mode. Prove: a real cycle + receipt.
- **P4 Mission graph + connectors:** durable graph, approval gates; MCP import disabled-by-default.
- **P5 Launcher + provisioning:** one-click, folder-pick, fat/lite, health-gate.
- **P6 Cinematic:** ComfyUI splash + theme, wired in.
- **P7 Package + honesty gates:** Spark + Forge twins, run the full gate checklist, write proof to MEMORY.md.

## 12. WHAT THIS IS NOT (scope guards)
- Not a rebuild of ABUZ8_OS/ABUZ8_OS_DIST/QADIR_CORE — those stay untouched; we learn from them.
- Not a cloud product — local-first; cloud is optional routing only.
- Not sellable until Section 10 is all green.

---
**APPROVE and I start P0 (skeleton + prove boot/brain) in E:\ABU\AL_BURAQ. Each phase proven before the next. No selling until the gates are green.**
