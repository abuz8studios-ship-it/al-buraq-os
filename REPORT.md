# AL-BURAQ OS — Probe · Audit · Diagnose · Evolve · Optimize · Verify · Report
**System:** Al-Buraq Agent OS (Apex Self-Learning Sovereign Desktop OS)
**Canon:** The Builders Book (Zero to Hero in Agentic Systems) by Ahmad Odeh & Qadir · ABUZ8 LLC
**Date:** 2026-10-01
**Method:** Probe-first. Every defect below was reproduced with evidence BEFORE being fixed, and every fix was re-probed live over HTTP AFTER. No claim without a receipt.

---

## 1. Executive Summary

A full probe → audit → diagnose → evolve → optimize → verify cycle was run against the codebase at `01fe7c1`. The pre-existing 39-test suite passed at baseline (12.03s), but **green tests were treated as insufficient** per the Law of the Probe — adversarial live probing against the running server found **6 confirmed defects**, including two that the previous session's report (2026-09-30, see Appendix A) had claimed were already fixed.

All 6 defects were cured with smallest-change edits, 13 new regression tests were added (one per defect, each encoding the exact probe that caught it), and the full suite re-verified: **52/52 passed in 1.62s** (was 39 tests / 12.03s — the suite itself got **7.4x faster** because offline agent turns no longer burn two HTTP retry cycles with backoff sleeps against a dead brain). Live re-probes of all 6 defects returned green; a 26-endpoint smoke sweep returned zero failures.

---

## 2. Probe Baseline

| Probe | Result |
| :--- | :--- |
| `pytest tests/` (pre-existing 39 tests) | 39 passed, 12.03s |
| Live boot of `backend/server.py` on clean data dir | Boots, `/health` 200 |
| Static asset + app routes (`/`, `/apps/*`, `/assets/*`) | All 200 |
| Adversarial probes P1–P8 (below) | **6 defects confirmed** |

---

## 3. Diagnosed Defects (each probe-reproduced BEFORE the fix)

