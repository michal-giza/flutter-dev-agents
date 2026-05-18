# Brief 06 — Pitch deck template (10 slides)

## Goal

A reusable Keynote / Google Slides / Figma Slides deck for:
1. Selling the project to mid-size companies (P2) — "use this in
   your CI" sales motion.
2. Conference / meetup talks (P3 audience).
3. Funding conversations (if/when applicable).

ONE deck, master-slide-driven, easy to swap a single slide per
audience.

## Audience

Primarily P2 (mobile-QA leads at companies) and P3 (agent-builders
at conferences). Lowest priority of the six briefs.

## The 10 slides

### 1 — Title

- Logo + wordmark, centered.
- Tagline below: "Your factory of Flutter agents."
- Speaker name + role + URL in the bottom-right, small.

### 2 — The problem (one sentence + one chart)

> _Flutter teams spend 30-50% of their QA time maintaining
> selectors. Patrol helps, but the test PLAN itself still needs a
> human in the loop._

Visual: a bar chart of "Time spent on selector maintenance" sourced
from the Drizz May 2026 report (cited explicitly in a footnote).

### 3 — The insight (one sentence)

> _Agents can write the test plan. They just need typed tools and
> a real device to drive._

Visual: a small architecture-sketch (subset of brief-04) showing
agent → MCP → phone, with the MCP boundary highlighted.

### 4 — The product (the demo)

EITHER an embedded GIF of the demo video (10s), OR a side-by-side
of "Claude Code chat" and "Samsung S25 running the app". Talk over
this slide for 30-45 seconds.

### 5 — How it works (one diagram)

The detailed architecture from brief-04, full screen. Talk through
the loop: dispatcher → middleware → router → device.

### 6 — Why now (three bullets)

- MCP spec stabilised (2025-11-25, with tool annotations + outputSchema).
- Anthropic explicitly publishing tool-design guidance.
- Claude / Cursor / etc. have hit the host-side tool-count ceiling
  — pre-built MCPs are what unblocks them.

### 7 — Proof (the receipts)

Three columns:
- **Engineering-credible**: 109 tools, 491 hermetic tests + 5
  real-device tests, MCP 2025-06-18 compliant.
- **Production-credible**: SBOM in CI, CVE scan blocking, 7 ADRs,
  Apache 2.0, runbook with top-10 failures + fixes.
- **Battle-tested**: real-user incidents driving every batch —
  reference the May 2026 hardening pass (caps, K1, K2, byte budget).

### 8 — Comparison

A small table — `flutter-dev-agents` vs `Patrol alone` vs `Appium
+ scripts` vs `manual QA`:

| | flutter-dev-agents | Patrol alone | Appium + scripts | Manual QA |
|---|---|---|---|---|
| Agent-callable | ✓ (MCP) | × | × | × |
| iOS + Android | ✓ same surface | partial | with adapters | ✓ |
| Selector hygiene tool | ✓ `list_missing_widget_keys` | × | × | × |
| Production-credible | ✓ Apache 2.0 + SBOM | open-source | varies | n/a |
| Setup time | < 5 min | < 5 min | hours | n/a |

### 9 — Roadmap (the next six months)

A simple horizontal timeline:
- **Now (May 2026)**: 0.2.0 — enterprise-ready, integrations
  shipped.
- **Next quarter**: outputSchema rollout to all 109 tools; VS Code
  extension; Helm chart.
- **Q3 2026**: `resources/` + `prompts/` MCP primitives; sub-server
  split for the 40-tool ceiling problem.
- **Q4 2026**: hosted-MCP option (HTTP+OAuth 2.1 for orgs who can't
  run locally).

### 10 — Ask + call to action

- "Star the repo" + URL.
- "Try the 5-minute install" + URL.
- For sales: "Schedule a 15-min demo against your test suite —
  msquaregiza@gmail.com".

## Visual specs

- **Background**: `#0A0E1A` deep blue-black on every slide.
- **Text**: `#F4F0EA` off-white.
- **Accents**: orange (`#F76C28`) for the ONE thing per slide that
  matters most. Lime (`#A6E22E`) for ✓ marks. Coral (`#FF6E6E`) for
  ✗ marks.
- **Type**: Inter Tight 700 for slide titles (~48pt), Inter 400 for
  body (~24pt), JetBrains Mono 14pt for any code.
- **No transition animations**. Cuts only. Builds OK on slide 6
  (bullets fade in).
- **No clip art**. Real screenshots from `~/.mcp_phone_controll/sessions/`
  for visuals.

## Format

- 16:9 widescreen (1920×1080 export at 1.5× = print-ready).
- Source: Figma Slides OR Keynote (.key). NOT PowerPoint — fonts
  break.
- A PDF export of every slide individually for embedding in blog
  posts.

## Deliverables

- `docs/design/assets/pitch-deck.fig` (Figma source)
- `docs/design/assets/pitch-deck.pdf` (10-page PDF export)
- `docs/design/assets/pitch-slides/` directory with each slide as
  individual 1920×1080 PNG (for blog embeds + social sharing)
- A short `pitch-deck-talking-points.md` with 1-2 sentence speaker
  notes per slide so the deck works without a memorised script

## Definition of done

- Every claim on the deck is sourced (chart on slide 2 cites Drizz,
  numbers on slide 7 match the latest commit).
- Slide 4 has a working demo embed (still + GIF + link to the full
  video).
- Comparison table on slide 8 isn't a hit-piece — every competitor
  gets at least one ✓. Truth-first selling.
- Works without the speaker (PDF readable as a standalone artifact).

## Claude prompt

```
Design a 10-slide pitch deck for `flutter-dev-agents`. Audience:
P2 (mobile-QA leads) and P3 (agent-builders at conferences).

Slides (in order):
1. Title (logo + tagline + speaker)
2. Problem: "30-50% of Flutter QA time is selector maintenance"
   with a chart sourced from Drizz May 2026.
3. Insight: "Agents can write the test plan; they need typed
   tools + a real device."
4. Product: demo embed (GIF + still + link).
5. How it works: architecture diagram (subset of brief-04).
6. Why now: MCP spec stable, Anthropic publishing tool guidance,
   host tool-count ceilings.
7. Proof: 3 columns (engineering-, production-, battle-credible)
   with real numbers (109 tools, 491 tests, MCP 2025-06-18,
   Apache 2.0).
8. Comparison table: us vs Patrol vs Appium+scripts vs manual.
9. Roadmap: now / next quarter / Q3 / Q4 timeline.
10. Ask: star + try + email.

Visual: dark #0A0E1A bg, off-white text, one orange accent per
slide, lime ✓ + coral ✗ only where they earn it. Inter Tight 700
titles ~48pt, Inter 400 body ~24pt, JetBrains Mono for code. No
transition animations. No clip art. Real screenshots only.

Output: Figma Slides source + 10-page PDF + per-slide PNGs +
talking-points doc (1-2 sentence speaker notes per slide).

The deck must work without me speaking — every claim is sourced,
the demo on slide 4 has a still + GIF + URL.
```
