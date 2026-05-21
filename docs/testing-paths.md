# Testing paths — which strategy to use when

Companion to [`docs/testing-scenario-design.md`](testing-scenario-design.md):

| Doc | Answers the question |
|---|---|
| `testing-scenario-design.md` | **What** to test (taxonomy + standards) |
| `testing-paths.md` (this one) | **How / when / in what order** (orchestration) |

Read this when an agent or human asks "I want to test something — what do I actually do right now?" The `recommend_test_path` tool returns one of the canonical paths below, sequenced as a runnable plan.

## The seven canonical paths

| Path | Context | Wall-clock | Devices touched |
|---|---|---|---|
| `pre_commit` | Before `git commit` | 60s | none |
| `pre_pr` | Before opening a PR | 5-10 min | 1 |
| `daily_dev` | Inner dev loop | 15 min (+ user-driven UI) | 1 |
| `nightly` | Regression matrix | 1h+ | many |
| `pre_release` | Before any production ship | 30-60 min | 1-2 |
| `hotfix` | Before re-shipping a fix | 5-10 min | 1 |
| `postmortem` | Reproducing a prod incident | open-ended | 1 |

## How to pick one

```
Did something go wrong in production already?
  └─ Yes → postmortem (reproduce + diagnose)
      └─ found a fix → hotfix (verify minimally)

Are you about to push code?
  └─ git commit → pre_commit (60s static + unit)
  └─ git push (open PR) → pre_pr (must-pass gate)

Are you actively building something?
  └─ Yes → daily_dev (inner loop with profiling)

Is it the end of the day / nightly CI?
  └─ Yes → nightly (regression matrix)

Are you about to ship to users?
  └─ Yes → pre_release (full audit)
```

## Isolation guarantees (what each path WON'T touch)

A core design principle: testing should NEVER impact a real user's data, a production backend, or a developer's personal device state. Every path lists its `isolation_guarantees` in the tool result so you can run it on your daily phone without fear.

Common guarantees across paths:
- **Test devices only.** None of the canonical paths assume the device is signed into a real-user account.
- **Locked + cleared between flows.** `select_device` + `clear_app_data` ensures one path's state doesn't leak into the next.
- **No outbound webhooks** unless `MCP_WEBHOOK_ALLOWLIST` is explicitly set.
- **No production backend** — paths use the project's test/staging env.
- **Artifacts isolated to the session dir** — `~/.mcp_phone_controll/sessions/<sid>/`.

When a path needs a side-effect step (a build, a lock acquire, a clear_app_data), that step is marked `side_effects=True` in the returned plan so the agent can decide whether to skip on a retry.

## The seven paths in detail

### 1. `pre_commit` — fast static + unit checks (60s)

**Use when**: you're about to `git commit`. Designed to fit in a pre-commit hook without slowing the developer's loop.

**Steps**: dart_analyze → dart_format (check-only) → run_widget_test → list_missing_widget_keys (optional).

**Pass criteria**: all steps return `ok=true`. Fix locally — don't amend over a broken state.

**Skip when**: you're only changing docs (run nothing); mid-rebase (wait until rebase completes).

**Alternative**: pre_pr for deeper coverage before opening a PR.

### 2. `pre_pr` — minimum-defensible quality gate (5-10 min)

**Use when**: you're about to open a PR for review.

**Steps**: check_environment → select_device → quality_gate → test_coverage_report (with threshold) → run_integration_tests → audit_accessibility → release_device.

**Pass criteria**:
- All required steps `ok`
- `test_coverage_report.passed_threshold == True`
- `audit_accessibility.blocker_count == 0`

**Skip when**: docs-only PR (skip integration + coverage); branch < 24h ahead of main (the nightly path is more comprehensive).

**Alternative**: nightly (broader matrix), pre_release (deeper audit).

### 3. `daily_dev` — inner loop with profiling (15 min + user-driven UI time)

**Use when**: actively building/iterating on a feature, want diagnostic feedback after each interaction.

**Steps**: mcp_ping → select_device → new_session → prepare_for_test → propose_test_scenarios (top 3 P0 happy-path) → start_debug_session → memory_summary → allocation_profile(reset) → start_frame_profile → **(agent drives the UI here)** → stop_frame_profile → detect_undisposed_controllers → assert_no_errors_since → summarize_session → stop_debug_session → release_device.

**Pass criteria**:
- `stop_frame_profile.jank_pct < 5%`
- `allocation_profile` delta has no growing classes you expected to stay flat
- `detect_undisposed_controllers.total_suspect_instances` doesn't trend up
- `assert_no_errors_since` passes

**Skip when**: refactor-only changes (pre_commit faster); investigating prod incident (use postmortem).

**Alternative**: hotfix (focused), nightly (broader).

### 4. `nightly` — cross-device regression matrix (1h+)

**Use when**: end-of-day or scheduled CI run, want broad regression coverage.

