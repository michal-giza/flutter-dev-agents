# Teaching strategy — flutter-dev-agents curriculum

We're shipping teaching material, not content. The difference is that
content gets consumed; teaching changes how the student thinks.
Everything below is built on that distinction.

## Pedagogical thesis

Four frameworks, each chosen for a specific reason. Cite them in the
material itself so students see the load-bearing structure.

### 1. Cognitive Load Theory — keep working memory unsaturated

**Sweller, 1988 — and 35 years of follow-up.** Working memory holds
~4 items. Instructional material that overflows this fails to land,
no matter how clever. Practical rules we'll obey:

- **One new concept per lesson.** The lesson's secondary topics must
  be things the student already knows from prior lessons or general
  background.
- **Worked-Example Effect**: a fully-worked example with annotation
  beats a problem statement plus an expectation of self-derivation,
  every time, until the student is past novice. We're teaching MCP
  internals from scratch — every student is a novice until proven
  otherwise.
- **Fade the guidance.** Worked example → half-blank → independent.
  Don't jump from "I'll show you" to "you build it" in one step.

### 2. Spiral Curriculum — concepts return at higher resolution

**Bruner, 1960.** Don't teach Clean Architecture once, exhaustively.
Teach the *idea* of layers in Week 1 with one example, return in
Week 3 with three layers visible, return in Week 6 with the full
4-layer thing. Each pass deepens; no pass overwhelms.

Concrete sequence in our material:
- **Week 1**: "tools have layers — descriptor, dispatch, use case."
- **Week 3**: "let's see why those layers matter — here's a bug
  the boundary prevented."
- **Week 6**: "now here's the actual `phone-controll/domain/`
  structure. You already know what each layer does."

### 3. Karpathy's "Zero to Hero" — build the production thing, not a toy

**Recent applied pedagogy: Karpathy's Neural Networks: Zero to Hero
(2022) + Let's Reproduce GPT-2 (2024).** Every module ends with a
working version of the actual production thing. Not a simplified
toy. A reduced-scope version of what we ship.

This is uncomfortable for course creators because the production
thing has complexity students aren't ready for. The discipline:
**ship the complexity, but in stages.** Week 1 produces a one-tool
MCP. Week 8 produces a 5-tool MCP with proper dispatch and tests.
The architecture is the same; the surface grows.

The opposite anti-pattern: 7 weeks of "Hello World" toys that
prepare you for nothing.

### 4. Software Carpentry — hands-on, mini-lectures, exercises

**The Carpentries methodology** (active since ~2010, used to train
~50K researchers/year). Per ~90-minute session:

- 10 minutes mini-lecture (concept introduction)
- 10 minutes live-coded walkthrough
- 20 minutes student exercise
- 5 minutes review
- Repeat

No 60-minute lectures. The student touches the keyboard at minute
20 of every session. We'll structure each lesson into 90-minute
sessions following this pattern.

## What we're not doing

- **Not a video course.** Video is high-production-cost, low-
  adaptability. We're shipping written + executable material first.
  Add video later when the written material is validated.
- **Not Coursera-style mega-courses.** 30 hours of "learning
  outcomes" trying to be everything. Our flagship is 16-20 hours
  total; ruthless about what stays.
- **Not "follow along and copy my code."** That produces students
  who can replay one demo and nothing else. We use the worked-
  example-then-fade pattern explicitly to prevent this.
- **Not gated paywalls everywhere.** Weeks 1-2 are free. They prove
  value to the prospective student AND validate teaching quality
  cheaply.

## Audience segmentation

Three distinct learners. **Don't try to teach all three at once.**

### A) Solo Flutter dev shipping consumer apps
- **Knows**: Flutter, BLoC, Firebase, App Store flow.
- **Doesn't know**: MCP, Python deeply, agent tooling.
- **Wants**: throughput. "I want to ship 6 apps with the effort of 3."
- **Course fit**: flagship.

### B) Engineering manager / tech lead at a small studio
- **Knows**: software architecture, testing, CI.
- **Doesn't know**: Flutter specifics, AR/Vision testing.
- **Wants**: scalable test infrastructure for a team of 2-5.
- **Course fit**: flagship + one "team scale-up" module.

### C) AI/ML engineer adopting agent tooling
- **Knows**: LLMs, RAG fundamentals, prompt engineering.
- **Doesn't know**: Flutter, MCP protocol details.
- **Wants**: production-grade agent stack patterns.
- **Course fit**: a separate "MCP server engineering" track
  pulled from our internals work (middleware chain, image cap,
  version handshake, Voyager, hybrid retrieval, Reflexion).

**Prioritisation:** A first. It has the lowest churn risk, the
highest LTV (apps keep shipping), and matches the lead author's
lived experience. B as a co-target. C as a follow-on.

## Curriculum architecture: one flagship, three on-ramps

