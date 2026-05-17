# Code review — 2026-05-17

Second pass after the May 2026 hardening batch (commits `89ddd7d` →
`9317e6e`, ~12 commits, +1500 LOC code + tests + docs). The first review
(`docs/code-review-2026-05-15.md`) graded the system **B → A−**; this
follow-up checks whether the §7 backlog actually closed and surfaces what
the recent fixes left untested.

This is the brutal version. The marketing version is the article.

## Scoreboard

| Dimension | 2026-05-15 | 2026-05-17 | Δ |
|---|---|---|---|
| Architecture cleanliness | A− | A− | unchanged (registry split was extracted but not topic-split as the §7 plan envisioned) |
| Test breadth (count) | 386 | 408 | +22 tests |
| Test depth (coverage %) | 70% | **71%** | barely moved — most new code added LOC without proportional tests |
| Production readiness | B | **B+** | image-cap + iOS K1/K2 closed; cross-MCP composition partly closed |
| Agent ergonomics | A | A | no regressions; `mcp_ping.image_cap_px` helps debug stale subprocess |
| Documentation freshness | A | A | article + walkthrough updated in same batch as fixes |
| Operational maturity | C+ | **B−** | pre-commit hook + doctor cap-pipeline probe; still no real-device CI |
| **Overall** | A− | **A−** | nudged up the production-readiness axis without losing ground |

Honest answer to "is it truly tested, all real paths tested, done,
furnished?": **No. It's now genuinely production-credible — but it is not
"all real paths tested" and the gap between what looks tested (408 ✓)
and what actually has coverage on the hot paths is non-trivial.**

## §1 — What's actually tested vs what isn't

```
TOTAL                                                     8659   2477   71%
```

Headline: **71% statement coverage**. That's not bad in absolute terms;
the deception is what's IN the 29% gap.

### Critical hot-path files with <50% coverage

| File | Cov | Risk |
|---|---|---|
| `presentation/mcp_server.py` | **0%** | The stdio MCP entry point. Touched by every real session. Zero tests. |
| `__main__.py` + `adapters/__main__.py` | **0%** | Both server entry points untested. |
| `data/repositories/system_environment_repository.py` | **28%** | The doctor. We added 4 new check rows this batch (`pymobiledevice3_cli`, `image_cap_pipeline`, updated tunneld fix) and **wrote zero unit tests for them**. The live probe in chat is the only verification. |
| `infrastructure/flutter_machine_client.py` | **24%** | The JSON-RPC client that drives `flutter run --machine`. Powers every `start_debug_session` / `restart_debug_session`. 127 statements, 97 missed. |
| `data/repositories/flutter_debug_session_repository.py` | **23%** | The owning repository for the above. Stateful, threaded, lifecycle-sensitive. 149 stmts, 114 missed. |
| `data/repositories/qdrant_rag_repository.py` | **20%** | The RAG backbone. Tested mostly via the embedded fallback; the Qdrant path is barely exercised. |
| `data/repositories/wda_ui_repository.py` | **31%** | Now dual-mode (physical/sim). We added 6 K1 tests but they target the factory, not the repo. Action wrappers (tap/swipe/type_text/press_key/find/dump_ui) still untested under the new sentinel path. |
| `infrastructure/ios_observation_repository.py` | **17%** | The K2 hint we shipped lives here. Not unit-tested — only verified via grep. |
| `data/parsers/dart_analyze_parser.py` | **17%** | Output-format-fragile by definition. |

### Gaps in this week's own new code

The fixes that shipped between `89ddd7d` and `9317e6e` introduced ~5
load-bearing code paths with **zero direct test coverage**:

1. **`_HARD_CEILING_PX = 1900` in `image_safety_net.py`.** The whole reason
   it exists is "the env-driven default leaked one too many times."
   There is no test asserting it actually catches an env override past
   1900 — only that the soft cap works. Easy to break without noticing.

2. **`_byte_budget_kb()` + the byte-budget recompress pass.** The 32-MB
   API ceiling motivation. No test that `MCP_MAX_IMAGE_BYTES_KB`
   actually triggers `compress_png_in_place`. No test of the
   `image_cap.compressed: [...]` envelope key.

3. **`SystemEnvironmentRepository._check_image_cap_pipeline()`.** Live-
   verified once in chat. No unit test. It's a doctor probe — if it
   regresses silently, the doctor lies.

4. **`pymobiledevice3_cli` doctor row.** Same — added, manually
   verified, not tested.

