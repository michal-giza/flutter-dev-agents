# 🧪 Test Runbook — flutter-dev-agents

The single doc readers run when they want to validate the work in the
articles. Phase 0 is universal pre-flight; Phases 1–5 map 1:1 to
articles #1–#5. Each scenario lists exact commands, the stdout to
expect, and what counts as a pass.

If a scenario doesn't pass, the troubleshooting table at the bottom is
keyed by the symptom. Every command was captured from a real machine
on the day this doc was written; if your output differs, that's a
signal worth diagnosing — don't paper over it.

---

## Phase 0 — Pre-flight (5 min, always)

Confirms the install works before any agent does any thinking.

```bash
cd ~/Desktop/flutter-dev-agents/packages/phone-controll

# 1. Suite must be green.
.venv/bin/python -m pytest tests/ -q
```

**Expected tail:**
```
======================== 301 passed, 2 skipped in 1.83s ========================
```

```bash
# 2. The container must build and register all tools.
.venv/bin/python -c "
import asyncio
from mcp_phone_controll.container import build_runtime
async def main():
    uc, d = build_runtime()
    print('total tools:', len(d.descriptors))
asyncio.run(main())
"
```

**Expected:** `total tools: 98`

**Pass criteria:** `301 passed`, `total tools: 98`. If either is off, **stop** and investigate before going further. Most likely cause: an editable-install drift (`uv pip install -e '.[dev,ar,http,rag]'`).

---

## Phase 1 — Article #1 (the dev loop) scenarios

### Scenario A — 4-tool boot sequence (2 min)

**Goal:** Confirm `describe_capabilities`, `check_environment`, `list_devices` all return `ok:true` against your local machine.

```bash
cd ~/Desktop/flutter-dev-agents/packages/phone-controll

.venv/bin/python -c "
import asyncio
from mcp_phone_controll.container import build_runtime
async def main():
    uc, d = build_runtime()
    res = await d.dispatch('describe_capabilities', {'level':'basic'})
    print('describe_capabilities:', res['ok'],
          'tool_subset:', len(res['data']['tool_subset']))
    print('  first 5 in recommended_sequence:',
          res['data']['recommended_sequence'][:5])
    res = await d.dispatch('check_environment', {})
    print('check_environment:', res['ok'])
    res = await d.dispatch('list_devices', {})
    print('list_devices:', res['ok'])
    if res['ok'] and res['data']:
        d0 = res['data'][0]
        print('  first device:', d0.get('serial'), d0.get('platform'))
asyncio.run(main())
"
```

**Expected stdout (tail):**
```
describe_capabilities: True tool_subset: 18
  first 5 in recommended_sequence: ['describe_capabilities', 'check_environment', 'inspect_project', 'list_devices', 'select_device']
check_environment: True
list_devices: True
  first device: R3CYA05CHXB Platform.ANDROID
```

**Pass criteria:**
- `tool_subset: 18` (the BASIC tier).
- `recommended_sequence` starts with `describe_capabilities`.
- At least one device listed (or empty list with `ok:true` if no phone is plugged in — also fine).

**Why this matters:** If a 4B agent can't pass this check, nothing else in the article works for it.

### Scenario B — Declarative dev loop (5 min, requires a real Flutter project + device)

**Goal:** The plan walker drives the same loop a human follows in VS Code — open IDE, lock device, start `flutter run --machine`, hot-reload, capture the debug log, stop.

Edit `examples/templates/dev_iteration.yaml` and replace the two `REPLACE_*` placeholders with your `package_id` and a real `integration_test/<file>.dart`. Then in Claude Code:

```
> Use phone-controll. Validate then run examples/templates/dev_iteration.yaml
> against /Users/<you>/Desktop/<your-project>. After it finishes, call
> summarize_session and paste the 3-line headline.
```

**What to watch for in the agent's tool calls:**
1. `validate_test_plan` → `ok:true`. (Tier B2 semantic checks.)
2. `run_test_plan` walks: PRE_FLIGHT → OPEN_IDE → CLEAN → DEV_SESSION_START → HOT_RELOAD → UNDER_TEST → DEV_SESSION_STOP.
3. `summarize_session` returns a 3-tuple `{headline, facts, errors}`.

