# Course outline — "Build a 4B Flutter Dev Factory"

A paid-tier syllabus draft for the bundled `flutter-dev-agents` +
`rag-search` package. 8 weeks, 1–2 evenings per week, ships with a
private repo of working code per module.

Target student: solo founder or small studio that's already shipped
1–3 Flutter apps and wants to scale by automating the boring parts.
Knows Flutter, comfortable on the CLI, has a Mac. **Doesn't** need
deep ML/RAG expertise — that's what the course teaches.

Pricing: **$299 self-paced** / **$499 with one 30-min office hour per
month for 3 months**. Cohort cap 30 to make office hours feasible.

---

## Module 0 — Why a Flutter dev factory? (free preview)

- The one-person-company economics chapter from
  [`docs/article/building-flutter-dev-agents.md`](article/building-flutter-dev-agents.md).
- The benchmark table (70× scaffold, 6× hot-reload).
- Live demo: 4 Claudes in 4 projects on 4 devices. 8 minutes of video.
- **Deliverable:** student installs `flutter-dev-agents`, runs the
  sanity check from `docs/walkthrough-vscode-test.md`. **Pass criterion:**
  `describe_capabilities(level="basic")` returns 18 tools.

## Module 1 — RAG from scratch (free, sourced from `rag-search/module_1`)

- Vector embeddings, why dense beats lexical for "concept" queries.
- Qdrant in 30 minutes (Docker, one container, one collection).
- BGE-small / FastEmbed: ONNX-served, no GPU.
- Chunking: fixed-size vs language-aware. Why size matters.
- **Deliverable:** student indexes a Flutter project, runs 5 queries.
- **Reading:** Lewis et al., 2020 (RAG); Karpukhin et al., 2020 (DPR).

## Module 2 — Production RAG (free, sourced from `rag-search/module_2`)

- Smart file filtering. Glob discipline.
- Metadata-filtered queries. Hybrid (dense + sparse) with RRF.
- Idempotent re-indexing on `(collection, source, hash(text))`.
- Language-aware chunking for Dart specifically.
- **Deliverable:** the indexer behind `phone-controll`'s `index_project`.
- **Reading:** Liu et al., 2023 ("Lost in the Middle").

## Module 3 — Tools and agents (paid)

- MCP (Model Context Protocol) crash course.
- Building a tool: domain → repository → use case → registry.
- Result/Err contracts. The `next_action` field is the agent's
  remote control.
- Why argument coercion + corrected_example matter for 4B models.
- Output truncation, rate limits, circuit breakers.
- **Deliverable:** student adds a custom tool to `phone-controll`,
  passes the shadow-run harness.
- **Reading:** Schick et al., 2023 (Toolformer); Qin et al., 2023
  (ToolBench).

## Module 4 — The dev iteration loop (paid)

- `flutter run --machine` JSON-RPC daemon protocol.
- Hot reload, hot restart, service extensions.
- Multi-window VS Code orchestration.
- Plan walker: PRE_FLIGHT → CLEAN → LAUNCHED → UNDER_TEST.
- Why declarative plans beat ad-hoc tool sequences.
- **Deliverable:** student writes a YAML plan for one of their own
  apps, runs it green via `run_test_plan`.

## Module 5 — Patrol-first testing on real devices (paid)

- Why `tap_text` is a trap. Polish-locale war story.
- Patrol selectors and widget Keys.
- The Test Validity Rubric (8 criteria).
- AR / Vision specifics: marker detection, pose stability, golden
  images.
- iOS quirks: tunneld, DDI, WebDriverAgent setup.
- **Deliverable:** Patrol smoke test running against the student's
  actual phone.

## Module 6 — The RAG bridge (paid)

- Why an 8 KB SKILL is overkill for 4B agents.
- `recall(query, scope)` vs loading the whole skill.
- Indexing the SKILL + docs + session traces into Qdrant.
- The dependency boundary in
  [`docs/composition.md`](composition.md).
- **Deliverable:** student's local model retrieves SKILL chunks
  instead of loading the full file. Measured token-budget delta on
  their own model.

## Module 7 — Reflection, retry, benchmarking (paid, advanced)

Builds on Tier H from
[`docs/next-session-enhancements.md`](next-session-enhancements.md).

- Reflexion-style self-critique loops.
- Corrective RAG when retrieval scores poorly.
- Building a small benchmark suite specific to the student's apps.
- Measuring: does adding tool X actually help the agent succeed more?
- **Reading:** Shinn et al., 2023 (Reflexion); Yan et al., 2024
  (CRAG); Qin et al., 2023 (benchmarking methodology).

## Module 8 — Productization (paid, capstone)

- The four-tier monetization ladder from the article.
- How to license your own version of this stack.
- Multi-project economics: 3 Claudes × 3 devices = real throughput.
- Cohort discussion + 1:1 office hour.

---

## Bonus material (paid only)

- **Private repo** with Tier G + Tier H code pre-wired to the
  course's example app.
- **Recorded debugging sessions** for the three real war stories
  (iOS 26 DDI, Polish-locale `tap_text`, screenshot binary
  corruption).
- **Cohort Discord** — kept private to paying students.

## What this is not

- A general-purpose Flutter course. Students must already know Flutter.
- An ML deep-dive. We use embeddings; we don't train them.
- A SaaS sales pitch. The output is a working factory the student owns.

## Distribution

- **Gumroad** for the self-paced tier.
- **Maven** or a private cohort platform for the office-hours tier.
- Article #1, #2, #3 (free) drive top-of-funnel.
- Each module's code lands in the public repo on a quarter delay; the
  course is always one quarter ahead of the open-source release.

## Marketing positioning

> "Stop writing the same Patrol boilerplate twice. Stop debugging
> Polish-locale failures one phone at a time. Build the agent factory
> that does it for you."

One-line: **Solo founder Flutter automation, taught from scratch, with
a working agent at the end.**

## Cohort metrics to track

- Completion rate per module (Module 4 is the choke point).
- Time-to-first-green from install to "agent ran my Patrol test."
- Net Promoter Score after Module 8.
- % of students who refer at least one other student.

---

*This outline is not a commitment. It's the next step before
committing — the artifact you put in front of 5 prospective students,
ask "would you pay for this?", and iterate.*
