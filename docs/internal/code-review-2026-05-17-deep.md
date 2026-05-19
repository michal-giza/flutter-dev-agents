# Deep code review — 2026-05-17 (research-backed)

Third pass after the May 2026 hardening batch + Tier B closures. The
first two reviews (`code-review-2026-05-15.md`, `code-review-2026-05-17.md`)
scored the system on what's there. This one scores it against what
should be there given the current MCP spec (`2025-11-25`) and
patterns from production MCP servers in mid-2026.

The brutal version. Honest about gaps the previous reviews missed
because they were calibrated on our own roadmap, not the external
state of the art.

## What we measured

- Internal audit: file sizes, exception-handler hygiene, coverage on
  critical paths, observability call sites, signal handling,
  streaming-response support, MCP-capability advertisement.
- External research: current MCP spec (`2025-11-25`), Anthropic's
  `Writing effective tools for AI agents`, Block's MCP playbook,
  Cursor's tool-count ceiling, IBM mcp-context-forge fuzz stack,
  Drizz/arconsis on Flutter-MCP token cost.

## Headline findings

### 1. We're one spec revision behind on three things that matter

| MCP feature | Spec since | Our support | Cost of not having it |
|---|---|---|---|
| `outputSchema` + `structuredContent` on tools | `2025-06-18` | none | agent parses `{ok, error, next_action}` from free-form JSON every call |
| Tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`, `title`) | `2025-06-18` | none | hosts can't gate destructive ops; safety prompts downgraded |
| `resources/` API for addressable artifacts | spec since `2024-11-05`, ubiquitous by `2025-11-25` | none | screenshots returned as paths agents have to re-Read; goldens have no canonical URI |

These aren't theoretical. Anthropic's `Writing effective tools` guide
explicitly recommends `readOnlyHint` for tools like `take_screenshot` and
`destructiveHint` for `tap`/`swipe`/`boot_simulator`. We have neither.
A host that respects the hints will downgrade to weaker safety prompts
on every call.

### 2. We pass the tool-count ceiling some hosts enforce

Cursor caps the model's tool surface at **40 tools** — anything past
that is silently dropped before reaching the LLM. We currently expose
**108 tools**. Claude Code doesn't cap (yet), but the pattern is
moving toward limits.

Anthropic's guidance is explicit: *"More tools don't always lead to
better outcomes. Build a few thoughtful tools targeting specific
high-impact workflows."* Block reduced their Linear MCP from 30+
thin wrappers to 2 flexible query tools and measured better agent
performance.

Our 108 is honest — every tool earns its keep — but the surface needs
to be **navigable**, not flat. The right move is either:
- **Sub-server split** by workflow (`phone-driver`, `phone-tests`,
  `phone-recording`) so each is under 40,
- **Or** a thin core (12-18 BASIC tools) + a `list_advanced_tools`
  meta-tool that streams the full surface only when asked.

The `set_agent_profile`/`describe_capabilities(level=...)` system we
already have is the right shape — we just don't use it aggressively
enough. BASIC should be ~12 tools, not the current ~24.

### 3. Observability infrastructure exists but is dead code

`src/mcp_phone_controll/observability.py` exposes `emit(event, level,
**fields)` with JSON-line output gated on `MCP_LOG_FORMAT=json`. It
is called **0 times** across `src/`. Every operational signal — tool
dispatch start/end, latency, failures — is invisible.

Compare to current state-of-the-art: structured JSON logs with
session/trace IDs is the floor for production MCP servers
(systemprompt.io playbook, Zeo observability guide). MCP also has a
native `logging/` notification primitive (server → client) for
host-routed telemetry that we don't emit.

### 4. The actual stdio entry was 0% tested until 15 minutes ago

`presentation/mcp_server.py` — the 37-LOC file every real session
talks through — was untested. Now at 100% (5 tests, shipped this
session). But the fact that it took two reviews to notice is the
finding: coverage gates lie when they're measured at the wrong
boundary.

### 5. No SIGTERM handler. Orphaned subprocesses are real.

We spawn `flutter run --machine`, `xcodebuild test-without-building`,
`pymobiledevice3 ...` — all long-lived children. If the MCP process
dies abruptly (Claude Desktop crash, Mac sleeps, parent kill), these
get orphaned. Device locks also leak — `force_release_lock` exists
but only the user can call it after the fact.

Production MCPs install a SIGTERM/SIGINT handler that:
1. Stops accepting new dispatches
2. Drains in-flight tool calls (or cancels them with a timeout)
3. Releases all device locks held by this session
4. Terminates spawned subprocesses
5. Flushes pending logs
6. Exits cleanly

We do none of this.

### 6. Path-traversal guard exists on `compress_png` only

The `compress_png` guard from the previous batch restricted writes to
known-safe roots. **Eight other path-accepting tools have no equivalent**:
`fetch_artifact`, `install_app(bundle_path)`, `run_patrol_test(test_path)`,
`grep_logs`, `ocr_screenshot`, `compare_screenshot`,
`save_golden_image`, `patch_apply_safe(project_path)`. Most are read-only
so the risk is lower, but a prompt-injected `install_app(bundle_path="/etc/passwd")`
or `grep_logs(path="/Users/<other-user>/.ssh/...")` is the kind of
hole that closes silently if we generalize the `_is_within(child, parent)`
helper.

### 7. Testing technique gaps vs production floor

| Technique | We have | Production floor |
|---|---|---|
| Hermetic unit tests | 433 | ✓ |
| Real-device gated tests | 3 (skipped without flags) | partial — need more |
| Snapshot/contract tests on `tools/list` | none | recommended — Kai Gritun, Block playbook |
| Property-based on input schemas | none | recommended — IBM Schemathesis pattern |
| Fuzz on the dispatcher | none | recommended — IBM RESTler |
| Mutation testing on safety paths | none | recommended for `cap_pngs_in_envelope`, lock release |
| mypy in CI | configured, not run | should be in CI |
| MCP Inspector golden-path smoke | none | recommended |

### 8. Flutter-specific pitfalls research flagged that we don't address

Drizz and arconsis report **30-50% of Flutter QA time spent on selector
maintenance**. We expose `tap_text`, `tap`, `find_element`, `dump_ui`,
`extract_ui_graph`, `ocr_screenshot` — six tools that could matter, but
no tool that surfaces the highest-leverage diagnostic: **"which
widgets in this project are missing semantic keys"**. That's the single
tool a Flutter-driving agent would benefit most from. It's 30 lines.

### 9. `dump_ui` has no `depth` or `visible_only` parameter

Same arconsis report: large-app UI-tree dumps balloon token cost.
Anthropic's tool design guidance: response cap ~25K tokens; our
`dump_ui` returns the full tree. A 4B-context agent (our advertised
support tier) can't survive one `dump_ui` against a real app.

## Scoreboard delta

| Dimension | 2026-05-17 (review #2) | This review | Δ |
|---|---|---|---|
| MCP spec compliance | implicit "good enough" | **2 revisions behind** | regression in perceived state |
| Observability | partial | **dead code** | regression in perceived state |
| Operational maturity (graceful shutdown) | not measured | **none** | new gap |
| Path-safety | `compress_png` only | **8 tools still ungated** | new gap |
| Agent-ergonomics ceiling | unbounded | **108 vs 40-tool host floor** | new gap |
| Tool annotations | not advertised | **missing across all 108 tools** | new gap |

Headline: **we're A− on what we measured, but B+ on what should have
been measured.** The previous reviews graded the system against its own
roadmap, not against the world.

## Ship order (by impact-per-hour)

### Tier 0 — ship today (low risk, high impact)

1. **Tool annotations.** Add `read_only`, `destructive`, `idempotent`,
   `open_world` flags to `ToolDescriptor`. Default values per tool
   based on a one-time audit. Surface in the MCP `tools/list` response.
   ~1 hour including the per-tool annotation pass.
2. **Snapshot/contract test on `tools/list`.** Single test that dumps
   the live tool surface to a JSON fixture and compares; CI fails on
   diff unless the fixture is updated in the same PR. ~30 min.
3. **Generalize the path-traversal guard.** Lift `_is_within` to a
   shared helper, apply to the 8 other path-accepting tools. ~45 min
   including tests.
4. **`dump_ui(visible_only, depth, max_bytes)`.** Default depth 4,
   default `visible_only=true`, hard cap at 20K tokens. ~30 min.
5. **MCP server tests** — already shipped this session (5 tests,
   0% → 100% on `mcp_server.py`).

Total Tier 0: ~3 hours, addresses 5 of the 9 findings.

### Tier 1 — next focused session (high risk OR high cost)

6. **SIGTERM handler.** Drain → release locks → terminate
   subprocesses → flush logs → exit. ~2 hours including a real-kill
   test using `os.kill(pid, signal.SIGTERM)` against a subprocess that
   holds a fake lock.
7. **Wire `observability.emit`** at dispatcher pre/post hooks +
   structured fields (tool_name, duration_ms, ok, session_id). ~1
   hour. Optionally also bridge to MCP `logging/` notification
   primitive.
8. **`outputSchema` on the 18 BASIC tools first**, then expert tier.
   Per-tool dataclass already exists; just need a `to_json_schema()`
   pass. ~3 hours for all 108; ~30 min for BASIC.
9. **Schemathesis fuzz job** on the dispatcher. ~2 hours.
10. **`list_missing_widget_keys` tool** for Flutter-specific
    selector hygiene. ~1 hour. The highest single-tool ROI in this
    list per Drizz's data.

### Tier 2 — defer until users ask

- `resources/` API for artifacts (large refactor)
- `prompts/` API
- `elicitation/create` for missing args
- Streamable HTTP transport upgrade
- OAuth 2.1 (only relevant if exposing remotely)
- Sub-server split for the tool-count ceiling
- Mutation testing (mutmut/cosmic-ray)
- mypy in CI

## Honest answer to "best MCP ever made?"

**Closer than two days ago, still not there.** We've closed the gaps
our own roadmap saw. The next leap requires acting on what the
external world has settled on as table-stakes: tool annotations,
structured outputs, contract tests, graceful shutdown,
observability you can actually grep. None of that is hard. Most of it
is one focused session.

The discipline this review enforces: **calibrate the bar with the
outside, ship the gap, repeat.**

## Sources

The full research bibliography (28 sources) is in the research
agent's findings. Key references for the priority decisions above:

- [MCP Spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)
- [MCP Spec 2025-06-18 Tools (outputSchema + annotations)](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [Anthropic: Writing effective tools for AI agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Block: MCP server playbook](https://engineering.block.xyz/blog/blocks-playbook-for-designing-mcp-servers)
- [Demiliani: Too-many-tools problem (Cursor's 40-tool ceiling)](https://demiliani.com/2025/09/04/model-context-protocol-and-the-too-many-tools-problem/)
- [systemprompt.io: MCP production deployment](https://systemprompt.io/guides/mcp-servers-production-deployment)
- [Drizz: Flutter mobile test automation guide](https://www.drizz.dev/post/flutter-mobile-test-automation-the-complete-guide)
