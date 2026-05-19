# Scenarios — fully-worked end-to-end examples

Each scenario is a complete copy-paste-ready story:
**setup → prompt → expected output → variations → cleanup**.

Pick the one closest to what you're trying to do; adapt the
package IDs / device serials / project paths.

| # | Scenario | Time | Tier |
|---|---|---|---|
| [01](01-five-minute-smoke.md) | Five-minute morning smoke test | 5 min | BASIC |
| [02](02-polish-locale-repro.md) | Reproduce a Polish-locale permission bug | 10 min | BASIC |
| [03](03-multi-project-debug-loop.md) | Multi-project debug loop, 3 phones in parallel | 15 min | INTERMEDIATE |

## What to expect from these

Unlike the API docs, scenarios show **the whole flow**:

- The exact prompt to paste.
- The expected per-tool output (timings, envelopes, paths).
- What to read in the response and why it matters.
- Common variations + when to use each.
- Failure modes you might still hit + how to recover.

## Authoring guidelines (if you write a new one)

- **One concrete user**, **one concrete app**, **one concrete
  device** — don't write "your device may vary." Future-you and
  every reader will be grateful for the concreteness.
- **Numbered tool sequence** in the prompt. Free-form prompts
  vary too much to be reproducible.
- **Expected output as code blocks**. Real timings, real paths,
  real envelope shapes.
- **At least one "what goes wrong" subsection**. Failure recovery
  is half the value.
- **Reference the BASIC / INTERMEDIATE tier each scenario needs**
  — readers should know whether they have to set `MCP_TOOL_TIER`.

See [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md) for PR
mechanics.

## What's missing? (high-value gaps if you want to contribute)

- iOS-specific scenarios (iOS sim with sandboxed file paths, real
  iPhone with `--rsd` routing).
- AR scenarios (camera-calibration loop, marker-detection
  validation).
- CI scenarios (running a YAML plan from GitHub Actions with
  artifact retention).
- Local-LLM scenarios (`agent_loop_small_llm.py` driving a
  Patrol test against an emulator on a 4 GB model).

PRs welcome.
