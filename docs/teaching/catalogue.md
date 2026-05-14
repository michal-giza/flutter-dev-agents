# Title + hook catalogue

Every lesson has a working title and a 1-sentence hook. The hook is
the line that goes on the marketing page. The title is what students
see in the table of contents.

## Naming principles

- **Hook tells the student what they'll do or feel.** Not what the
  lesson is *about*.
- **Title is descriptive, not clever.** Cleverness is for the hook.
- **Numbers in titles when they're concrete.** "The 4 AM Test" not
  "Automated Testing 101."

---

## Flagship: Build a Flutter Dev Factory

### Lesson 1 — The 4 AM Test

> *I have six Flutter apps. Last Tuesday at 4 AM, one of them ran a
> test, captured a screenshot, and posted to Slack — while I slept.
> Here's how, in 90 minutes.*

- **Audience prerequisite**: Flutter + Python basics, no MCP knowledge.
- **Big idea**: A factory is a set of small composable tools an agent
  drives. By the end of this lesson the student has one tool wired
  to Claude Code and can call it.
- **Production deliverable**: A `take_screenshot` tool implemented
  end-to-end (use case, descriptor, dispatch). The full flutter-dev-
  agents repo is the reference; the student builds a 50-line subset
  themselves.
- **Knowledge citations**: MCP spec (modelcontextprotocol.io), Karpathy
  "build the production thing" framing, our own
  `src/mcp_phone_controll/domain/usecases/observation.py`.

### Lesson 2 — Boundaries that survive an unreliable narrator

> *The LLM will hallucinate. Your codebase doesn't have to bend to
> accommodate that. Here's how layers help.*

- **Big idea**: Clean Architecture isn't dogma — it's defense against
  unreliable callers. The agent is the unreliable caller.
- **Production deliverable**: Refactor Lesson 1's tool into a 3-layer
  Use Case + Repository + Descriptor split. Run identical behaviour.
  Show diff between "all in one file" vs. "layered."
- **Knowledge citations**: Clean Architecture (Martin, 2017); our
  `docs/adr/0002-middleware-chain.md`.

### Lesson 3 — When the agent is wrong

> *Half of agent debugging is reading error messages the agent
> couldn't act on. `next_action` fixes that.*

- **Big idea**: Result/Err with a `next_action` field turns every
  failure into a structured recovery hint the agent can switch on.
- **Production deliverable**: Add 3 failure modes to Lesson 2's tool.
  Watch the agent recover from each.
- **Knowledge citations**: Railway-oriented programming (Wlaschin,
  2014); ReAct (Yao et al., 2022, arXiv:2210.03629); our
  `src/mcp_phone_controll/domain/failures.py`.

### Lesson 4 — The device is a singleton, your sessions are not

> *Two Claude windows + two Galaxy S25s + two projects. They don't
> step on each other because of one file: a device lock.*

- **Big idea**: Filesystem-level device locks let N agents share M
  devices safely. Cross-process state without a daemon.
- **Production deliverable**: A working 2-session multi-project demo.
  Two Claude windows, two locks, two screenshots — no collision.
- **Knowledge citations**: `O_EXCL` file locking (Linux man page),
  our `src/mcp_phone_controll/data/repositories/filesystem_device_lock_repository.py`.

### Lesson 5 — Patrol-first testing

> *I shipped a Polish-locale test that broke on the first iPhone
> someone tested it on. Here's why that won't happen again.*

- **Big idea**: Tests against display strings break the moment your
  user changes language. Tests against widget Keys don't.
- **Production deliverable**: Convert a `tap_text` test to a Patrol
  test; demonstrate locale-switching that doesn't break it.
- **Knowledge citations**: Patrol docs (leancode.co/patrol); our
  `docs/adr/0001-image-cap.md` for the failure mode that motivated
  the discipline; SKILL-FULL.md "Polish-locale war story" section.

### Lesson 6 — The agent eats your context

> *A 4B model has 8K of context. Your SKILL.md is 30K. Math doesn't
> work. RAG does.*

- **Big idea**: Long-context isn't the answer for small models;
  retrieval is. Token-budget thinking is the load-bearing skill.
- **Production deliverable**: Index the project's docs into Qdrant.
  Show before/after agent context size for a 50-call session.