**Pass criteria:**
- A new VS Code window opened on your project.
- `~/.mcp_phone_controll/sessions/<sid>/` exists with screenshots + debug logs + (if `report.format=junit`) a `.junit.xml`.
- `headline` shows ≥ 6 successful calls.

### Scenario C — Multi-project parallelism (10 min, requires 2 devices)

**Goal:** Two Claude sessions run independent loops against different devices.

Open two terminals → two `claude` sessions → in each, run Scenario B with a different project + device serial. The second session must **not** acquire the first session's device.

**Pass criteria:**
- Each session locks its own serial in `~/.mcp_phone_controll/locks/`.
- Each opens its own VS Code window.
- `list_locks` from a third session sees both locks owned by different `session_id`s.
- `release_device` in session 1 doesn't touch session 2.

---

## Phase 2 — Article #2 (the RAG bridge) scenarios

> **Pre-req:** `[rag]` extras installed and Qdrant running.
> ```bash
> cd ~/Desktop/flutter-dev-agents/packages/phone-controll
> uv pip install -e '.[rag]'
> docker run -d --name qdrant -p 6333:6333 \
>   -v ~/qdrant_storage:/qdrant/storage qdrant/qdrant
> curl -s http://localhost:6333/healthz
> ```

### Scenario A — Index a project, recall a chunk (5 min)

```bash
cd ~/Desktop/flutter-dev-agents/packages/phone-controll

.venv/bin/python -c "
import asyncio
from pathlib import Path
from mcp_phone_controll.container import build_runtime

async def main():
    _, d = build_runtime()
    # 1. Index this very repo's docs.
    res = await d.dispatch('index_project', {
        'project_path': str(Path.cwd().parent.parent),
        'collection': 'fda-test',
    })
    print('index:', res['ok'])
    if res['ok']:
        s = res['data']
        print(f\"  files={s['files_indexed']} chunks={s['chunks_indexed']}\"
              f\" duration={s['duration_ms']}ms\")
    # 2. Ask for the SKILL chunk on UMP_GATE.
    res = await d.dispatch('recall', {
        'query': 'UMP_GATE preconditions decline path',
        'k': 3,
        'scope': 'all',
    })
    print('recall:', res['ok'])
    if res['ok']:
        for i, c in enumerate(res['data'], 1):
            print(f\"  [{i}] {c['source']} score={c['score']:.3f}\")
            print(f\"      {c['text'][:120]}...\")
asyncio.run(main())
"
```

**Pass criteria:**
- `index: True` with `files=…` ≥ 20 and `chunks=…` ≥ 50.
- `recall: True` with 3 results, each `score > 0.3`.
- Hybrid retrieval is doing work — at least one of the top-3 results contains a literal substring match of a query token (proves lexical fusion fired).

### Scenario B — Token-budget proof (3 min)

**Goal:** Confirm the article's "70% savings" claim in your own environment.

```bash
cd ~/Desktop/flutter-dev-agents/packages/phone-controll

# Old SKILL (preserved as SKILL-FULL.md after the G6 collapse).
wc -c ~/Desktop/claude_skills/skills/mcp-phone-controll-testing/SKILL-FULL.md
# New thin SKILL (loaded by Claude Code at session start).
wc -c ~/Desktop/claude_skills/skills/mcp-phone-controll-testing/SKILL.md
```

**Expected:** `30794` bytes for SKILL-FULL.md, `4570` bytes for SKILL.md (or close to it).

**Pass criteria:** New SKILL ≤ 1/5 of the old one. Add `recall(scope="skill")` per-call cost (~200 tokens) × your typical query count to compute your actual budget delta.

### Scenario C — Shadow-run smoke (1 min)

**Goal:** Tier-G tools all return well-formed envelopes under fuzz.

```bash
cd ~/Desktop/flutter-dev-agents/packages/phone-controll
.venv/bin/python -m scripts.shadow_run --suite tier_g --iterations 50
```

**Expected stdout (tail):**
```
shadow-run done → /Users/<you>/.mcp_phone_controll/shadow-runs/<stamp>-shadow.json
```

**Pass criteria:** Exit code 0, no `tools_with_violations` mentioned in stderr. The JSON report's `envelope_invariants_violated` must be `0` for every tool.

---

## Phase 3 — Article #3 (Reflexion + CRAG) scenarios

### Scenario A — Reflexion retry on a flaky phase

**Goal:** Watch the plan walker insert a `REFLECTION` pseudo-phase, retry, and recover.

