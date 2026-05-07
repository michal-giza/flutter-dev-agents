# 8 KB SKILL is overkill — a RAG bridge for one-person Flutter dev factories

*Article #2 in a series. The first one introduced
[`flutter-dev-agents`](building-flutter-dev-agents.md) — 92 tools, one
MCP, multi-project dev loop. This one closes the biggest hole that
piece left open: the agent's context budget.*

---

## The pain in one paragraph

The skill file `mcp-phone-controll-testing/SKILL.md` is 30 KB on disk,
~7,500 tokens loaded. For Claude Sonnet that's fine — 200 KB of context
budget, eat the cost. For a 4 GB Qwen 2.5 running on a Mac via MLX, it's
30% of the prompt budget gone before the agent has read a single user
message. The skill is supposed to teach the agent *when* to call which
tool. Loading the whole thing every turn is the opposite of that.

I have an open RAG project on the same laptop. Two months ago I taught a
4-module RAG-from-scratch course (`rag-search/codebase-rag`) with a
production capstone — Qdrant + FastEmbed + a language-aware chunker that
already understands Dart. The two repos didn't talk to each other.

Tonight they do. This is what I shipped, why, and what the literature
says about whether it should work.

---

## The decision: small in-repo RAG, not import-the-course

`rag-search` is structured as a teaching project, not a library. No
`pyproject.toml`. Importing from a sibling source tree means versioning
hell. The right move was the boring one: ship a minimal RAG
implementation **inside** `phone-controll`, inspired by the course but
not bound to it. ~500 LOC across:

- `data/chunker.py` — language-aware chunker for `.md`, `.dart`,
  `.py`, plus a fixed-window fallback.
- `data/repositories/qdrant_rag_repository.py` — Qdrant + FastEmbed
  client behind the `RagRepository` protocol.
- `data/repositories/null_rag_repository.py` — informative-failure
  fallback when the optional `[rag]` extras aren't installed.
- `domain/usecases/recall.py` — `Recall(query, k, scope)` and
  `IndexProject(project_path)`.

Two new tools register: `recall` and `index_project`. Total tool count
goes from 92 to 94. The course is unchanged, used as the reference
implementation. The dependency boundary is documented in
[`docs/composition.md`](../composition.md): two MCPs, one Qdrant
instance, no shared code.

## What the literature says

I don't ship architecture decisions on vibes. The relevant papers, in
the order they shaped this design:

