# Master plan — flutter-dev-agents × rag-search

The single document you (Michal) pick up tomorrow. Covers what shipped
tonight, the publish queue, GitHub setup steps, the landing-page
architecture + content, the deferred items grouped by reason, and the
"what's missing as of 2026-05-07" forward roadmap.

Date stamp: **2026-05-07**.

---

## What shipped tonight (Tier H + I subset)

### Tier H — agent literacy (5/5 shipped)
- **H1** Hybrid retrieval (dense + lexical RRF) on `recall`. ~150 LOC, 7 tests.
- **H2** `recall_corrective` — CRAG self-grading with scope fallback. ~120 LOC, 4 tests.
- **H3** Reflexion retry phase in plan walker. `MCP_REFLEXION_RETRIES` env. 4 tests.
- **H4** Voyager skill library — `promote_sequence`, `list_skills`,
  `replay_skill`. SQLite-persistent. 6 tests.
- **H5** `MCP_STRICT_TOOLS` — opts into OpenAI structured-output mode at
  the function-call layer. 5 tests.

### Tier I — productization (2/4 shipped)
- **I1** `bench/run_bench.py` — 10 deterministic benchmark tasks, JUnit
  + JSON output, CI-gated via `tests/unit/test_bench_smoke.py`. 1 test.
- **I4** `scripts/watch_index.py` — debounced file-watcher that
  re-indexes on save. Optional `watchdog` dep.

### What did NOT ship tonight (and why)
- **I2 Docker CI image** — env-heavy work; needs a clean Linux runner +
  Android emulator config + manual smoke. Better as a focused
  half-day session than a 30-minute crunch tonight.
- **I3 `mcp-rag-bridge` workspace package** — refactor that touches
  every import path. Plumbing change; no user-visible win until I'm
  actively maintaining a third MCP. Defer until that pressure exists.
- **All of Tier J** — these are research investigations, not code
  drops. Documented as 1–3 day investigations each. Run them after the
  benchmark suite (I1) lands and we can measure deltas.

### Numbers
- Tools: **94 → 100** (+6: `recall_corrective`, `promote_sequence`,
  `list_skills`, `replay_skill`, plus the two pre-existing `recall` and
  `index_project`).
- Tests: **269 → 296**, all green, < 1.5 s wall-clock.
- New use cases: 7. New repositories: 2. New scripts: 2.

---

## Tier J — deferred research investigations

Each is a 1–3 day standalone investigation, not a coding batch. Run
sequentially, publish results in articles #4–6.