```bash
cd ~/Desktop/flutter-dev-agents/packages/phone-controll
MCP_REFLEXION_RETRIES=2 .venv/bin/python -m pytest \
  tests/unit/test_reflexion_retry.py -v
```

**Expected stdout (tail):**
```
tests/unit/test_reflexion_retry.py::test_no_retry_when_disabled_blocks_immediately PASSED
tests/unit/test_reflexion_retry.py::test_reflexion_retries_recover_when_attempts_eventually_succeed PASSED
tests/unit/test_reflexion_retry.py::test_reflexion_exhausts_retries_then_blocks PASSED
tests/unit/test_reflexion_retry.py::test_reflection_notes_carry_failure_diagnosis PASSED
============================== 4 passed in 0.03s ===============================
```

**Pass criteria:** All four tests pass. The recover-and-continue test is the headline — it proves a single flaky `UNDER_TEST` phase doesn't blow the run.

**To exercise live against your project:** Set `MCP_REFLEXION_RETRIES=2` in the Claude Code environment, then run a known-flaky Patrol test through `run_test_plan`. In the resulting `session_summary`, look for:
- A `REFLECTION` outcome with `notes` containing the prior failure diagnosis.
- A subsequent successful retry of the same phase.
- `overall_ok: true` despite the original failure (because the retry-success absorbs it).

### Scenario B — CRAG fallback on low-confidence query

**Goal:** When a scope has weak chunks, CRAG falls back through the scope ladder.

> Pre-req: Phase 2 done — index has been populated.

```python
# Paste into a Python REPL or save as test.py
import asyncio
from mcp_phone_controll.container import build_runtime

async def main():
    _, d = build_runtime()
    # An intentionally vague query that won't match the SKILL well.
    res = await d.dispatch('recall_corrective', {
        'query': 'something very generic',
        'k': 3,
        'scope': 'skill',
        'confidence_threshold': 0.30,
        'max_retries': 3,
    })
    print(res)

asyncio.run(main())
```

**Pass criteria:**
- `ok: true` even if confidence is low — CRAG returns best-effort.
- `data.used_scope` differs from the requested `scope` (proves fallback fired).
- `data.diagnosis` is a coherent sentence explaining why.

---

## Phase 4 — Article #4 (Voyager skill library) scenarios

### Scenario A — Promote → list → replay roundtrip

```bash
cd ~/Desktop/flutter-dev-agents/packages/phone-controll
.venv/bin/python -m pytest tests/unit/test_skill_library.py -v
```

**Expected stdout (tail):**
```
tests/unit/test_skill_library.py::test_promote_then_list_then_replay PASSED
tests/unit/test_skill_library.py::test_promote_rejects_invalid_name PASSED
tests/unit/test_skill_library.py::test_promote_rejects_empty_window PASSED
tests/unit/test_skill_library.py::test_replay_unknown_skill PASSED
tests/unit/test_skill_library.py::test_replay_records_failure PASSED
tests/unit/test_skill_library.py::test_apply_overrides_substitutes_dollar_placeholders PASSED
============================== 6 passed in 0.04s ===============================
```

**To exercise live in Claude Code:**

```
> 1. select_device by my serial
> 2. new_session(label="boot")
> 3. start_debug_session(project_path="/path/to/my/app", mode="debug")
> 4. promote_sequence(name="boot_debug_session", description="lock device, open session, start flutter run --machine")
> 5. list_skills
```

**Pass criteria:** `list_skills` shows `boot_debug_session` with `steps=3` (or however many low-level calls preceded the promote). `success_count: 0` initially — counters bump on **replay**, not on creation.

### Scenario B — Replay a skill on a different project

```
> replay_skill(name="boot_debug_session", overrides={"proj": "/path/to/other/app"})
```

**Pass criteria:**
- The 3 underlying tool calls execute in order, with the `$proj` placeholder substituted.
- `list_skills` now shows `use_count: 1`, `success_rate: 1.0` (assuming all steps succeeded).

---

## Phase 5 — Article #5 (benchmarking) scenarios

### Scenario A — Run the bench (1 min)

```bash
cd ~/Desktop/flutter-dev-agents/packages/phone-controll
.venv/bin/python -m bench.run_bench
```