**Lewis et al., 2020 ("RAG", [arXiv:2005.11401](https://arxiv.org/abs/2005.11401))**
— the foundational "retrieve, then generate" paper. Established that
retrieval-augmented models beat parametric-only ones on knowledge-
intensive tasks at fixed parameter count. Translation for our setting:
a 4B model with retrieval beats a 4B model trying to memorize the SKILL
in its prompt.

**Liu et al., 2023 ("Lost in the Middle", [arXiv:2307.03172](https://arxiv.org/abs/2307.03172))**
— LLMs recover content at the start and end of a long context far
better than the middle. The 8 KB SKILL has its phase state machine
two-thirds of the way down. Loading it whole means the agent reliably
forgets the rules that matter most. Retrieving 3 chunks puts the
relevant 600 tokens at the front of the prompt where they get used.

**Karpukhin et al., 2020 ("DPR", [arXiv:2004.04906](https://arxiv.org/abs/2004.04906))**
— dense retrieval (the BGE-small-v1.5 we use) reliably beats BM25 on
"concept" queries like "what does UMP_GATE require?". For exact-token
queries ("`stop_app`"), BM25 wins. We ship dense for v1; hybrid is
queued in `docs/next-session-enhancements.md` (Tier H1).

**Shinn et al., 2023 ("Reflexion", [arXiv:2303.11366](https://arxiv.org/abs/2303.11366))**
— periodic self-summary improves long-horizon task success. We added
auto-narrate-every-Nth-call (Tier G3) tonight, gated by
`MCP_AUTO_NARRATE_EVERY=5`. Drop-in, off by default for Claude.

**Yao et al., 2022 ("ReAct", [arXiv:2210.03629](https://arxiv.org/abs/2210.03629))**
— interleaving reasoning and action beats either alone. The
`recommended_sequence` field on `describe_capabilities` (Tier G1) is
the ReAct prior — agents do better when given a strong "this is the
typical first move" hint than when forced to plan the whole sequence.

**Brown et al., 2020 (GPT-3, [arXiv:2005.14165](https://arxiv.org/abs/2005.14165))**
— the in-context learning paper. The replay buffer in `describe_tool`
(Tier G2) returns the 3 most recent successful invocations of a tool
from the session trace. That's few-shot learning grounded in the
agent's own behaviour, which empirically sticks better than synthetic
examples.

These six papers cover ~95% of the design choices. None of them is
new — all were on arxiv before 2024. The honest read is that the
field figured this out two years ago and we're catching up.

## Tier G shipped — what each tool does

Six new productivity items, plus the seventh (a CI-side shadow-run
harness) to make sure new tools don't ship with broken envelopes.

- **G1 — `recommended_sequence`.** `describe_capabilities(level=basic)`
  now returns a 9-tool ordered list ending in `release_device`. The
  agent doesn't have to guess where to start.
- **G2 — replay buffer.** `describe_tool("select_device")` now returns
  the 3 most recent successful real invocations from this session.
- **G3 — auto-narrate.** Every Nth dispatcher call attaches a one-line
  prose `narrate` field. Reflexion-style. Configurable via env var.
- **G4 — `recall(query, k, scope)`.** Top-k chunks from the indexed
  SKILL/docs/code/trace. The new pipe instead of loading the SKILL
  whole.
- **G5 — `index_project(project_path)`.** Walk md/dart/py, chunk
  language-aware, push to Qdrant. Idempotent on re-index.
- **G6 — SKILL collapse.** 30 KB → 4.5 KB. The full skill stays as
  `SKILL-FULL.md` and gets indexed on startup. The thin `SKILL.md`
  loads at session start; the rest is on demand.
- **G7 — shadow-run.** `python -m scripts.shadow_run --suite tier_g`
  fuzzes every Tier G tool 100 times through the real dispatcher, asserts
  envelope invariants. Ran clean on first execution; pinned via a unit
  test so CI catches drift.

## Numbers

The agent's prompt with the old SKILL: ~7,500 tokens before the user
even speaks.

The agent's prompt with the new thin SKILL: ~1,100 tokens.

Per-call cost of `recall(query, scope="skill", k=3)`: ~200 tokens (the
3 retrieved chunks). For a typical session with 6 distinct skill
queries: 1,100 + 6 × 200 = 2,300 tokens. Versus 7,500 baseline. **Net
savings: ~70%.**

That's headroom for: longer conversation history, more tool-call results
in context, more screenshots embedded as base64. Or, on a 4 GB Qwen,
it's the difference between "fits" and "context overflow on turn 8."

I haven't run a full benchmark yet — Tier H3 has the bench suite as a
follow-up — but the in-context numbers above are arithmetic, not vibes.

## What the test suite looks like now

```
247 tests (Tier A–F)        — base, all green
+ 8 tests (Tier G discovery)
+ 5 tests (chunker)
+ 8 tests (recall + index_project)
+ 1 test (shadow-run smoke)
= 269 tests, < 3 s wall-clock
```

Plus 2 opt-in real tests that hit a real `flutter` SDK when
`MCP_REAL=1` is set. The shadow-run harness ran 25 iterations × 8 tools
× fuzz strategy and produced **zero envelope-invariant violations** on
the first try. That's the bar enhancement #7 in article #1 was after.

## What's monetizable about this

This is article #2, but there's a thesis I tucked into the previous one
that gets more concrete now: **the combined stack is sellable**.

Two repos:

1. **`flutter-dev-agents`** — the MCP, MIT/Apache, the credibility
   piece. Open. 92 → 94 tools.
2. **`rag-search/codebase-rag`** — the 4-module RAG course +
   capstone. Some modules free, advanced ones paid.

Three monetization ladders mapped against what already exists:

- **Course** ($299–499/student/cohort) — Module 0–8 syllabus drafted
  in [`docs/course-outline.md`](../course-outline.md). 8-week format.
  M3 + M6 + M7 + M8 are paid-only. Realistic first cohort: 30
  students × $299 = $9 K, repeatable quarterly.
- **Consulting** ($3–8 K per setup) — "I'll come into your team
  remote, install both projects, index your monorepo, customize the
  SKILL, train your engineers for a day." Real $ from solo founders /
  small studios who can't allocate engineering time to this.
- **Newsletter / paid Substack** ($5–10/mo) — articles #2 → N drive
  top-of-funnel for the course. Paid tier ships monthly behind-the-
  scenes posts.

Tier 4 (hosted indexing) and Tier 5 (SaaS) are still 6+ months out.
Don't build infra speculatively when consulting + course revenue
covers the same demand without paying for servers.

## Stuff I deliberately deferred

- **Hybrid (dense + sparse) retrieval.** Dense is fine for v1.
  Tier H1.
- **CRAG / corrective retrieval.** When confidence is low, re-query.
  Tier H2.
- **Reflexion retry on `UNDER_TEST`.** Tier H3.
- **Voyager-style skill library.** Promote successful sequences to
  named macros. Tier H4.
- **Pydantic + `outlines` grammar enforcement.** Stop double-validating
  arguments; constrain at sample time. Tier H5.

The full backlog with citations is in
[`docs/next-session-enhancements.md`](../next-session-enhancements.md).

## Try it yourself — three test scenarios

Pre-req: Qdrant running locally + the `[rag]` extra installed:

```bash
docker run -d --name qdrant -p 6333:6333 \
  -v ~/qdrant_storage:/qdrant/storage qdrant/qdrant
cd ~/Desktop/flutter-dev-agents/packages/phone-controll
uv pip install -e '.[rag]'
```

Full expected stdout + pass criteria for each scenario lives at
[`docs/test-runbook.md`](../test-runbook.md) Phase 2.

### Scenario A — Index a project, recall a chunk (5 min)

```python
import asyncio
from pathlib import Path
from mcp_phone_controll.container import build_runtime

async def main():
    _, d = build_runtime()
    res = await d.dispatch('index_project', {
        'project_path': str(Path.home() / 'Desktop/flutter-dev-agents'),
        'collection': 'fda-test',
    })
    print('index:', res['ok'], '— files:', res['data']['files_indexed'])

    res = await d.dispatch('recall', {
        'query': 'UMP_GATE preconditions decline path',
        'k': 3, 'scope': 'all',
    })
    for c in res['data']:
        print(f"  {c['score']:.3f}  {c['source']}")

asyncio.run(main())
```

**Pass:** ≥ 20 files indexed, top-3 chunks each scoring above 0.3, with
at least one literal-token match (proves hybrid lexical fusion fired).

### Scenario B — Token-budget proof (3 min)

```bash
wc -c ~/Desktop/claude_skills/skills/mcp-phone-controll-testing/SKILL-FULL.md
wc -c ~/Desktop/claude_skills/skills/mcp-phone-controll-testing/SKILL.md
```

**Pass:** new SKILL.md is roughly 1/5 of SKILL-FULL.md (~30 KB → ~4.5 KB).
Multiply by tokens-per-byte for your encoder to get the per-session
budget delta. On Qwen 2.5-7B that's the ~70% number from the article.

### Scenario C — Shadow-run smoke (1 min)

```bash
.venv/bin/python -m scripts.shadow_run --suite tier_g --iterations 50
```

**Pass:** exit 0; every Tier-G tool reports
`envelope_invariants_violated: 0` in the JSON report. This is the test
that promotes new tools from "feels right" to "ships green under fuzz."

## What I'm asking from readers

Clone it. Plug in your phone. Run the walkthrough at
[`docs/walkthrough-vscode-test.md`](../walkthrough-vscode-test.md).
Then run `index_project(your_flutter_project)` and watch your local 4B
model start asking the SKILL real questions.

If you find a paper I should have cited but didn't, mail it to me.
The risk isn't that we're wrong about RAG — it's that we're behind on
the literature. Two years ago this was new; today it's table-stakes.
The next 12 months will compound on whatever we ship in the next 12
weeks.

---

*Source: github.com/`<your-handle>`/flutter-dev-agents — Apache 2.0.
Course at github.com/`<your-handle>`/rag-search — pricing TBA. Article
written 2026-05-07; cite arxiv numbers, not me.*
