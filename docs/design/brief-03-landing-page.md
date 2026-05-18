# Brief 03 — Landing page design system

## Goal

A landing page that converts the three audiences:
- P1 lands → reads hero → clicks "Try it locally"
- P2 lands → reads hero + "Production-credible" section → clicks
  "Read the runbook"
- P3 lands → reads hero + architecture diagram → clicks "GitHub"

Single-page, mobile-responsive, no auth wall. The repo's GitHub
page IS the documentation; this page is the **conversion surface**.

## Audience

All three personas; the page splits them via section ordering.

## Hosting

Cloudflare Pages, free tier. Subdomain candidate:
`flutter-dev-agents.dev` or `mcp-phone-controll.dev`. Static SPA;
no JS framework needed — pure HTML/CSS + minimal Alpine.js for the
code-snippet tabs.

## Page structure (top to bottom)

### Hero (above the fold)

- Logo + wordmark, top-left.
- Right-aligned nav: `Docs` · `GitHub` · `Try it` (the last one is a
  primary button, orange).
- Headline (H1, ~64px desktop / 40px mobile):
  > Your factory of Flutter agents.
- Subhead (~24px):
  > MCP server that lets autonomous agents build, deploy, and test
  > Flutter apps on real iPhones and Android phones.
- **Primary CTA** button (orange, large): `Try it locally — 5 min`.
  Links to a fragment on the page with the install snippet.
- **Secondary CTA** (text link, off-white): `Read the docs →`.
  Links to the GitHub repo.
- **Hero visual**: the architecture diagram from brief-04, or — once
  the demo video lands — an embedded 90-second loop.

### Three-line proof bar (immediately below hero)

```
109 tools  ·  491 tests  ·  MCP 2025-06-18  ·  Apache 2.0  ·  v0.2.0
```

Single line on desktop, two on mobile. JetBrains Mono, slate grey.

### "What is this?" section

A 30-second answer in three short paragraphs + ONE code snippet
showing a real agent call. Don't bury the lede.

```
The agent calls:
  > prepare_for_test, take_screenshot, tap_and_verify,
  > assert_no_errors_since, run_patrol_test...
... and the MCP drives a real phone via adb / pymobiledevice3 /
WebDriverAgent. You get a verifiable test run; the agent gets a
typed `next_action` on every failure.
```

### "Built for 2026 agents" — feature grid (4 columns × 2 rows)

Eight feature tiles, each with an outlined icon (Lucide / Phosphor),
a 2-3 word title, and one sentence:

1. **MCP-spec native** — readOnly / destructive / idempotent / outputSchema
   on every tool. Spec 2025-06-18.
2. **Cap-the-context** — palette-mode PNG compression + 1900-px hard
   ceiling so screenshots never blow the 2000-px API limit.
3. **iOS + Android** — same tool surface, platform routing under
   the hood. Sims included.
4. **Multi-agent, multi-device** — filesystem-coordinated device
   locks; four Claudes can drive four phones in parallel.
5. **Quality gates** — Patrol, dart analyze, dart format, quick
   check, golden-image diffs — all dispatchable.
6. **Backed by RAG** — hybrid retrieval (dense + BM25), Reflexion
   retries, Voyager-style skill library.
7. **Observable** — structured JSON logs, Prometheus `/metrics`,
   `/health` + `/ready`, SBOM in CI.
8. **Secure** — path-traversal guards, CVE scanning, subprocess-injection
   audit, Apache 2.0.

### Show the work — agent transcript

A horizontally-scrolling carousel showing 4 real agent
interactions (pulled from `tests/agent/transcripts/`). Each card is
a stylized chat-transcript snippet with the tool call + envelope.
Click → copy as JSON.

### Production-credible — three-column proof

| Column 1 | Column 2 | Column 3 |
|---|---|---|
| **Spec-compliant** with annotations, outputSchema, contract test | **Battle-tested** 491 hermetic + 5 real-device tests, every commit | **Audit-ready** Apache 2.0, SBOM in CI, SECURITY.md with SLAs |

### Try it locally — interactive install snippet

Three tabs (Claude Code / Claude Desktop / Docker), each showing
the 4-line install + verify recipe. JetBrains Mono, click-to-copy.