5. **`_resize_pil` + `_save_compressed_png` palette pass.** The new
   compressor is exercised via `test_compress_png.py` indirectly, but
   the **PIL palette path inside `_resize_pil`** (lines 116-131 of
   `image_capping.py`) is missing from coverage. The cv2 path with
   PNG_COMPRESSION=9 + palette follow-up (lines 98-108) is also
   missed. The very lines that produce the 3-5× size savings have
   never been executed by a test.

If we shipped tests for items 1-5 above, the headline number would
move ~2 points and the actually-load-bearing coverage would move a
lot more.

### The `tests/agent/transcripts/` surface

3 transcripts (`01_basic_smoke`, `02_small_llm_self_correction`,
`03_dev_session_loop`). All from before the May 2026 fixes. **None
exercise the new tools** (`compress_png`, the K1 dual-mode WDA path,
the new doctor rows). The replay surface is exactly the kind of test
that prevents regressions in agent-visible contracts, and we let
the fixes ship without extending it.

### The `tests/integration_real/` surface

Exactly **one file** (`test_real_inspect_project.py`), skipped unless
`MCP_REAL=1` is set. The README/article both promise a "real-device
integration test" track; this is what's actually there. **First
review's item 5 was not closed.** No real `flutter`, no real `adb`,
no real `xcrun simctl` calls.

## §2 — Architecture audit

### What got better this batch

- ✅ **`presentation/descriptors/` package** extracted (`_shared.py` +
  `_param_builders.py`). `tool_registry.py` dropped 2885 → 2178 LOC.
- ✅ **Dual-mode WDA factory** is well-shaped: protocol-typed,
  injectable `is_simulator` and `wda_module`, structured
  `WdaUnreachable` translation. 6 hermetic tests pin the contract.
- ✅ **ADR-0006** documents the `patch_apply_safe` injection audit
  with two canary-file tripwire tests.

### What didn't get better

- ❌ The §7 plan envisioned **per-topic descriptor files** (`devices.py`,
  `ui.py`, `dev_session.py`, …). We extracted param-builders, not
  descriptors. `tool_registry.py` is still 2178 LOC of one big list
  literal. A new descriptor still requires editing four files
  (use-case, container, UseCases dataclass, tool_registry list).
- ⚠️  **`container.py` is now 656 LOC** with 5 bare `except Exception:`
  clauses (lines 229, 251, 256, 446, 609). Each is small but they're
  the kind of swallow that masks real config bugs.
- ⚠️  **No tests for the descriptors split.** The contract is
  "registry behavior identical after refactor" — there's no test that
  pins that.
- ⚠️  **The `UseCases` dataclass is 90+ fields long.** Adding a tool
  (like `compress_png` today) requires editing 4 places + 1 test.
  We've quietly tripled the surface area of the wiring code.

### Smells found

```
56 occurrences of `except Exception` across src/
 5 of them in container.py
 1 bare `except Exception:` swallowed silently in observability.warn paths
```

Most are defensible (best-effort probes, optional dependencies). The
`container.py` ones deserve a second look — `except Exception: return None`
in a composition root means "config file is broken, ship anyway."

### Files now > 500 LOC

```
 906  presentation/descriptors/_param_builders.py
 656  container.py
 562  data/repositories/yaml_plan_executor.py
 561  domain/entities.py
 474  domain/usecases/productivity.py
 422  domain/repositories.py
2178  presentation/tool_registry.py
```

`tool_registry.py` is still the elephant. `_param_builders.py` is
mechanical-but-large. `productivity.py` is one file holding 5+
unrelated use cases (scaffold/quick_check/grep_logs/summarize/
find_widget) and should split.

## §3 — Security audit

### What's clean
- ✅ All subprocess invocations use `create_subprocess_exec(*cmd)`. Zero
  `shell=True`. ADR-0006 documents the audit + tripwire tests.
- ✅ HTTP API key auth (`MCP_HTTP_API_KEY`) tested. Empty default
  documented as dev-loop-friendly.
- ✅ Webhook allowlist (`MCP_WEBHOOK_ALLOWLIST`) tested.
- ✅ `.mcpignore` + default credential exclusion in the indexer.

### What's not
- ❌ **No audit on `patch_apply_safe`'s gate runner.** Our injection
  audit covered `_run` (the git wrapper). It did NOT cover what
  happens if the gate runner itself shell-escalates. A malicious
  patch landing dart code that does `Process.run("rm -rf …")` would
  pass `git apply --check` and only blow up on `flutter test`. We
  said this in the residual-risks section of ADR-0006; we did not
  fix it.
