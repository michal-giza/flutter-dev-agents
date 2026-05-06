# Article #5 — Benchmarking your own agent stack: 10 tasks, 4 models, one honest table

**Target word count:** ~3000. **Audience:** anyone running an agent
stack who hasn't yet measured how much each piece actually helps.

## Outline

### Cold open (300 words)
"My agent works." That's a statement nobody can falsify until you put
it on a bench. ToolBench (Qin et al., 2023) is great but enormous.
Our 10-task `bench/run_bench.py` runs in 3 seconds against a fake stack
and ~3 minutes against a real local LLM. Small enough to run on every
PR. Specific enough to catch real regressions.

### Why we built our own bench instead of using ToolBench (500 words)
- ToolBench measures "can the agent use any tool" — too broad.
- Our bench measures "can the agent succeed at the canonical tasks
  this stack exists to solve" — narrow, and that's the point.
- The ten tasks (cite each):
  T01–T03: discovery + preflight
  T04: dev session lifecycle
  T05: clean-and-screenshot
  T06: graceful degradation when extras missing
  T07: rate-limit honoured
  T08: corrected_example on bad args
  T09: trace surface
  T10: skill library round-trip

### The harness (400 words)
- `bench/tasks.json` is the contract — adding a task means adding to
  this file plus, if needed, fake-fixture support.
- Per-call expectations: `ok`, `next_action`, `data_type`,
  `data_min_len`. Cheap, fast, deterministic.
- JUnit XML output → consumable by any CI runner.
- The CI gate: `tests/unit/test_bench_smoke.py` ensures nobody can
  ship a regression that breaks an existing task without explicit
  acknowledgement (delete the task, justify it in the PR).

### The four-models comparison (800 words)
- Claude Sonnet (200K ctx, baseline).
- Claude Haiku (faster, cheaper).
- Qwen 2.5-7B (local, MLX).
- Qwen 2.5-14B (local, requires more RAM).
- Per-task pass rate per model.
- Headline finding (TBD when actually run): probably Sonnet is 100%,
  Haiku ~95%, Qwen-14B ~85%, Qwen-7B ~75%. Specific failure modes
  documented per model.

### The Reflexion + CRAG ablation (400 words)
- Same 10 tasks × {baseline, +Reflexion=2, +CRAG, +both}.
- Per-condition pass rate.
- Honest reporting of where each helps and where it doesn't (Tier J1
  empirical data drops in here).

### What surprised us (300 words)
- TBD when run. Likely candidates:
  - Hybrid retrieval (H1) probably matters most when the query
    contains code identifiers; matters less for natural-language
    skill queries.
  - The strict-schema flag (H5) probably gives Qwen-7B a bigger lift
    than Qwen-14B.
  - The rate limiter probably catches more 4B model loops than
    expected.

### How to add a task to the bench (200 words)
- One JSON entry, one expected envelope shape.
- Run locally: `python -m bench.run_bench --tasks T11`.
- PR includes the task + a comment explaining "what regression would
  this catch."

### What's next (100 words)
Articles #1–5 wrap a complete narrative: ship the MCP, bridge with
RAG, add reflection/CRAG/skill library, measure. After this, the
backlog is research-grade work — Tree-of-Thoughts, real LLM-based
graders, the Flutter Web demo, the cohort launch.

### References
- Qin et al., 2023 — ToolBench,
  [arXiv:2307.16789](https://arxiv.org/abs/2307.16789).
- Cormack et al., 2009 — RRF (cited from H1 work).
- Liu et al., 2023 — Lost in the Middle (RAG ablation context).

## Distribution
- **Blog.** Title: "Benchmarking your own agent stack."
- **HN.** Title: "10 tasks, 4 models, one honest table."
- **r/LocalLLaMA.** Title: "How I measure my 4B agent stack."
- **Substack paid.** Full per-task per-model breakdown table.