```bash
git clone https://github.com/michal-giza/flutter-dev-agents.git
cd flutter-dev-agents && ./scripts/install.sh
# In Claude: call mcp_ping → confirm git_sha + n_tools
```

### Footer

- Logo + tagline (left)
- Three columns: Product (Docs, Changelog, Roadmap), Community
  (GitHub, Discussions, Issues), Legal (License, Security, Code
  of Conduct)
- "Built by Michal Giza" + GitHub link
- Copyright + Apache 2.0 mention

## Visual specs

- **Canvas**: max-width 1200px on desktop, fluid below 768px.
- **Vertical rhythm**: 80px section spacing on desktop, 48px mobile.
- **Buttons**: orange primary (`#F76C28`) with 8px border-radius,
  16px vertical / 24px horizontal padding, no gradients. Hover:
  slightly darker (`#E55A18`).
- **Code blocks**: `#0A0E1A` bg, `#F4F0EA` text, JetBrains Mono 14px,
  16px padding, no border. Inline code: same colors, 4px padding.
- **Section dividers**: invisible (use whitespace), not hairlines.
- **Mobile breakpoint**: 768px. Drop the 4-column feature grid to
  2 columns at 768px, 1 column at 480px.

## Performance budget

- **Total page weight**: < 200 KB (excluding the embedded demo
  video).
- **LCP**: < 1.2 s on a 3G throttle.
- **No client-side analytics**. If you need stats, use Cloudflare
  Analytics (cookieless, server-side). No GA.

## Accessibility

- WCAG 2.1 AA contrast on every text/background combination. Test
  with `axe`.
- All interactive elements keyboard-accessible.
- `prefers-reduced-motion: reduce` disables the transcript carousel
  auto-scroll.
- Skip-to-content link at the top.

## Deliverables

- Figma file with the full design system (colors, type, components).
- Hand-off in `design/handoff-landing.md` listing every component
  spec for a developer who didn't make the Figma file.
- Optional: an HTML/CSS implementation if the Figma designer also
  codes.

## Definition of done

- All six sections present.
- Hero ↔ install snippet flow works on mobile (no horizontal scroll).
- Page weight under 200 KB.
- WCAG AA across the page (verified with axe).
- All claims in the proof bar match the actual repo state
  (we may need to update the numbers).

## Claude prompt

```
Design a single-page landing page for `flutter-dev-agents` (MCP
server for autonomous mobile testing). Audience: indie devs +
mid-size company dev-platform engineers + agent-builders.

Required sections (in order):

1. Hero: logo top-left, nav top-right (Docs / GitHub / Try it),
   H1 "Your factory of Flutter agents.", subhead about the MCP
   driving real phones, primary orange CTA "Try it locally — 5
   min", secondary text link "Read the docs →".

2. Proof bar: "109 tools · 491 tests · MCP 2025-06-18 · Apache
   2.0 · v0.2.0".

3. "What is this?" 30-second answer in 3 paragraphs + 1 code
   snippet showing real agent tool calls.

4. Feature grid 4×2 with outlined icons + 2-3 word titles + 1
   sentence each. Eight features: MCP-spec native, cap-the-
   context, iOS+Android, multi-agent, quality gates, RAG-backed,
   observable, secure.

5. Agent transcript carousel showing 4 real tool-call cards.

6. "Production-credible" three-column proof: spec-compliant,
   battle-tested, audit-ready.

7. "Try it locally" with three tabs (Claude Code, Claude Desktop,
   Docker), 4-line install snippets each.

8. Footer with three columns and Apache 2.0 mention.

Visual: deep blue-black #0A0E1A background, off-white #F4F0EA
text, primary orange #F76C28 for CTAs, lime #A6E22E for ✓ marks,
Inter Tight 700 for headings, Inter 400-500 for body, JetBrains
Mono for code. No gradients, no 3D, no stock photos, no AI
buzzwords.

Mobile breakpoint 768px. WCAG AA contrast. Total page weight
under 200 KB excluding video.

Output: a Figma file or HTML/CSS implementation. Include a
handoff doc explaining each component's specs.
```
