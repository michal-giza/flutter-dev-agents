# Next-session enhancements

The list of work that's been scoped, isn't blocking anything tonight,
and should land in a future batch. Carved out of conversation history,
the article #1 / #2 backlog, and the arxiv literature review.

Format per item: a short title, why it matters, the rough shape of the
change, and the paper/source the design is grounded in (if any).

---

## Tier H — agent literacy (next batch)

### H1. Hybrid retrieval (dense + sparse) on `recall`

**Why.** Dense BGE-small handles "concept" queries (`UMP gate
preconditions`) well; BM25 wins on exact-token queries (`stop_app`,
`SerialNumber`). Hybrid retrieval is empirically dominant for both
(Karpukhin et al., 2020, [arXiv:2004.04906](https://arxiv.org/abs/2004.04906); Reichman & Heck,
2024, hybrid-RAG survey). **Shape.** Add `qdrant-client` BM25 sparse
index alongside the dense vectors; combine via reciprocal-rank fusion
(RRF). One method, one index.

### H2. CRAG (corrective RAG) on top of `recall`

**Why.** The agent currently trusts `recall` results blindly. CRAG
adds a self-grading step: if retrieved chunks score below a threshold,
fall back to a different scope or to web search (Yan et al., 2024,
[arXiv:2401.15884](https://arxiv.org/abs/2401.15884)). **Shape.** Wrap `Recall` in
`RecallWithGrade` that computes a relevance score and re-queries with a
different scope when the score is low. Article enhancement #6 ties in.

### H3. Reflexion-style retry loop in plan walker

**Why.** When `UNDER_TEST` fails, the plan walker today emits
`VERDICT_BLOCKED`. Reflexion (Shinn et al., 2023,
[arXiv:2303.11366](https://arxiv.org/abs/2303.11366)) shows a self-critique-and-retry
loop dramatically improves task success on long-horizon agent tasks.
**Shape.** Add a `_reflect` phase before `VERDICT_BLOCKED` that asks
the agent to write one sentence on why it failed, then attempts up to
2 retries with the new context. Gated by `MCP_REFLEXION_RETRIES`.

### H4. Voyager-style skill library

**Why.** Voyager (Wang et al., 2023,
[arXiv:2305.16291](https://arxiv.org/abs/2305.16291)) showed lifelong-learning
agents accumulate a per-task skill library that compounds over time.
We have a session trace; we don't yet promote successful sequences to
**reusable named skills**. **Shape.** Add `promote_sequence(name,
trace_slice)` that captures a successful tool sequence as a named
"macro" the agent can invoke. Lives in SQLite alongside the trace.

### H5. Pydantic + `outlines`-style grammar enforcement

**Why.** Article enhancement #2. Today the dispatcher coerces loose
types ("true" → True). Stronger: constrain the model's output at the
sampling layer so it can only emit schema-valid arguments
(Willard & Louf, 2023, "Efficient guided generation",
[arXiv:2307.09702](https://arxiv.org/abs/2307.09702)). **Shape.** A
`adapters/openai_compat.py` extension that ships JSON Schemas to
clients implementing OpenAI's `tools` field with `strict: true`. Stop
double-validating; trust the sampler.

---

## Tier I — productization (after Tier H)

### I1. Tool-usage benchmark suite

**Why.** Tool-LLM benchmarks (Qin et al., 2023,
[arXiv:2307.16789](https://arxiv.org/abs/2307.16789)) measure agent quality on a
fixed set of tasks. We don't have a benchmark; we should. **Shape.**
A `bench/` directory with 20 representative tasks (run a Patrol test,
hot-reload after edit, retrieve UMP guidance, scaffold a feature),
each with a deterministic expected envelope. Run nightly against
`qwen2.5:7b`, `qwen2.5:14b`, Claude Haiku, Claude Sonnet. Publish the
table.

### I2. CI Docker image

**Why.** Already noted in the umbrella plan as deferred. Now warranted:
the course publishes well in a container; consulting clients want a
hand-off they can run in GitHub Actions. **Shape.** Already specced —
`packages/phone-controll/docker/Dockerfile.ci`, headless Linux x86_64,
Android emulator + Flutter + Patrol + MCP. ~1 day of work.

### I3. Promote `mcp-rag-bridge` to its own package

**Why.** If hybrid + CRAG + grammar work lands, the RAG layer in
`phone-controll` becomes substantial. Tracking surfaces drift between
the course and the production code. **Shape.** Move `data/chunker.py`,
`data/repositories/{qdrant,null}_rag_repository.py`, and
`domain/usecases/recall.py` into `packages/mcp-rag-bridge/`. Re-export
from `phone-controll`. Versioned independently.

### I4. Indexing watcher

**Why.** `index_project` is one-shot. For real usage, the agent wants
the index to track edits. **Shape.** Add a thin CLI
`scripts/watch_index.py` that uses `watchdog` to re-index on file
modification, debounced. Optional dep.

---

## Tier J — research bets (when time permits)

These are 1–3 day investigations, not batches to ship blindly.

### J1. ReAct vs Plan-and-Solve for the dev loop

ReAct (Yao et al., 2022, [arXiv:2210.03629](https://arxiv.org/abs/2210.03629))
interleaves reasoning and action. Plan-and-Solve (Wang et al., 2023,
[arXiv:2305.04091](https://arxiv.org/abs/2305.04091)) plans the full sequence
upfront. We've leaned ReAct; when the agent has a strong prior (the
`recommended_sequence`, the SKILL), Plan-and-Solve may dominate. Run
both styles against I1's bench, publish results.

### J2. Long-context vs RAG ablation

Now that `recall` exists, we can measure: does feeding the whole
SKILL beat retrieving 3 chunks? Likely no on 4B — but it's testable.
"Lost in the Middle" (Liu et al., 2023,
[arXiv:2307.03172](https://arxiv.org/abs/2307.03172)) predicts RAG wins. Confirm
the prediction on our specific tasks; the answer becomes part of the
article.

### J3. Tree-of-Thoughts on plan validation

Tree-of-Thoughts (Yao et al., 2023,
[arXiv:2305.10601](https://arxiv.org/abs/2305.10601)) explores multiple branches
before committing. `validate_test_plan` could speculatively branch on
"what if this driver were `flutter_test` vs `patrol_test`?" and pick
the branch that scores highest before suggesting the fix. Probably
overkill, but worth measuring.

---

## Article queue

- **Article #2 (drafted in Tier G):** "8 KB SKILL is overkill — a RAG
  bridge for one-person Flutter dev factories." References Lewis 2020,
  Liu 2023, Karpukhin 2020.
- **Article #3 (Tier H):** "Reflection, retry, and corrective RAG —
  what ReAct alone can't do." References Shinn 2023, Yan 2024.
- **Article #4 (Tier I):** "How to benchmark your own agent stack."
  References Qin 2023; ToolBench, MetaTool benchmark methodology.
- **Article #5 (Tier J):** "ReAct vs Plan-and-Solve, measured against
  a real Flutter factory."

---

## Notes on the literature search

Re-check arxiv quarterly for these specific search terms to stay
current:

- "tool-augmented LLM" / "tool calling agent"
- "retrieval-augmented agent"
- "skill library lifelong learning"
- "code agent benchmark"
- "small language model 4B agent"
- "MCP / Model Context Protocol"

Citation-graph crawl from any new paper you read; track what cites
Toolformer, ReAct, Voyager. Most production-relevant work now sits at
the intersection of those three threads.
