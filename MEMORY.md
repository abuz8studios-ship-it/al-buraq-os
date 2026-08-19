# AL-BURAQ — Build Memory & Proof
**Built:** 2026-06-07 (Cowork/Qadir session) · **Location:** E:\ABU\AL_BURAQ (new, isolated)
**Status:** Core OS built end-to-end, ALL 8 honesty gates PASS (verified, not claimed).
**Rule honored:** only E:\ABU\AL_BURAQ was written; all ~30 existing builds read-only.

## WHAT WAS BUILT (apex self-learning agent OS)
| Layer | File | Proven |
|---|---|---|
| Backend (FastAPI, engine-agnostic) | backend/server.py | ✅ boots, all routes 200 |
| Agentic core THINK·ACT·VERIFY·LEARN | backend/agent_loop.py | ✅ multi-step + tool + signal log |
| Self-learning skill loop | backend/self_learning.py | ✅ proposed→evaluated→PROMOTED a real skill |
| Self-upgrade loop (propose/receipt) | backend/self_upgrade.py | ✅ regression/saturation→honest receipt |
| Mission graph (durable/resume/approval) | backend/mission_graph.py | ✅ pauses at approval gate, persists, resumes |
| MCP connectors (disabled-by-default) | backend/connectors.py | ✅ import w/ trust=unverified, enabled=false |
| Launcher (LM-Studio pattern) | launcher/provision.py + Start-AlBuraq.cmd | ✅ folder-pick→provision→health-gate→shell |
| Cinematic boot | renderer/boot.html + assets/splash.png | ✅ real Flux-generated Buraq splash |
| Shell (3 wired UIs) | renderer/index.html + apps/*.html | ✅ wired to backend, scrubbed clean |
| Cinematic assets | assets/splash.png, assets/wallpaper.png | ✅ ComfyUI Flux (live :8188) |

## HONESTY GATE RESULTS (final run, 2026-06-07)
[1] boots from clean folder ............... ✅ PASS
[2] brain answers (chat round-trip) ....... ✅ PASS
[3] agentic loop completes (signal log) ... ✅ PASS
[4] self-learning promotes a skill ........ ✅ PASS
[5] self-upgrade fires honest receipt ..... ✅ PASS (propose-only, no fake training)
[6] mission graph pauses at approval ...... ✅ PASS
[7] no secrets / no persona leaks ......... ✅ PASS (0 hits)
[8] honest offline (no fabricated reply) .. ✅ PASS

## VERIFIED-IN-SANDBOX vs NEEDS-WINDOWS
- Sandbox (Linux, mock brain): all 8 gates above. Logic proven.
- Needs Ahmad's Windows machine to prove with the REAL brain:
  * llama-server.exe + real GGUF on :8099 (already proven separately: LFM2 answered on :8099 earlier this session)
  * Start-AlBuraq.cmd one-click on Windows
  * the cinematic boot in a real browser/Electron window

## EDITIONS (brains verified on disk in E:\ABU\MODELS)
- Spark: LFM2.5-1.2B-Thinking (698MB) — any machine, no GPU
- Forge: DeepHermes-ToolCalling-8B (4.6GB) — the real "full agent"
- Titan: Qwen3.5-27B (27GB) — DEFERRED (needs engine-streams-model arch)

## NOT DONE / NEXT (honest)
- Real-brain end-to-end run on Windows (copy a GGUF + llama-server.exe into AL_BURAQ/brain, run Start-AlBuraq.cmd).
- Fat/lite exe packaging (PyInstaller/electron-builder) — launcher logic ready, not yet frozen to .exe.
- ComfyUI: generate the full theme set (login art, icon set) — splash + wallpaper done.
- NOT sellable until the real-brain Windows run passes (covenant: prove before price).

## ATTRIBUTION
Agentic loop + self-learning architecture adapted (clean-room, by study) from QADIR_CORE
(itself crediting Hermes MIT + OpenClaw MIT + Claude Agent SDK). Strategy from ABUZ8_OS_DIST.
No source trees were modified.

---
## REAL-BRAIN WINDOWS RUN — 2026-06-07 (FINAL GATE CLOSED)
Proven on Ahmad's actual machine, not sandbox/mock:
- Engine: llama-server.exe + LFM2-1.2B-Tool-Q4_K_M.gguf in AL_BURAQ/brain/ → :8099 HTTP 200
- Backend :8930 → brain_reachable:true
- REAL offline chat: "What is 17 times 23?" → "17 times 23 equals 391." (0.19s, 100% local, correct)
- Cinematic boot.html → health-gate → launcher: browser shows "● backend live :8930" (green)
- Fixed 2 real defects this run:
  1. Thinking-model empty content -> added reasoning_content fallback + raised max_tokens to 1024
  2. Renderer pointed at :8910 -> repointed all 4 HTML files to :8930 (Al-Buraq's port)
- Swapped Spark brain Thinking->Tool variant for clean answers (both real, on disk)

STATUS: Al-Buraq runs end-to-end on real hardware with a real offline brain. All 8 honesty gates + real-brain gate PASS.

## REMAINING TO BE A SHIPPABLE PRODUCT (honest)
- Freeze to one-click .exe (PyInstaller for launcher + bundle brain) — Spark fat exe ~1.5GB, Forge ~5.5GB.
- Generate Forge edition (swap in DeepHermes-8B) + prove it answers.
- Full ComfyUI theme set (login art, icons) — splash+wallpaper done.
- Code-signing cert (avoids SmartScreen warning) — future cost.

---
## ONE-CLICK EXE COMPILE — 2026-06-07 (C1-C4)
Added for true one-click deploy:
- supervisor.py: NEVER-DIE brain (watchdog auto-restart, proven restarts 1->2 after kill)
- brain_router.py: cloud+local switching (local floor never dies; OpenAI/Anthropic/OpenRouter by user key)
- bootstrap/main.py: self-extracting one-exe entry (extract-once to chosen folder, LM-Studio pattern)
- build/build_exe.ps1: PyInstaller build system, 3 editions

### SPARK EXE — PROVEN ONE-CLICK ✅
- AlBuraq-Spark.exe = 3.67 GB (LFM2-1.2B-Tool embedded)
- Launched from CLEAN folder -> self-extracted payload -> backend :8930 + brain :8099 UP
- Real offline chat through the compiled exe: "12 times 12 equals 144." (provider=local, 0.54s)
- Never-die supervisor alive, cinematic boot + shell serve 200
- User moves NOTHING. One file. Double-click. Works.

### FORGE / FUSION
- Forge (DeepHermes-8B, ~4.6GB payload) building.
- Fusion (both brains, ~5.3GB payload, auto-route) next.

---
## FINAL: ONE-CLICK DEPLOY SHIPPED — 2026-06-07
Architecture decision (Ahmad's call): embedded small brain in the EXE (never-die floor) +
big brains as drop-in POWER PACKS (plugin for more power). This sidesteps PyInstaller's
~4GB onefile member limit (which blocked embedding the 8B directly) AND gives an upsell path.

### DELIVERABLE 1 — the one-click EXE
- E:\ABU\AL_BURAQ\build\dist\AlBuraq-Spark.exe  (3.67 GB)
- Embeds: bootstrap + backend + renderer + cinematic assets + llama.cpp engine + LFM2-1.2B brain
- PROVEN one-click from a clean folder (final gate, all PASS):
  self-extract -> never-die brain -> real offline chat ("I'm ready.") -> brain-pack system ->
  cloud/local switching -> cinematic boot. User moves NOTHING.

### DELIVERABLE 2 — brain power packs (drop-in plugins)
- E:\ABU\AL_BURAQ\powerpacks\AlBuraq-Forge-8B.gguf (4.58 GB, DeepHermes 8B) + README.txt
- User drops a pack into install\brain\, activates in OS -> supervisor hot-swaps live (proven).
- Embedded Spark brain always remains the never-die floor.

### C-PHASE FEATURES (all proven)
- C1 never-die supervisor: watchdog auto-restart (proven restarts 1->2 after kill)
- C1 brain router: local floor + OpenAI/Anthropic/OpenRouter by user key
- C2 self-extracting bootstrap: extract-once to chosen folder, survives app deletion
- C3 PyInstaller build system: build/build_exe.ps1
- C5 brain-pack hot-swap: auto-detect ggufs, activate any, live engine swap (proven)

### KNOWN LIMIT (honest)
- PyInstaller --onefile cannot embed a single file >~4GB (struct.error). So the 8B/27B
  brains ship as power packs, NOT baked into the exe. This is the correct architecture anyway
  (smaller base download + upsell). A true 9GB all-in-one exe would need Inno Setup / 7-Zip SFX
  (not installed; offered, Ahmad chose the power-pack model instead).

### PRODUCT LINE (honest, covenant-safe)
- Base: AlBuraq-Spark.exe — one-click sovereign AI OS, works offline forever.
- Power Pack: Forge-8B brain — drop-in upgrade for deeper reasoning.
- Both proven to run real offline inference. Nothing claimed that isn't verified.