**Expected stdout (tail):**
```
bench done → /Users/<you>/.mcp_phone_controll/bench/<stamp>.json
  junit → /Users/<you>/.mcp_phone_controll/bench/<stamp>.junit.xml
  passed: 10/10
```

**Pass criteria:** `passed: 10/10`, no failures listed in stderr. Exit code 0.

### Scenario B — Add a custom task

Edit `bench/tasks.json`, add at the end:

```json
{
  "id": "T11-my-flow",
  "description": "Validate my own canonical workflow.",
  "calls": [
    {"tool": "list_devices", "args": {}, "expect": {"ok": true}},
    {"tool": "select_device", "args": {"serial": "EMU01"}, "expect": {"ok": true}},
    {"tool": "tap_and_verify", "args": {"text": "Sign in", "expect_text": "Welcome"}, "expect": {"ok": true}}
  ]
}
```

Then:

```bash
.venv/bin/python -m bench.run_bench --tasks T11-my-flow
```

**Pass criteria:** Your new task either passes (your fake/real stack supports the flow) or fails with a precise reason. Failure is fine — it's the bench doing its job.

---

## 📋 Quick checklist (printable)

```
PHASE 0 — Pre-flight
[ ] pytest: 301 passed, 2 skipped
[ ] build_runtime() reports 98 tools

PHASE 1 — Article #1 (dev loop)
[ ] Scenario A: 4-tool boot sequence all ok
[ ] Scenario B: declarative dev_iteration.yaml run produces session artifacts
[ ] Scenario C (optional): 2 sessions × 2 devices, no lock collision

PHASE 2 — Article #2 (RAG bridge)
[ ] Scenario A: index_project + recall return ≥3 ranked chunks
[ ] Scenario B: SKILL.md ≤ 1/5 of SKILL-FULL.md
[ ] Scenario C: shadow-run zero envelope-invariant violations

PHASE 3 — Article #3 (Reflexion + CRAG)
[ ] Scenario A: 4 reflexion tests pass
[ ] Scenario B: CRAG falls through scopes on vague queries

PHASE 4 — Article #4 (Voyager skill library)
[ ] Scenario A: 6 skill-library tests pass
[ ] Scenario B: replay_skill substitutes $-overrides correctly

PHASE 5 — Article #5 (bench)
[ ] Scenario A: 10/10 bench tasks pass
[ ] Scenario B: custom task lands and runs
```

---

## 🐛 Troubleshooting — likely culprits

| Symptom | Likely cause | Fix |
|---|---|---|
| `total tools: 92` (not 98) | Tier H/I aren't installed (editable mode drift). | `cd packages/phone-controll && uv pip install -e .` |
| `recall` returns `next_action: install_rag_extra` | `[rag]` extras missing. | `uv pip install -e '.[rag]'` |
| `recall` returns `next_action: start_qdrant` | Qdrant unreachable. | `docker run -d --name qdrant -p 6333:6333 qdrant/qdrant` |
| `index_project` says "no indexable content" | Globs exclude everything. | Pass `include_globs=["**/*.md","**/*.dart","**/*.py"]` explicitly. |
| `tap_text` returns `code: TapTextRefused` | A Patrol session is active. | Use `run_patrol_test` for app UI; pass `system=true` only for OS dialogs. |
| Hangs ~1 min on first `recall` | FastEmbed downloading the embedding model (~50MB). | Wait. One-time only. |
| `MCP_REFLEXION_RETRIES=N` does nothing | Env var read at process-start; need to relaunch Claude Code. | `exit` then `claude`. |
| Screenshot images "exceed dimension limit" in Claude | Image cap not in effect. | Make sure `image_capping.py` is on disk and you've relaunched Claude Code so the MCP subprocess restarted. |
| `bench` fails on T07 (rate-limit) | Test is sequence-dependent; running it alone is fine. | `python -m bench.run_bench --tasks T07-rate-limit-honoured` runs it isolated. |
| iOS-related failures | iOS 26 stale DDI. | `sudo pymobiledevice3 remote tunneld` then re-run. |

---

## What to share when asking for help

If a scenario fails and you need help diagnosing it, paste:
1. The exact command you ran.
2. The full envelope from the failing tool (the `error` block — `code`, `message`, `next_action`, `details`).
3. Your `MCP_*` env vars (`env | grep MCP_`).
4. A `.venv/bin/python -m pytest tests/ -q` summary line.

That's enough to triage 90% of issues without me asking follow-ups.