**Steps**: check_environment → propose_test_scenarios (top 50, full P0+P1+P2) → list_avds → list_simulators → build_app (release) → analyze_app_size (vs baseline) → run_test_plan (smoke.yaml across matrix) → audit_accessibility → disk_usage → prune_originals → summarize_session.

**Pass criteria**:
- All scenarios pass
- `audit_accessibility.blocker_count == 0`
- `analyze_app_size` deltas vs baseline < 500KB per package (unless intentional)
- No `next_action` field surfaces in the session trace

**Skip when**: no new changes since last nightly; CI build itself is failing.

**Alternative**: pre_release for any actual ship.

### 5. `pre_release` — full audit before production (30-60 min)

**Use when**: about to push to App Store / Play Store / production.

**Steps**: check_environment → quality_gate → test_coverage_report → build_app (release) → analyze_app_size (vs baseline) → propose_test_scenarios (top 20 P0 across critical categories) → run_test_plan (ump_decline.yaml) → audit_accessibility → memory_summary → detect_undisposed_controllers → capture_release_screenshot (optional) → session_summary.

**Pass criteria**:
- `quality_gate` ok
- `test_coverage_report.passed_threshold` true
- `analyze_app_size` deltas justify any growth
- `audit_accessibility.blocker_count == 0`
- All P0 scenarios pass
- `session_summary` documents the release for audit

**Skip when**: not an actual release (use pre_pr); CMS content-only change.

**Alternative**: hotfix if patching a live issue.

### 6. `hotfix` — focused verification before re-shipping (5-10 min)

**Use when**: you've fixed a production bug and need minimal verification before pushing the fix.

**Steps**: mcp_ping → dart_analyze → run_widget_test → select_device → clear_app_data → launch_app → **tap_and_verify (REPLACE: the action that triggered the bug)** → assert_no_errors_since → take_screenshot → release_device.

**Pass criteria**:
- Regression test passes
- `tap_and_verify` succeeds (this is the crucial step — the agent customizes this per bug)
- `assert_no_errors_since` clean
- Screenshot attached to the hotfix PR

**Skip when**: bug is a build/config change (use pre_commit); bug in a rarely-hit path (defer to nightly).

**Alternative**: postmortem for full diagnosis; pre_pr if a regression PR.

### 7. `postmortem` — reproduce + diagnose a production incident (open-ended)

**Use when**: a production incident landed; you need to reproduce + diagnose to write up the postmortem.

**Steps**: check_environment → new_session → select_device → clear_app_data → start_debug_session → start_frame_profile → **(agent reproduces the failure flow)** → stop_frame_profile → memory_summary → read_debug_log (120s window) → dump_widget_tree → take_screenshot → session_summary.

**Pass criteria** (this path has unusual "pass"):
- **Either** the issue reproduces deterministically and `session_summary` captures the trace
- **Or** the issue does NOT reproduce — and the trace documents what was tried so the next engineer doesn't redo the work

**Skip when**: incident is solved; incident is purely backend/infra.

**Alternative**: hotfix once you have a fix to verify.

## Composing paths

Some real-world workflows chain multiple paths:

```
Active development day:
  daily_dev × N iterations
  → pre_commit (when ready to commit)
  → pre_pr (when ready to PR)
  → review / merge
  → (auto) nightly that night

Production incident:
  postmortem (diagnose)
  → fix branch
  → hotfix (verify the fix)
  → pre_pr (PR for the fix)
  → merge + nightly
  → if it's a critical release, pre_release before shipping the patch
```

The tool doesn't auto-chain — each call returns one path. The agent decides which to call next based on the previous path's pass/fail.

## Recommendation paths and the existing 125 tools

Each path is built from existing MCP tools — no path requires anything that isn't already shipped. This means:

- New tools added to the MCP automatically benefit existing paths if you update the path builders.
- Paths are debuggable: the agent can see exactly which tool calls + args the recommendation produces.
- Paths are tweakable: if a user's workflow differs (e.g. they want `audit_accessibility` in `pre_commit`), they can compose their own variant from the same primitives.

## When NOT to use these paths

- **You already have a defined testing workflow your team relies on.** Use that. The recommended paths are starting points, not laws.
- **You're prototyping.** Test paths are for things you ship — at prototype stage, just dogfood.
- **You're testing a third-party SDK in isolation.** None of these paths are designed for "test this dependency in vacuo" — use the SDK's own test harness.

## See also

- [`docs/testing-scenario-design.md`](testing-scenario-design.md) — the WHAT (taxonomy)
- [`docs/operational-gotchas.md`](operational-gotchas.md) — pre-flight issues that cost an hour the first time
- [`docs/tools-by-category.md`](tools-by-category.md) — full tool catalog grouped by user goal
- [`examples/scenarios/`](../examples/scenarios/) — end-to-end worked examples
- [`docs/runbook.md`](runbook.md) — top-10 production failure modes