```
                  ┌────────────────────────────────┐
                  │   Build a Flutter Dev Factory  │
                  │   (Flagship, 8 weeks, paid)    │
                  └────────────────────────────────┘
                              ▲
              ┌───────────────┼───────────────────┐
              │               │                   │
   ┌──────────┴────┐  ┌──────┴───────┐  ┌────────┴─────────┐
   │ On-ramp 1     │  │ On-ramp 2    │  │ On-ramp 3        │
   │ MCP from      │  │ RAG to       │  │ Production       │
   │ scratch       │  │ Agents       │  │ Python for       │
   │ (2 weeks,     │  │ (existing    │  │ Flutter devs     │
   │ free)         │  │ rag-search   │  │ (1 week, free)   │
   │               │  │ course)      │  │                  │
   └───────────────┘  └──────────────┘  └──────────────────┘
```

Each on-ramp ends with a prerequisite check that matches the
flagship's Week-1 entry test. Students self-route based on what
they already know.

## The flagship's 8 weeks

Each week is one ~90-minute "lecture lesson" + one ~3-hour exercise.
Total student time: 4-5 hours/week. Total content: ~16-20 hours.

| Week | Title | Big idea | Production deliverable |
|---|---|---|---|
| 1 | The 4 AM Test | Why a factory beats a workshop | One-tool MCP wired to Claude Code |
| 2 | Boundaries that survive an unreliable narrator | Clean Architecture for agent tooling | Use case + repository pattern |
| 3 | When the agent is wrong | `Result/Err` + `next_action` discipline | Structured failures, agent recovery |
| 4 | The device is a singleton, your sessions are not | Device locks + multi-project | Two-Claude factory demo |
| 5 | Patrol-first testing | Locale-free, widget-Key-driven | Flutter integration tests via MCP |
| 6 | The agent eats your context | Image cap + RAG + tier ladder | 4B model running 50-call loop without OOM |
| 7 | Skills that compound | Voyager-style library + Reflexion retry | Replayable named macros |
| 8 | Shipping like a studio | Release-mode capture + JUnit + n8n | One-button release-listing prep |

Each row is a "big idea" with a working deliverable. No vapor.

## Why this strategy beats the obvious alternative

The obvious alternative: "5 articles, each ~3000 words, sequential."
Articles are good for top-of-funnel marketing. They are bad at
teaching, for one reason: there's no feedback loop. A student who
reads article #3 doesn't know if they understood it until they hit
a real wall in their own project.

The flagship's exercise-per-lesson is the feedback loop.

## What "knowledge-backed" means in practice

Every claim a student encounters cites either:
- A paper (arXiv, peer-reviewed, or recognised tech-industry whitepaper)
- A specific code path in the repo (`src/mcp_phone_controll/...`)
- An ADR (`docs/adr/0001-image-cap.md` etc.)

No "I think this is true." Either we have the citation or we say
"this is a heuristic from the author's six-app experience" — and
that's a valid citation too, **as long as we label it**.

The single biggest pedagogical lie in software courses is "trust
me" without a source. We don't do that.

## Required reading for the teacher (you, this week)

You're writing the material. Six things to absorb first; ~6 hours
total:

1. **Karpathy — Neural Networks: Zero to Hero** (YouTube
   playlist intro, 5 minutes). Notice the "we build the actual
   thing" framing.
2. **Sweller, Cognitive Load Theory: Recent Theoretical
   Advances** (2010 paper, ~30 minutes). The worked-example
   effect is non-obvious until you've read it.
3. **Andy Matuschak — How can we develop transformative tools
   for thought?** (~1 hour read). The argument for "patient
   curriculum."
4. **The Carpentries — Instructor Training summary** (~30
   minutes). Steal their lesson template.
5. **Software Engineering at Google — Chapter 11 (Testing
   Overview)** (~1 hour). For how to teach testing without
   making people hate testing.
6. **DeepLearning.AI — any one short course** (~1 hour). The
   ~1-hour-per-course format is your model for the on-ramps.

These aren't optional. They're the thing that makes the difference
between "content creator" and "teacher."

## Strategic risks and how to manage them

- **You over-teach the internals.** Your six months of pain on
  image-cap is interesting to you, not necessarily to the student
  shipping their second app. Filter ruthlessly: does the student
  need this to ship?
- **You under-teach the rationale.** The opposite trap. A student
  who can copy your code but doesn't know why you made each choice
  can't adapt when their context differs. Every decision: cite
  the ADR or admit it's a heuristic.
- **You miss the actual ceiling for a 4B agent.** A claim like
  "70% context savings" needs the measurement. Either you measure
  or you mark it as "approximate, not benchmarked."
- **You ship before validating.** Run the first lesson by 3 people
  before week 2 lands. If they can't complete the exercise in
  ~3 hours, the lesson is broken.

## Cadence

- **Tomorrow afternoon (Sat 2026-05-16)**: write Lesson 1 in full.
  See `tomorrow-afternoon.md` for the 90-minute specific plan.
- **Next week**: write Lesson 2.
- **Week 3**: publish Lesson 1 as a free public artifact (blog post
  + working code repo). Get 5 readers to attempt the exercise.
  Iterate.
- **Week 4-10**: write one lesson per week. Validate each with
  the prior week's readers.
- **Week 11**: announce cohort 1 enrollment.
- **Week 12-19**: run cohort 1.

This puts cohort 1 starting in early August. Realistic, not
aspirational.