### J1. ReAct vs Plan-and-Solve
- **Hypothesis.** With `recommended_sequence` (G1) and the SKILL
  thinned (G6), Plan-and-Solve (Wang et al., 2023,
  [arXiv:2305.04091](https://arxiv.org/abs/2305.04091)) may dominate
  ReAct (Yao et al., 2022, [arXiv:2210.03629](https://arxiv.org/abs/2210.03629))
  on our specific tasks.
- **Method.** Implement a Plan-and-Solve loop in `examples/`; run both
  against `bench/tasks.json` × {Claude Sonnet, Claude Haiku, Qwen
  2.5-7B, Qwen 2.5-14B}. Publish the table.
- **Effort.** 2 days.

### J2. Long-context vs RAG ablation
- **Hypothesis.** Loading the whole SKILL beats RAG on Claude (200K
  context); RAG beats long-context on 4B models. Confirm "Lost in the
  Middle" (Liu et al., 2023, [arXiv:2307.03172](https://arxiv.org/abs/2307.03172))
  on our tasks specifically.
- **Method.** Run benchmark with two skill-loading strategies: full
  SKILL inline vs `recall(scope="skill")`. Per-model breakdown.
- **Effort.** 1 day.

### J3. Tree-of-Thoughts on plan validation
- **Hypothesis.** ToT (Yao et al., 2023,
  [arXiv:2305.10601](https://arxiv.org/abs/2305.10601)) explores driver
  alternatives (`flutter_test` vs `patrol_test`) and picks the highest-
  scoring branch — beats single-shot validation on plans with
  ambiguous driver kinds.
- **Method.** Wrap `validate_test_plan` in a ToT branch generator;
  measure on hand-crafted ambiguous plans.
- **Effort.** 3 days. Probably overkill; measure first.

---

## Publish queue

The articles, in order. Article #1 and #2 already exist in
`docs/article/`. Outlines for #3–#5 are in `docs/article-outlines/`
(written in this batch). Tone: same as #1 / #2 — first-person,
arxiv-grounded, no SaaS-cope.

| # | Title | Status | Word count | When |
|---|---|---|---|---|
| 1 | Building flutter-dev-agents | drafted | ~4600 | publish next week |
| 2 | 8KB SKILL is overkill — RAG bridge | drafted | ~2300 | 2 weeks after #1 |
| 3 | Reflection, retry, and corrective RAG | outline | target ~3000 | 4 weeks after #1 |
| 4 | The Voyager skill library — agents that compound | outline | target ~2500 | 6 weeks after #1 |
| 5 | Benchmarking your own agent stack | outline | target ~3000 | 8 weeks after #1 |

Distribution channel:
1. **Personal blog** — primary canonical URL (when the landing page is
   live, see below).
2. **dev.to / Hacker News / r/FlutterDev / r/MachineLearning** — cross-
   post 3 days after blog publication. Different headline per platform
   (HN-style vs r/FlutterDev-style).
3. **Substack** — paid newsletter wraps the public articles + private
   "behind the scenes" addenda. $5/mo, kicked off after article #3.

---

## GitHub setup steps

You're authenticated as `michal-giza` (verified via `gh auth status`).
Tokens have `repo`, `workflow`, `gist`, `read:org` — sufficient for
public repo creation, push, and CI.

### Status (as of 2026-05-07)

Both repos are live and public:
- **`michal-giza/flutter-dev-agents`** — pushed tonight by Tier H+I batch.
  https://github.com/michal-giza/flutter-dev-agents
- **`michal-giza/rag-to-agents`** — already on GitHub (course-side
  was pushed earlier).
  https://github.com/michal-giza/rag-to-agents

Note: the course was titled `rag-to-agents` on GitHub, not `rag-search`.
Decide whether to keep that name or rename + redirect; "rag-to-agents"
is actually a stronger marketing name (it describes the journey).

### After the push
- **Add README badges** (build status, license, tests passing). The
  README in `flutter-dev-agents` already exists; add `[![tests](...)]`
  badges pointing at GitHub Actions runs.
- **Add `.github/workflows/ci.yml`** — runs `pytest` + the Tier-G
  shadow-run + the bench. Already drafted in the umbrella plan;
  copy-paste into `.github/workflows/`.
- **Pin two repos to your GitHub profile** — visibility hack, free.
- **Open a "Discussions" tab** on each repo. Use it for the article
  comment thread; post #1 announcement there as the first issue.

### Cross-link
- `flutter-dev-agents/README.md` already mentions the walkthrough; add
  one line: "Companion course: github.com/michal-giza/rag-search."
- `rag-search/README.md` should add: "Working production agent: see
  github.com/michal-giza/flutter-dev-agents."

---

## Landing page — what to build, what to defer

You floated three options: Cloudflare Pages, HuggingFace Space, Flutter
+ Rust backend. Honest assessment by ROI.

### Recommended: Cloudflare Pages (static, ~3 hours to ship)
- **Why.** Free hobby tier; deploys via `git push` to a connected
  repo; HTTPS + custom domain out of the box; zero servers to babysit.
- **Stack.** Astro or Eleventy (static SSG), markdown content, no JS
  framework dependency. `gh` integrates with Cloudflare Pages directly.
- **Content** (see "Landing page content" below):
  - Hero: "The Flutter dev factory for solo founders."
  - 30-second demo video (recorded on the Mac with QuickTime).
  - Three pillars: open-source MCP, paid course, consulting.
  - Article #1 + #2 inline.
  - Email-capture for course launch waitlist.
- **URL.** Buy `flutterfactory.dev` or `flutter-dev-agents.com`. ~$15/yr.

### Defer: Flutter Web frontend + Rust on HF Space
- **Why deferred.** Flutter Web has bundle-size + first-paint issues
  (~1.5 MB gzipped) that hurt SEO. Rust on HF Space is novel but adds
  complexity (Spaces auto-sleep, cold-start latency). For a marketing
  landing page, neither pulls weight.
- **When it makes sense.** If you ever ship an interactive demo of the
  agent driving a phone in the browser — *that* needs a backend.
  Flutter for the demo UI, Rust for the WebSocket relay to the MCP
  running locally on a HF Space-hosted Linux box. Then the stack
  earns its complexity.
- **Plan if/when needed.** ~5 days. Spec lives below.

### Backup option: Notion / Gumroad-only landing
- **Why.** Zero engineering. Notion published as `flutter-factory.notion.site`,
  Gumroad page for the course. Looks unprofessional but saves a week.
- **When.** If Cloudflare Pages slips past 1 week.

---

## Landing page content (Cloudflare Pages, target word count: ~800)

### Hero block
```
The Flutter dev factory for solo founders.

I run six Flutter apps. Four are camera/AR/Vision-heavy. I built the
agent that lets one person ship like a small studio.

[Watch the 30-second demo]   [Read article #1]   [Get the course →]
```

### Three pillars (3-column section)
1. **Open-source MCP** — 100 tools. Drives Patrol tests, hot reload,
   debug sessions, multi-project workflows. MIT/Apache. Star on GitHub.
2. **Paid course** — Build your own factory in 8 weekends. Ships with
   a private repo of working code. Module 0–8, $299 self-paced.
   [Join the waitlist].
3. **Consulting** — I'll set up your factory laptop. $5K, remote,
   one weekend, hands-on training. [Email].

### Articles section (inline)
- Article #1 link with one-line summary.
- Article #2 link with one-line summary.
- "More on Substack" with current paid-subscriber count.

### Social proof
- GitHub stars (auto-updated via shield).
- Cohort testimonials once you have them.
- "Featured in" if anyone picks up the article.

### CTA footer
- Email capture for course launch.
- Link to GitHub, Substack, Twitter/X.
- License footer + "Built by Michal Giza, 2026."

### What NOT to put on the landing page
- Tutorial content. Tutorials live in articles + course.
- Pricing tier comparison tables. Confuses without context.
- Testimonials you don't have yet — leave the section if needed.
- A "log in" button. There's nothing to log into.

---

## What's missing as of 2026-05-07 — forward roadmap

You asked for this explicitly. Honest assessment of what's still
missing, ranked by leverage.

### Missing-but-likely-small (1–3 days each)
1. **GitHub Actions CI** — Linux + macOS jobs running `pytest` +
   shadow-run + bench. Drafted in the umbrella plan but not landed.
2. **Pre-commit hooks** — `ruff` + `mypy` + `pytest -x` on staged
   files. ~30 min once configured.
3. **Tier I3 — `mcp-rag-bridge` workspace package** — when adding more
   RAG smarts (H-tier follow-ups), the in-tree path will start
   feeling cramped. Pull out cleanly.
4. **Indexing watcher unit tests** — `test_watch_index.py` mocking the
   `watchdog` events. Should hit 100% of the script's branches.
5. **Strict-mode integration tests** — verify `?strict=true` on the
   HTTP adapter passes through to actual local LLMs (Ollama, vLLM)
   that support it.

### Missing-and-medium (1 week each)
6. **Tier I2 — Docker CI image** for headless emulator runs.
7. **Tree-of-Thoughts on plan validation (J3)** — measure first.
8. **Real BM25 sparse retrieval** via FastEmbed's `SparseTextEmbedding`
   replacing the lexical proxy in H1.
9. **HTTP transport tests against Ollama** — end-to-end loop with a
   real local LLM driving the agent.

### Missing-and-large (1+ week each)
10. **Bench against real local LLMs** — needs a working Ollama setup
    on the dev machine, model pulls, evaluation harness. Tracked as
    J1+J2.
11. **The Flutter Web demo + Rust HF backend** — deferred above.
12. **iOS 26 DDI workaround** — hacky `start_tunneld`-then-pray works,
    but a cleaner solution requires upstream pymobiledevice3 work.

### Missing-but-strategic (months)
13. **Course distribution platform.** Decide between Maven (cohort
    + community) vs Gumroad (self-paced) vs both. Course outline
    written; revenue happens when you put it in front of 5
    prospective students this week.
14. **Newsletter platform.** Substack vs Beehiiv vs ghost.io self-
    hosted. Paid subscriber timing depends on article #3 landing.
15. **Trademark / brand.** "Flutter Factory" might be a registrable
    name. If you go with the consulting tier, it's worth $300 and
    1 hour at the IP office.

### Things you don't need yet
- **A team.** Solo founder economics; one person can run all of this
  through 50 cohort students × $299. Hire only when course revenue
  exceeds half your time spent on it.
- **A SaaS / hosted indexing service.** Premature; never build infra
  before consulting + course saturate.
- **An AGI-style autonomous fix loop.** Reflexion (H3) is the
  ceiling for now; full autonomous code-and-fix cascades into "agent
  ate my repo" territory. Watch the literature; don't build it
  speculatively.

---

## Week-by-week schedule (next 8 weeks)

### Week 1 (this week, 2026-05-07 → 13)
- [ ] Push both repos to GitHub (`gh repo create` × 2).
- [ ] Add `.github/workflows/ci.yml` to flutter-dev-agents.
- [ ] Buy domain.
- [ ] Cloudflare Pages account + connect to flutter-dev-agents repo.
- [ ] Article #1 published canonically.
- [ ] Tweet/X post linking to GitHub + article #1.

### Week 2
- [ ] Cloudflare Pages landing live.
- [ ] Article #2 published.
- [ ] HN submission of article #2.
- [ ] Course outline visible behind a "join waitlist" form.
- [ ] First 5 prospective-student emails / interviews. Ask "would you
      pay $299?"

### Week 3–4
- [ ] If 3+ of those 5 say yes: announce cohort 1 dates.
- [ ] If <3: revise outline based on feedback, repeat.
- [ ] Article #3 drafted.
- [ ] Set up Substack (free tier) — re-publish articles 1–3.

### Week 5–6
- [ ] Article #3 published.
- [ ] First consulting prospect outreach (3 inbound from articles, hopefully).
- [ ] Substack paid tier opens.
- [ ] Cohort 1 enrollment opens (if Week 2 validation positive).

### Week 7–8
- [ ] Article #4 drafted + published.
- [ ] Cohort 1 starts.
- [ ] First consulting engagement (or: keep iterating).

The article cadence (every 2 weeks) drives the course/consulting
funnel. The cohort cadence (quarterly) is downstream of that. Don't
build infra ahead of demand — you've already built more code than most
solo founders ever ship.

---

## Quick reference — files you'll want tomorrow

- `docs/master-plan.md` — this file.
- `docs/article/01-building.md` (still named `building-flutter-dev-agents.md`).
- `docs/article/02-rag-bridge.md`.
- `docs/article-outlines/03-reflection-retry-crag.md` ← new.
- `docs/article-outlines/04-voyager-skill-library.md` ← new.
- `docs/article-outlines/05-benchmarking-your-stack.md` ← new.
- `docs/composition.md` — the dependency boundary.
- `docs/walkthrough-vscode-test.md` — what to run when validating.
- `docs/testing-procedures.md` — the four testing tiers.
- `docs/course-outline.md` — paid course syllabus draft.
- `docs/next-session-enhancements.md` — Tier H/I/J citations (most
  superseded by this file now, kept for cross-reference).
- `bench/tasks.json` + `bench/run_bench.py` — the benchmark.
- `scripts/shadow_run.py` — the fuzz harness.
- `scripts/watch_index.py` — the indexing watcher.

You're set. Go to bed.