- **Knowledge citations**: Lewis et al., 2020 (RAG, arXiv:2005.11401);
  Liu et al., 2023 (Lost in the Middle, arXiv:2307.03172);
  Karpukhin et al., 2020 (DPR, arXiv:2004.04906); our
  `docs/adr/0005-hybrid-retrieval.md`.

### Lesson 7 — Skills that compound

> *The agent learned to boot a debug session yesterday. Today, that
> ritual is one tool call. Tomorrow, three rituals are one workflow.*

- **Big idea**: Promote successful sequences to named skills. Replay
  them. The library compounds.
- **Production deliverable**: Promote a 3-call sequence from a
  successful session. Replay it on a different project with a
  different device.
- **Knowledge citations**: Voyager (Wang et al., 2023,
  arXiv:2305.16291); Reflexion (Shinn et al., 2023,
  arXiv:2303.11366); our `docs/adr/0004-voyager-skill-library.md`.

### Lesson 8 — Shipping like a studio

> *Build → install → walk the flow → capture release shots → post
> to Slack → drag into Play Console. One YAML plan.*

- **Big idea**: Declarative test plans aren't just for CI. They're
  the release runbook too.
- **Production deliverable**: A YAML plan that produces ready-to-
  upload Play Store + App Store screenshots and notifies Slack
  via the n8n webhook.
- **Knowledge citations**: Our `examples/templates/dev_iteration.yaml`;
  `docs/n8n-integration.md`; Google's "Software Engineering at
  Google" Ch. 23 (Continuous Delivery).

---

## On-ramp 1: MCP from Scratch (2 weeks, free)

For students who know Python + LLMs but haven't built an MCP.

### Lesson 0.1 — One JSON message

> *MCP is JSON in, JSON out. There's no magic. Let's prove it.*

- **Big idea**: MCP is a JSON-RPC protocol over stdio. We can read
  and write the bytes.
- **Production deliverable**: A 30-line Python MCP server that
  responds to `tools/list` and `tools/call` with one trivial tool.
  Claude Code can call it.

### Lesson 0.2 — Add a real tool

> *Here's `read_file`, the smallest useful MCP tool. Build it.*

- **Big idea**: Real tools have descriptors, schemas, error handling.
- **Production deliverable**: A `read_file` tool with proper schema
  validation and structured errors.

---

## On-ramp 2: RAG to Agents (4 modules, existing)

Lives in `rag-search/codebase-rag`. Modules 1-4 already drafted.
Slot it in as the "bridge" between MCP basics and the flagship's
Lesson 6.

---

## On-ramp 3: Production Python for Flutter devs (1 week, free)

For Flutter devs whose Python is rusty. Focused on what they need
for the flagship, not exhaustive Python.

- **Lesson P.1** — type hints, dataclasses, `Result/Err` pattern.
- **Lesson P.2** — async/await, the `asyncio` event loop, why our
  use cases are async.
- **Lesson P.3** — Protocols + dependency injection + composition root.

---

## Article-style top-of-funnel

Separate from courses. Free, public, written for HN/Reddit.
Each article is a teaser for a flagship lesson.

| Article | Drives traffic to | Status |
|---|---|---|
| 01 — Building flutter-dev-agents | Lesson 1 + Lesson 2 | drafted |
| 02 — 8 KB SKILL is overkill | Lesson 6 | drafted |
| 03 — Reflection, retry, corrective RAG | Lesson 7 | outlined |
| 04 — The Voyager skill library | Lesson 7 | outlined |
| 05 — Benchmarking your own agent stack | Lesson 8 | outlined |

Article = essay. Lesson = exercise + working artifact. **Don't
confuse the two.**

---

## Pricing (preliminary)

| Tier | Price | What's included |
|---|---|---|
| Free articles + on-ramp 1 + on-ramp 3 | $0 | Filter for serious students |
| Self-paced flagship | €249 | All 8 lessons + private repo |
| Cohort (4 weeks) | €499 | + 4 group sessions + Discord |
| Consulting setup | €3,000-€8,000 | "I'll set up your factory" |

Run cohort 1 at €299 for first 10 to validate. Adjust upward
based on demand.
