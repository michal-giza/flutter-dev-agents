# Decision: defer the topic-split of `tool_registry.py` (B2) — third time

**Status**: deferred (explicitly, with rationale)
**Date**: 2026-05-17
**Mentioned in**: code reviews 2026-05-15, 2026-05-17 (twice), 2026-05-17-deep, enterprise audit

## Context

`presentation/tool_registry.py` is ~2200 LOC of `build_registry()`
which constructs ~109 `ToolDescriptor(...)` literals in a single
long list. The first review proposed splitting it into
`presentation/descriptors/devices.py`, `descriptors/ui.py`,
`descriptors/dev_session.py`, etc., one file per logical area.

The split would have:
- ~6-8 new module files
- ~109 descriptor literals moved across them
- All their use-case imports moved alongside
- `build_registry()` reduced to a `[*build_devices(uc),
  *build_ui(uc), ...]` aggregator
- Same external API; pure refactor

## Why deferred (again)

The work has been on every backlog list for two weeks and keeps
getting passed over. The reasons compound:

1. **Risk-vs-reward is bad in a multi-fix commit.** Moving 109
   descriptor literals across 6 files means 109 chances to flip an
   argument, drop an annotation, or break an import. Tests +
   contract snapshot would catch most regressions, but the LOC
   moved (~1800) plus the import-rewiring surface (~50+ imports to
   move alongside) is risk we wouldn't accept for a feature.

2. **The original pain point is mostly solved.** The
   `descriptors/_shared.py` + `_param_builders.py` extraction
   (commit `89ddd7d`) already pulled the 700-LOC mechanical mass
   off `tool_registry.py`. What's left in the file is ~1500 LOC of
   call sites — they're readable, just numerous. The marginal
   return on splitting them further is real but small.

3. **Best done as a dedicated focused session.** The kind of
   work that warrants its own merge: review every descriptor,
   regroup, update the contract snapshot, walk every test that
   touches the registry. Co-mingling it with feature work makes
   review harder and risk worse.

4. **Onboarding-friction claim doesn't show up in practice.** The
   stated value was "easier to navigate for new contributors." So
   far the new tools that have shipped (`compress_png`,
   `start_wda_on_simulator`, `list_missing_widget_keys`) have all
   been added cleanly by finding the right anchor and editing
   inline. The file is big, not confusing.

## When to revisit

Real triggers (any one of these):
- A new contributor specifically reports navigation difficulty in
  PR review.
- The file exceeds 3000 LOC (currently 2200).
- A descriptor refactor is needed that touches > 10 existing tools
  (we'd have to walk the file end-to-end anyway).
- We adopt a feature that requires per-topic ordering or grouping
  (e.g. category-based MCP `prompts/`).

Non-triggers (don't redo this):
- "It would be cleaner." (yes, but small return)
- "Senior code reviewer flagged it." (it's been flagged; we've
  evaluated and deferred — that's a closed decision until a real
  trigger above fires)

## What was done instead

The previous Tier 0 / Tier 1 work (commits `84be6ec`, `3c80f75`,
`def7377`, `56ba3fc`, `dde420e`, and the enterprise batch) shipped
~250 LOC of value that closes more user-visible gaps than this
refactor would. Opportunity cost was the right call.

This decision is logged so the next review doesn't open the same
discussion with no context.
