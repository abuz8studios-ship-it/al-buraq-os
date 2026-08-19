# AL_BURAQ — Harvest Report (read-only study of existing builds)
**Date:** 2026-06-07 · **Author:** Qadir/Cowork
**Method:** Read-only study of the strongest existing builds. NOTHING modified. This folder (E:\ABU\AL_BURAQ) is the ONLY write target. We build NEW here, learning from — not touching — the existing work.

---

## SOURCES STUDIED (all left untouched)
| Source | What it gave us |
|---|---|
| `ABUZ8_OS_DIST` (30GB) | The strategic blueprint + release/legal/ISO pipeline + 3-brain shelf |
| `ABUZ8_OS` (v1.0.0 installers) | Honest DEMO_READINESS_MATRIX (28/43 real) — the anti-fake-green truth source |
| `QADIR_CORE` | The REAL agentic loop + self-learning + self-upgrade machinery (ran today 2026-06-07) |

---

## HARVEST 1 — The Strategic Blueprint (from ABUZ8_OS_DIST/AGENTIC_SWISS_ARMY_STRATEGY.md)
Position: **local-first desktop agent OS** that always boots its own embedded brain, probes the device, imports MCP connectors, routes to local/cloud/Docker/external frameworks.
Competitor-lane migration targets to ADOPT:
- OpenAI Agents SDK → run traces, skill cards, patch review, sandbox profiles
- MS Agent Framework → workflow YAML, typed tasks, approval gates
- LangGraph → **persistent mission graph, checkpoint/resume, human-in-the-loop**
- CrewAI → ready-made business crews (website, content, sales, CRM, support)
- Docker MCP → connector import with trust labels + isolated launch
- OpenHands → workspace sandbox, tests-before-apply, code mission mode
**Non-negotiable promise:** always a useful local brain; frameworks optional, never required for first launch.

## HARVEST 2 — The Honesty Discipline (from ABUZ8_OS/DEMO_READINESS_MATRIX.md)
The model for our truth-gate. Real failure patterns to AVOID:
- "Connect-brain pill" showed green but didn't re-point chat (CONN vs AGENTS were separate objects) → **wire the actual path, test round-trip not just /health**
- No watchdog → killed server stayed dead → **build real self-heal**
- Memory 3D used 58-entry seeded sample, not live data → **bind to live or show honest empty**
- install.ps1 "survives reboot" only true AFTER install → **don't overclaim**
Rule adopted: a feature is WORKING only if proven real end-to-end, adversarially.

## HARVEST 3 — The Agentic Loop (from QADIR_CORE/brains/agent/loop.py — v2, "engine-agnostic")
**THINK → ACT → VERIFY → LEARN.** Itself derived from Hermes (MIT) + OpenClaw (MIT) + Claude Agent SDK.
- THINK: assemble context, route to best brain
- ACT: execute tools with alias resolution + error capture
- VERIFY: check results, detect loops, validate output
- LEARN: record experiences/behavior deltas (Jiminy reflector)
- Error recovery: classified errors + recovery hints (retry/rotate/fallback/compress), jittered exponential backoff, fallback cascade (router→ollama native→prompt), tool guardrails (duplicate/failure-threshold/no-progress detection)
- **No hardcoded brain** — uses whatever's loaded or QADIR_MODEL; never force-loads. Default = OPEN.

## HARVEST 4 — The Self-Learning / Self-Upgrade Engine (QADIR_CORE) — RAN TODAY
Two real, scheduled, idempotent loops (183 real log cycles in self_learning_log.jsonl):
1. **Skill self-improvement** (`brains/agent/self_learning.py` G15): HARVEST tool history → PROPOSE skills (n-gram detect) → INGEST YAML to skills/proposed → EVALUATE (score+promote or prune) → feedback to neural router. Turns repeated behavior into curated, scored skills.
2. **Model self-training** (`core/self_learning_loop.py`): signal.jsonl → eval suite → regression detector (rolling mean vs baseline) → **LoRA finetune trigger** when threshold crossed. Safety: never blocks serving, writes audit receipts, cost-gated, idempotent, detects regression AND saturation, max-trigger/day cap.
3. **Eval loop** (`skills/engine/eval_loop.py`): runs proposed skills against eval suite, auto-promote ≥ threshold, auto-prune failures, writes signals to router.

---

## WHAT AL_BURAQ WILL BE (the apex synthesis)
A NEW build in E:\ABU\AL_BURAQ that combines the best of all three:
- **Boot:** LM-Studio-style one-click → cinematic splash (ComfyUI) → first-run permission + folder-pick → provision → wake brain → cinematic OS (the 3 wired UIs).
- **Brain:** engine-agnostic 3-tier shelf (Spark 1.2B / Forge 8B / Titan 27B-deferred), llama.cpp CPU-safe, never force-load.
- **Agentic loop:** THINK→ACT→VERIFY→LEARN with the Hermes error-recovery + guardrails.
- **Self-learning:** the HARVEST→PROPOSE→INGEST→EVALUATE skill loop + the signal→eval→regression→LoRA self-upgrade loop, both safety-gated.
- **Mission graph:** durable, resumable, human-approval (LangGraph-style).
- **Connectors:** MCP import, trust-labelled, disabled by default.
- **Honesty gate:** the adversarial readiness-matrix discipline — nothing claimed unless proven real.

## RULES CARRIED FORWARD
- Build ONLY in E:\ABU\AL_BURAQ. Read-only on all existing builds. Do not touch the other ~30 OS/agent folders.
- No selling until boot + brain + each claimed capability proven real.
- Reuse code by COPYING into AL_BURAQ (with attribution), never editing the source trees.