| # | Defect | Evidence (reproduced) | Root cause | Severity |
| :--- | :--- | :--- | :--- | :--- |
| **P2** | Nested JSON tool args execute as `{}` | `_act('{{tool: memory_store \| {"key":"k1","metadata":{"nested":{"deep":1}}}}}')` → `error: key and content required`. Prior report claimed this regex breakage was fixed; it was not. | Non-greedy regex `(\{.*?\})` stops at the first `}` | High — any model emitting nested tool args fails |
| **P3** | Quotes in user text corrupt offline tool directives | POST `/api/inbox/send` with `"probes" and 'receipts'` → `builders_book_query` executed with `args: {}` (user's query silently lost) | f-string interpolation of raw user text into JSON args, no escaping | High — silent data loss on common input |
| **P4** | Approval-gated nodes with payloads never execute | Create mission w/ gated payload → approve → node status `done`, `result: None`. The `'approved'` branch in `advance()` was dead code | `approve()` marked nodes `done` directly; `advance()` never selected `approved` | High — approval gates silently skip the action they gate |
| **P5** | `/api/jobs` wrong `last_run` + double full-file harvest | Fresh server: `last_run` = current ts of last *signal* row, not last learn cycle; `learn.harvest()` called twice per poll, each re-reading/re-parsing the whole `signal.jsonl` | Wrong data source + O(file-size) work per poll | Medium — grows worse with history |
| **P6** | `/api/boot/report` honesty gates hardcoded `True` | Fresh EMPTY data dir → all 8 gates `true`, incl. `agentic_core_verified` with zero signal rows | Dict literal, never computed | High — violates DESIGN_SPEC §1.3 "No fabricated metrics, ever" |
| **P7** | Unbounded file reads | `signal_tail`, `harvest()`, `_rows()` read the entire file per call; `LEARNED.md` grows unbounded, and its stale HEAD (not tail) was injected into prompts | No tail-bounded IO | Medium — latency grows with history |
| **P8** | (minor items) CORS `allow_credentials=True` with wildcard origin (invalid combo); `albuq_install.json` typo in bootstrap; Sovereign UI showing hardcoded fake telemetry (memory 98/82/68/34%, "128,420 tokens", "$0.87") | Code/UI inspection + rendered HTML | — | Low–Medium |

*Note:* P1 — `/health` latency with brain down — measured at 2ms on this host (connection-refused is instant). It degrades to ~3s/poll only behind packet-dropping firewalls; hardened anyway via TTL-cached reachability (1.0s probe timeout, 2.5s cache).

---

## 4. Evolutions (smallest change per defect)

| File | Change |
| :--- | :--- |
| `backend/agent_loop.py` | **Balanced-brace, string-aware directive scanner** (`_extract_tool_directives`) replaces the non-greedy regex — nested JSON and braces-inside-strings now parse. **`_directive()` builder** uses `json.dumps` so user text can never corrupt args. Word-boundary trigger matching (`timeline` no longer fires the clock tool; `*` and `%` now trigger math). **Local-brain preflight** (0.6s probe, 2s TTL cache) skips the 2×30s retry loop when the floor engine is provably down. **LEARNED.md**: tail (fresh corrections) injected instead of head; file rotates at 64KB keeping newest 300 entries. |
| `backend/server.py` | **Honesty gates computed live from disk evidence** (`honesty_gates` + `honesty_evidence` + `honesty_all_green`); structural gates are labeled as such. `builders_book.status` reflects real L4 vault count. **TTL-cached `_brain_reachable()`**. **`/api/jobs`** reports the last *real* learn-cycle ts from the audit log; no harvest per poll. **`/api/signal/tail`** bounded (seek-based tail; reports whether `total_count` is exact). CORS credentials flag fixed. |
| `backend/mission_graph.py` | `approve()` marks payload-carrying gates `approved` (action executes on next `advance()`); payload-less checkpoints keep the legacy `done` behavior. `advance()` selects `approved` nodes. |
| `backend/self_learning.py` | Bounded tail harvest (`MAX_HARVEST_ROWS=5000`); new `last_cycle_ts()`. |
| `backend/self_upgrade.py` | Rolling success computed over bounded recent tail (`MAX_SIGNAL_ROWS=5000`). |
| `backend/jsonl_io.py` | **New.** Shared seek-based `tail_lines`/`tail_jsonl` — constant-cost reads regardless of history size. |
| `bootstrap/main.py` | Config filename fixed to `alburaq_install.json` (legacy `albuq_install.json` still honored). |
| `renderer/apps/sovereign.html` | **Honest telemetry**: Memory Layers, Model Router, connector count, and signal/cost panels now hydrate from live `/api/memory/stats`, `/api/brains/config`, `/api/connectors/list`, `/api/signal/tail` every 15s; hardcoded fake numbers removed; offline states shown honestly. |
| `.gitignore` | Runtime state untracked (`data/baseline.json`, `data/triggers/` — kept on disk), `.venv/`, `.pytest_cache/` ignored. |
| `tests/test_probe_regressions.py` | **New.** 13 regression tests — one per cured defect, each a receipt. |

---

## 5. Verification Receipts

### 5.1 Test suite (before → after)

```text
BEFORE:  39 passed in 12.03s
AFTER:   52 passed in 1.62s   (39 pre-existing, all green + 13 new regression tests)
```

The 7.4x suite speedup is itself a fix receipt: offline agent turns previously spent ~0.7–1.5s each in two failed HTTP retries + backoff sleeps per THINK; the preflight makes offline turns ~1–8ms.

### 5.2 Live re-probes of every defect (post-fix, real HTTP on :8931)

```text
P2 nested args            PASS   memory_store executed with nested metadata
P3 quoted text            PASS   builders_book_query received the query intact
P4 approval executes      PASS   approve -> status 'approved' -> advance executed 'SIDE_EFFECT_RAN'
P5 jobs last_run          PASS   None before /api/learn/run -> real cycle ts after
P6 honest gates           PASS   fresh dir: embedded_brain_floor=False, agentic_core_verified flips
                                 True only after real turns; evidence strings served with the report
smoke: 26 GET endpoints   0 failures
chat fallback             provider=sovereign_offline, reply present, brain_reachable=False (honest)
memory CRUD               store + delete round-trip OK
static routes             /, /apps/*, /assets/* all 200
```

### 5.3 Measured latencies (post-fix, brain offline)

| Operation | Measured |
| :--- | :--- |
| Offline agent turn (full THINK·ACT·VERIFY·LEARN) | **4–8 ms** (≈1.3–1.8s pre-fix) |
| `/health` (UI polls every 8s) | 0.8–1.9 ms |
| `/api/signal/tail` on 60,000-row signal.jsonl | < 2 ms, returns last 20 exactly, `total_count_is_exact: false` (honest) |

### 5.4 Honesty gates — live state on the audit server

```json
"honesty_gates": {
  "launcher_clean_folder": true,      // structural — proven by test_gate_1
  "zero_secrets_leaked": true,        // structural — masking enforced + test_gate_7
  "embedded_brain_floor": false,      // honest: no GGUF/engine on this machine
  "agentic_core_verified": true,      // receipt: real turns in signal.jsonl
  "skill_loop_verified": true,        // receipt: self_learning_log.jsonl written
  "upgrade_loop_verified": true,      // receipt: upgrade cycle ran (reason logged)
  "mission_graph_verified": true,     // receipt: missions.sqlite on disk
  "builders_book_ingrained": true     // receipt: 11/11 chapters in L4 vault
}
```

On a **fresh empty** data dir the same endpoint returns `agentic_core_verified: false`, `skill_loop_verified: false`, `embedded_brain_floor: false`, `honesty_all_green: false` — verified by test `test_boot_report_gates_honest_on_fresh_dir`. No more fake green.

---

## 6. Known Limitations (honest, not claimed fixed)

- **No GGUF in repo** (by design — weights carry their own licenses). Until a brain pack is present, `embedded_brain_floor` reports `false` and the sovereign deterministic floor serves; that is the gate working, not a bug.
- `mission-control.html` still contains cinematic placeholder content (portfolio/cron/revenue mock panels) from the harvested shell; its live-wired calls (`/api/boot/report`, `/api/jobs`, port probes) are functional.
- LoRA training remains propose/receipt-only on machines without a GPU box (documented behavior, receipts in `data/triggers/`).

---

## Appendix A — Audit trail: the 2026-09-30 report

The previous session's report claimed "39 tests, 100% pass, all honesty gates verified." The 39-test pass was reproducible; however, adversarial probing **disproved two of its fix claims**: (1) "regex breakage on nested JSON" was still broken (P2), and (2) the honesty gates it declared 100% verified were hardcoded constants, not verifications (P6). Per the Builders Book: *doc-trust over disk-trust is a failure pattern.* This report supersedes it; the previous deliverables (4-layer memory, unified inbox, Builders Book engine, static routing) were re-verified working and kept intact.
