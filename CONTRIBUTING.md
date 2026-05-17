# Contributing to flutter-dev-agents

Thanks for your interest! This document is the short version. Long
version is the codebase itself — every architectural decision lives
in `docs/adr/` and every batch of changes has a commit-message
rationale.

## Quick start

```bash
git clone https://github.com/michal-giza/flutter-dev-agents.git
cd flutter-dev-agents
./scripts/install.sh        # one-shot setup: brew deps + venv + uiautomator2 init
cd packages/phone-controll
.venv/bin/pytest -q          # 466+ hermetic tests, ~15 s
.venv/bin/ruff check src tests scripts
```

## Pre-commit hooks (recommended)

```bash
uv pip install pre-commit
pre-commit install
```

Runs ruff + fast pytest + tool-catalogue staleness check on every
commit. Same gates as CI — if local pre-commit passes, the PR will too.

## Branch + commit conventions

- Branch name: `feature/short-description` or `fix/short-description`
- Commit format: conventional commits where natural —
  `feat(scope): …`, `fix(scope): …`, `docs: …`, `test: …`, `refactor: …`
- One concern per commit. We squash-and-merge at the PR boundary, so
  intermediate commits don't need to be perfect, but the message of
  the squash commit (= PR title + body) does.
- Co-author yourself: if you used Claude / Cursor / Copilot in a
  meaningful way, add the `Co-Authored-By:` trailer.

## What good PRs look like

Look at the recent commit history for examples. Every load-bearing
change has:

1. **A reason in the commit message** — what symptom drove this, not
   just "what I did."
2. **Tests** that pin the new behaviour. Specifically:
   - Per-tool tests in `tests/unit/test_<tool>.py`
   - Snapshot/contract tests update via `UPDATE_CONTRACT=1 pytest …`
     when the public tool surface changes.
3. **No ruff errors** (`.venv/bin/ruff check src tests scripts`).
4. **No coverage regression** on the changed file(s).
5. **Docs touched** when a user-facing thing changes — the walkthrough,
   the article, the relevant ADR.

## Adding a new tool — the recipe

1. Domain layer: write the use case in `src/.../domain/usecases/<area>.py`.
   Use `BaseUseCase[Params, Result]`. Result type must be a frozen
   dataclass.
2. Container: wire it in `container.py` (one new field in the use-cases
   block at the bottom).
3. Registry: add to the `UseCases` dataclass + a `ToolDescriptor(...)`
   call in `build_registry()` in `presentation/tool_registry.py`. Add
   the param-builder in `presentation/descriptors/_param_builders.py`.
4. Annotations: the centralised classifier in
   `descriptors/_shared.py:default_annotations()` will best-effort
   classify; add to the explicit lists if your name doesn't follow the
   established prefixes.
5. Tests: `tests/unit/test_<tool>.py` — at minimum a happy path, a
   guard path, and a failure-envelope path.
6. Refresh the contract snapshot:
   `UPDATE_CONTRACT=1 .venv/bin/pytest tests/unit/test_tools_list_contract.py`
7. Regenerate the docs/tools.md catalogue:
   `MCP_QUIET=1 .venv/bin/python -m scripts.generate_tool_catalogue`

## Adding a new platform / framework

See `docs/adding_a_framework.md` and `docs/adding_an_mcp.md`. Both
codify the recipes so the diff stays small.

## Test layout

- `tests/unit/` — hermetic, no real CLI, < 100 ms per test
- `tests/integration/` — multi-component, still uses fake clients
- `tests/integration_real/` — opt-in real-toolchain (`MCP_REAL=1`)
  and real-device (`MCP_REAL_DEVICE=1`) tests
- `tests/agent/transcripts/` — JSON replay transcripts for agent-loop
  regression testing

## Security-impacting changes

Anything touching `domain/path_guard.py`, `presentation/image_safety_net.py`,
the subprocess-spawning helpers, or `notify_webhook` allowlist logic
needs:

- An update to the relevant ADR (or a new one in `docs/adr/`)
- A tripwire test that breaks if the guard is silently weakened
- A mention in the PR description so reviewers know to look

## Code of conduct

Be excellent. Disagreement is fine; condescension isn't. Issues that
violate this get closed without engagement.

## Reporting a security vulnerability

See `SECURITY.md`. Don't open a public issue.

## License

By contributing, you agree your contributions are licensed under the
Apache License 2.0 (`LICENSE` at repo root). No separate CLA — the
inbound license is the outbound license.
