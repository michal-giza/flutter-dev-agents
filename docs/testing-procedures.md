# Testing procedures — `flutter-dev-agents`

This document is the testing protocol for the monorepo. Read it before
opening a PR or writing new tests. The same protocol governs human-written
code AND code produced by autonomous agents — small models in particular
need a deterministic test bar to chase.

## Test taxonomy

We run four flavours of tests, each gated differently:

| Flavour              | Path                              | Default | Wall-clock |
| -------------------- | --------------------------------- | ------- | ---------- |
| Unit                 | `tests/unit/`                     | always  | < 1s       |
| Integration (faked)  | `tests/integration/`              | always  | < 1s       |
| Agent replay         | `tests/agent/`                    | always  | < 1s       |
| Real device / SDK    | `tests/integration_real/`         | opt-in  | minutes    |

Default `pytest` runs only the first three (≈ 250 tests, < 1 second on a
laptop). Setting `MCP_REAL=1` opts into the slow real-SDK suite, intended
for human-driven validation runs (or CI with a Linux+emulator job).

## What each flavour proves

### Unit (`tests/unit/`)

Each domain use case + repository protocol is exercised with fakes from
`tests/fakes/`. Catches:

- Result/Err contract changes — `next_action` field present, error code
  stable, details dict shape.
- Argument parser regressions (e.g. parsing real `flutter test`
  JSON-reporter output).
- Pure-function correctness for vision math, JSON-RPC framing, plan
  semantics.

The bar is **100% coverage for `domain/usecases/`** (every Use Case has at
least one unit test). Repositories that wrap CLIs are covered indirectly
via parser tests.

### Integration with fake repos (`tests/integration/`)

End-to-end exercises the dispatcher with a fully-faked repo graph. Catches:

- Tool registration drift — an added Use Case must appear in the
  `expected_tool_names` set or the test fails.
- Envelope shape regressions — every tool must return either
  `{"ok": True, "data": ...}` or
  `{"ok": False, "error": {"code", "message", "next_action", "details"}}`.
- Argument coercion (`"true"` → `True`) for small-LLM resilience.

### Agent transcript replay (`tests/agent/`)

JSON-encoded transcripts of typical agent sessions, dispatched against a
fake runtime. Each step asserts envelope invariants — not exact equality,
but the load-bearing fields (`ok`, `error.code`, `error.next_action`,
`data_truncated`).

This is how we pin agent behaviour against drift. If the SKILL ladders or
the dispatcher changes shape, the transcripts catch it before a small-LLM
agent does.

The provided transcripts:

- `01_basic_smoke.json` — the canonical 4B-LLM checklist
- `02_small_llm_self_correction.json` — argument coercion + corrected_example
- `03_dev_session_loop.json` — full dev-iteration loop

Add a new transcript whenever you ship a new SKILL section or a new
agent-facing flow. They're cheap and they pay for themselves the first
time you change one of the underlying tools.

### Opt-in real (`tests/integration_real/`)

The fixture `tests/fixtures/sample_flutter_app/` is a minimal Flutter
project. The opt-in tests run **real** `flutter`, `dart`, `git` against
it.

Run with:

    MCP_REAL=1 pytest tests/integration_real

Add `MCP_REAL_DEVICE=1` to also exercise device-attached paths (install,
screenshot, etc). That requires a running emulator or attached phone.

These tests are slow and environment-dependent. They live outside the
main suite on purpose.

## Local development workflow

1. Make a code change.
2. Run `pytest -x tests/unit tests/integration tests/agent` — should be
   < 1s. If anything fails, fix before continuing.
3. If the change touches an agent-facing surface (tool descriptions,
   ladders, envelope shape), run the agent transcripts:
   `pytest tests/agent`.
4. Periodically (before a release, or after a non-trivial refactor) run
   `MCP_REAL=1 pytest tests/integration_real`.
5. Run `pytest --cov` once before the PR to confirm `domain/usecases/` is
   fully covered.

## Tests we DON'T write

- Tests against real third-party APIs (Firebase, AdMob) — those go
  behind feature flags and are validated manually.
- UI snapshot tests of generated PNGs — use `compare_screenshot`'s
  golden-comparison instead, which lives at the use-case layer.
- Performance benchmarks — `pyperf` is great but the dev-loop variance
  is dominated by emulator warm-up; benchmarks live in a separate repo
  if/when needed.

## Adding a Use Case — testing checklist

1. Write the Use Case under `domain/usecases/` with a `dataclass(frozen)`
   params and a `Result[T]` return.
2. Add a unit test covering: success, the most likely failure mode, and
   the "wrong arguments" path (assert `next_action == "fix_arguments"`
   and `details.corrected_example` is shaped correctly).
3. Wire it into `presentation/tool_registry.py` with a tool descriptor.
4. Wire it into `container.py` and the integration test's
   `_build_fake_dispatcher`.
5. Add the tool name to the integration test's `expected_tool_names` —
   this one fact catches every wiring mistake.
6. If it's a new agent-facing flow, add it to a transcript.

## Adding an agent-facing tool — the bar

- BASIC tools: description ≤ 35 words. Enforced by
  `tests/unit/test_tool_description_audit.py`.
- All tools: description ≤ 70 words.
- Required: at least one path returns `next_action="fix_arguments"` with
  `details.corrected_example` populated, OR the tool is documented as
  not validating arguments.
- Long outputs: if the data field can exceed ~8 KB, document the
  `data_truncated` semantics in the description.

## CI

GitHub Actions runs the default suite on every PR (Linux, macOS,
Python 3.11). The opt-in real suite runs on a separate cron-driven job
on a self-hosted macOS runner with a connected emulator. See
`.github/workflows/ci.yml` (umbrella) and `docker/Dockerfile.ci` for the
containerised future.

## Why this matters for autonomous-agent workflows

Agents don't read READMEs. They read tool descriptions, error envelopes,
and example outputs. The tests above pin those *exact* surfaces:

- **Tool descriptions** — the audit ensures they're concise.
- **Error envelopes** — every failure carries `next_action`, validated
  per Use Case.
- **Examples** — every InvalidArgumentFailure carries
  `details.corrected_example`, validated per Use Case.
- **Transcripts** — the canonical "this is what a session looks like"
  document, executable.

If you change one of these things, the tests turn red before the agent
turns confused.