- ❌ **No path-traversal check on `compress_png(path=…)`.** The new
  tool takes any path on disk and rewrites it. An agent (or
  prompt-injection upstream) could pass `~/.ssh/known_hosts.png` or
  similar. We check `.png` extension and existence, but not that the
  path is under an artifacts directory we own. Low severity (PNG
  rewrites only break the PNG, can't escalate), but a hostile path
  could destroy a file the user actually wanted.
- ⚠️  **`notify_webhook` permits HTTPS to any host by default.** The
  allowlist is opt-in. A prompt-injected agent could POST internal
  trace data to an attacker-controlled domain. Should default to
  empty allowlist (= refuse all) and require explicit opt-in.

## §4 — Operational maturity

### What we have now
- ✅ Pre-commit hook (`.pre-commit-config.yaml`) mirrors CI exactly
- ✅ Doctor check for the cap pipeline (live-verified, no unit test)
- ✅ `mcp_ping` exposes git_sha + image_cap_px → stale subprocess
  diagnosable
- ✅ Tool catalogue auto-generated; CI fails on drift
- ✅ Boot self-check log

### What we still don't have
- ❌ **No latency budgets on any path except the image-cap one.** A
  regression making `take_screenshot` 5x slower would land green.
- ❌ **No memory budget anywhere.** A `dump_ui` against a complex tree
  can return 200 KB+ of XML. We truncate but don't measure.
- ❌ **No structured metrics output.** `observability.emit` writes
  JSON lines if `MCP_LOG_FORMAT=json` but nothing aggregates them.
- ❌ **No release process documented.** When does this hit version
  0.2.0? When is "v1" called? The `pyproject.toml` says `0.1.0` from
  day one.
- ❌ **No CI matrix for Python versions.** Single Python 3.11 lane.
  Released to 3.13 transitively (our local venv runs 3.13) but no
  test confirms.

## §5 — What to ship next (priority-ordered, by impact-per-hour)

### Tier A — high impact, low risk (2-4 hours total)

1. **Test the hard 1900 ceiling + byte budget.** 4 tests in
   `test_image_safety_net.py`. Catches future regressions on the
   exact code paths that have caused four user-visible outages.
2. **Test `_check_image_cap_pipeline`.** 2 tests in a new
   `test_doctor_probes.py`. Inject the env repo, assert it reports
   ok=True with PIL present, ok=False with no backends.
3. **Path-traversal guard on `compress_png`.** Refuse paths outside
   `~/.mcp_phone_controll/sessions/` AND outside the user's project
   path, unless an `--allow-anywhere` flag is passed. Tests for both
   branches.
4. **Tighten `notify_webhook` default.** Empty allowlist → refuse
   non-localhost by default. One-line change + flip of the existing
   test expectation.

### Tier B — high impact, moderate cost (1-2 days)

5. **Real-device integration tests under `MCP_REAL=1`.** Start with
   3: `select_device → take_screenshot → release_device` (Android),
   the iOS equivalent, and `inspect_project` against a real Flutter
   project. CI lane that runs them with a connected emulator.
6. **Topic-split `tool_registry.py`.** Extract `descriptors/devices.py`,
   `descriptors/ui.py`, `descriptors/dev_session.py`,
   `descriptors/ide.py`, `descriptors/code_quality.py`,
   `descriptors/rag.py`. Each ~150-300 LOC. Eliminate the big-list
   pain.
7. **Coverage for `flutter_machine_client.py`** (currently 24%).
   Mirror the `test_vm_service_client.py` pattern — scripted fake
   stdio + JSON-RPC frames.

### Tier C — defer until users ask

8. SQLite trace persistence
9. Multi-Python-version CI matrix
10. Metrics aggregation surface (prometheus/otel)
11. Topic-per-descriptor structural enforcement

## §6 — Verdict

**"Best MCP ever made for that"** is a high bar. Where we sit today:

✅ The agent-visible surface — tool envelopes, `next_action` codes,
   safety nets, doctor probes — is good. Better than most production
   MCPs I've reviewed.

✅ The recent batches closed real production bugs (image cap, iOS K1,
   tunneld hint, byte budget). Each fix shipped with a backlog entry
   documenting why and a commit message documenting how.

⚠️  The hot-path coverage is thinner than the headline 71% suggests.
   The image-cap and cross-MCP paths that fixed real user failures
   are themselves under-tested.

⚠️  The §7 backlog from the first review is half-closed. Items 1-3
   shipped. Items 4-5 (per-topic descriptors, real-device tests) did
   not.

⚠️  Some new code paths from this batch shipped with zero direct test
   coverage. We caught the regressions in production; the safety nets
   we added then went un-tested themselves.

**Status: production-credible, not production-finished.** Solo-founder
deployable today. To call it "best ever made" needs Tier A (closes the
gaps from THIS batch's own fixes) + Tier B (closes the carryover from
the first review). 1-2 days of focused work.

The fix is to keep the test surface growing with the code, not after
it.
