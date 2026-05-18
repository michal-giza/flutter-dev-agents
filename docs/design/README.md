# Design brief pack — `flutter-dev-agents`

Shippable specs for every visual asset the project needs to launch.
Each brief below is **self-contained**: a designer (human, Figma
Make, Anthropic Designer Skill, Midjourney prompt) can start work
without reading the rest of the repo.

If you don't have a designer, paste the prompt at the bottom of each
brief into Claude with the **anthropic-skills:design-handoff** or
**Claude Designer** skill — output is usually usable in one round.

## Brand foundations (the source of truth)

Every asset below pulls from these four constraints. Don't deviate
without updating this section.

### Identity

- **Name (product)**: `flutter-dev-agents`
- **Name (server)**: `mcp-phone-controll` (the npm-style hyphenated
  form, intentional — matches the package name on PyPI)
- **One-line description**: "MCP server that lets autonomous agents
  build, deploy, and test Flutter apps on real iPhones and Androids."
- **Tagline candidates** (pick one for the landing):
  1. _"Your factory of Flutter agents."_
  2. _"From idea to App Store, autonomously."_
  3. _"The mobile-testing MCP for 2026 agents."_
- **Anti-tagline** (what we are NOT): not a no-code builder, not a
  "vibe coder" tool, not a Patrol alternative. We orchestrate the
  agents that orchestrate Patrol.

### Audience

Three personas. Briefs below indicate which ones each asset targets:

- **P1 — Solo Flutter dev / indie shipper**. Wants the agent to do
  the boring 80% of test runs so they can keep building. Cares
  about: reliability, "does it actually drive my phone?", small
  setup. Reads: HackerNews, Reddit r/FlutterDev, indie-hacker
  newsletters.
- **P2 — Mobile-QA lead / dev-platform engineer at a 50-500-person
  company**. Wants to cut Flutter-test-maintenance time. Cares
  about: SOC 2 readiness, SBOM, observability, Kubernetes. Reads:
  Increment, Pragmatic Engineer, vendor blog comparisons.
- **P3 — Agent-builder / AI engineer evaluating MCPs for their
  product**. Wants a reference implementation that's NOT a toy.
  Cares about: spec compliance, tool annotations, the dispatcher
  middleware design. Reads: Anthropic blog, MCP spec, GitHub
  trending.

### Tone

- **Confident, not loud.** The product proves itself in 30 seconds;
  the design shouldn't oversell. Cite real numbers (109 tools, 491
  tests, 0.2.0 release) over adjectives ("powerful", "robust").
- **Mature, not stuffy.** This is engineering-credible
  infrastructure that happens to be open-source. Visual register:
  closer to Linear or Vercel than to a Web3 launch page.
- **Mobile-first imagery.** The product DRIVES phones. Show phones.
  Not generic dashboards or abstract neural-network swirls.

### Visual language

Pick a small palette and stay disciplined. The recommended set:

| Role | Color | Hex | Notes |
|---|---|---|---|
| Primary | Orange | `#F76C28` | echoes the `branding.color: orange` in the GitHub Action |
| Secondary | Deep blue-black | `#0A0E1A` | landing background, code-snippet bg |
| Text on dark | Off-white | `#F4F0EA` | not pure white; warmer, less hospital |
| Accent (success) | Lime | `#A6E22E` | use SPARINGLY — only for "✓ passed" type signals |
| Accent (alert) | Coral | `#FF6E6E` | only for "× failed" / error states |
| Neutral grey | Slate | `#3B4252` | dividers, secondary labels |

Typography:

- **Display / headings**: Inter Tight 700 (or a stand-in: Space Grotesk)
- **Body**: Inter 400 / 500
- **Code**: JetBrains Mono 400 / 600

Iconography: outlined, 1.5px stroke, 24px grid, rounded line-caps.
Lucide-icons or Phosphor (regular weight) cover 95% of the needs.

### What's already in the repo (don't re-invent)

- A 109-tool catalogue at `docs/tools.md`
- The product narrative at `docs/article/building-flutter-dev-agents.md`
- The architecture story at `docs/architecture.md`
- Real screenshots in `~/.mcp_phone_controll/sessions/` you can pull
  for the demos (after capping with `phone-controll audit --cap`)
- Anti-stale-subprocess gotcha is the #1 ops story — see
  `docs/runbook.md` if you need credibility for "this is a real
  production tool".

---

## The brief pack

Each brief below has a stable filename + slug so you can hand them
out individually:

| File | Asset | Format | Effort | Audience |
|---|---|---|---|---|
| `brief-01-logo.md` | Logo + brand mark | SVG + PNG (4 sizes) | 1 day | all |
| `brief-02-social-preview.md` | GitHub social preview image | 1280×640 PNG | 2 hours | P1, P3 |
| `brief-03-landing-page.md` | Landing-page design system | Figma file + responsive | 3-5 days | all |
| `brief-04-architecture-diagram.md` | Agent-loop architecture diagram | SVG, ~1600×900 | 4 hours | P2, P3 |
| `brief-05-demo-video.md` | 90-second demo video | MP4 1080p, voiceover script | 2-3 days | P1 |
| `brief-06-pitch-deck.md` | 10-slide pitch deck template | Keynote/Figma | 1 day | P2 (sales) |

Total: ~12 person-days of design work for the full pack. The first
three briefs (1+2+3) deliver 80% of the value in ~7 days; the rest
are launch-week assets.

## Order to ship in

1. **Logo first.** Everything else references it. (Brief 01)
2. **Social preview second.** It's how the project is discovered.
   (Brief 02)
3. **Architecture diagram third.** It's the single highest-leverage
   asset for the P3 audience (agent-builders) and unblocks the
   landing page hero. (Brief 04)
4. **Landing page.** With the logo, preview, and diagram in hand,
   the page assembles itself. (Brief 03)
5. **Demo video.** Once the landing page has a hero, the video
   replaces the static hero on the page. (Brief 05)
6. **Pitch deck.** Built from the landing-page assets; this is
   sales work, not marketing. Lowest priority unless you're
   raising. (Brief 06)

## Working with Claude designer / Figma Make / similar

Every brief ends with a **Claude prompt** block — copy-paste it into
Claude (preferably with the `design:design-system` or
`design:design-handoff` skill loaded) and you'll get a usable
first draft. Then iterate with the designer using the same brief
as the shared reference.

## What is intentionally NOT in this pack

- **Stock photography**. Use the real screenshots from
  `~/.mcp_phone_controll/sessions/`. Stock photos of "person on
  phone" or "team at laptop" undermine the engineering-credible
  tone we worked for.
- **Animated illustrations of robots/brains**. The product
  orchestrates real devices. Show real devices.
- **Marketing buzzwords on assets**. No "AI-powered", no
  "revolutionary", no "next-generation". Show the work.
- **A separate documentation theme**. GitHub-flavoured Markdown is
  fine for the docs surface; effort goes to the landing instead.

If you need something not covered here, open a PR adding a new
`brief-NN-<slug>.md` following the same template.
