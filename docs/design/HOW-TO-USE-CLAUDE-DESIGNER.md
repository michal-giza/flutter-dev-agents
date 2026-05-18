# How to use Claude for the design briefs

Practical walkthrough: which Claude surface to use for which brief,
how to paste the prompt, how to iterate, what to commit.

There's no single "Claude Designer" app. Three Claude surfaces work
for different parts of design work — this doc tells you which one
to open per brief.

## The three surfaces

| Surface | What it produces | Best for |
|---|---|---|
| **Claude.ai (web)** with artifacts | HTML, SVG, React components rendered live | logos (SVG), social previews (HTML/CSS), landing page (HTML), architecture diagram (SVG) |
| **Claude Code** with `design:` skills | Critique, handoff specs, accessibility audits, UX copy review | refining a draft you already have, checking WCAG, generating dev handoff specs |
| **Claude API / Projects** with full context | Long iteration loops with the codebase loaded | landing-page sections that need to match real product behavior |

You'll mostly use **Claude.ai (web)** for first drafts, then drop
into **Claude Code** to critique and refine. The two surfaces
complement each other — generation vs review.

## Setup (5 minutes, one time)

1. **Open Claude.ai** — make sure you're on a plan that includes
   artifacts (Sonnet 4.6 or newer; Free tier works but Pro
   gives more usage headroom for design work).
2. **In Claude Code** (this CLI), the design skills are
   auto-discoverable as `design:design-handoff`,
   `design:design-critique`, `design:design-system`,
   `design:ux-copy`, `design:accessibility-review`. They activate
   when you say `/design-critique` or describe a relevant task.
3. **For each brief**, you'll paste the bottom prompt block of the
   brief file into Claude.ai. Use `Cat brief-01-logo.md` from the
   terminal or open the file in your editor and copy the prompt.

## End-to-end worked example: ship the logo

Time budget: ~30 minutes of your time + a few minutes of Claude
processing.

### Step 1 — generate first draft in Claude.ai

1. Open Claude.ai → new conversation.
2. Paste the entire prompt block from
   `docs/design/brief-01-logo.md` (the section under
   `## Claude prompt`). Sample:

   > _You are designing a logo for `flutter-dev-agents`, an MCP
   > server that lets autonomous agents build, deploy, and test
   > Flutter apps on real iPhones and Android phones. […]_

3. Claude returns an SVG inside an artifact panel. You see it
   rendered live.

4. If you only get text and no rendered SVG, add a follow-up:
   > _"Render the SVG as an artifact so I can see it. Keep the
   > 32×32 viewbox."_

### Step 2 — iterate

Look at the rendered logo. Ask Claude to refine specifically:

> _"This is concept 1 (tap-target). I like the reticle but the
> phone-screen silhouette is too literal — try making it a single
> abstract rectangle with rounded corners. Keep the reticle but
> move it to the lower-third intersection."_

OR:

> _"Show me both concepts side by side so I can pick. Concept 1
> (tap-target) and concept 2 (signal-tower glyph) as two separate
> SVG artifacts."_

OR test the recognizability gate:

> _"Show me how concept 1 renders at 16×16 — is it still
> legible? Also generate the favicon (32×32 ICO equivalent as a
> small SVG)."_

Loop 3-5 times. After 5 iterations you have either a logo you like
or evidence that this concept won't work and you should pivot.

### Step 3 — critique with Claude Code

Once you have a draft you don't hate, swap surfaces:

1. Save the artifact SVG locally:
   `docs/design/assets/logo/draft-v1.svg`.
2. In Claude Code (this CLI), run:
   ```
   /design-critique on docs/design/assets/logo/draft-v1.svg
   given the brand foundations in docs/design/README.md and the
   spec in docs/design/brief-01-logo.md.
   ```
3. The `design:design-critique` skill will flag things like:
   - Does it survive monochrome? (load-bearing for favicon)
   - Does it survive 16×16? (load-bearing for activity-bar icon)
   - Is there visual hierarchy when paired with the wordmark?
   - Anti-patterns from the brief — robot icons, AI clichés,
     wrong color register

Apply the critique, save as `draft-v2.svg`, repeat once if needed.

### Step 4 — accessibility check

For colors that touch text (the wordmark on dark backgrounds):

```
/accessibility-review the color contrast of the wordmark
(#F4F0EA on #0A0E1A) against WCAG AA AAA standards.
```

The `design:accessibility-review` skill returns:
- Contrast ratio (should be > 7:1 for AAA on small text)
- Whether the icon works for colorblind users (red-green especially)
- Whether the favicon stays legible at 16×16

### Step 5 — generate dev handoff

Once you're happy:

```
/design-handoff for docs/design/assets/logo/final.svg.
Produce specs a frontend dev would need to embed this on the
landing page (clear-space, minimum size, padding rules).
```

The output goes into `docs/design/handoff-logo.md`.

### Step 6 — commit

```bash
git add docs/design/assets/logo/ docs/design/handoff-logo.md
git commit -m "design: ship logo + brand mark per brief-01"
```

Done. ~30 min of your time, ~5 Claude turns, a logo that's
spec-compliant and dev-ready.

---

## Surface map for the rest of the briefs

### brief-02 — Social preview (1280×640)

- **Claude.ai**: paste the brief's prompt. Claude renders an
  HTML/CSS preview that simulates the 1280×640 PNG. Take a
  screenshot at the right resolution OR ask Claude to also
  produce a Python script that renders the HTML to PNG via
  Playwright.
- **Claude Code** for critique: `/design-critique` against the
  brief; specifically check the "reads at 400px width" criterion.
- **Test**: paste your repo URL into [opengraph.xyz](https://opengraph.xyz)
  to see how the preview will look on social platforms.

### brief-03 — Landing page

- **Claude.ai**: paste the prompt; Claude produces an HTML/CSS
  artifact for each section. Build it up section by section
  rather than all at once.
- **Claude Code**: use `design:design-system` to extract the
  emerging design system (colors / type / spacing tokens) into a
  Figma-compatible JSON or Tailwind config.
- **`design:ux-copy`**: refine every CTA + headline. Ask for
  three alternatives per line; pick the strongest.
- **`design:accessibility-review`**: full WCAG audit of the page.

### brief-04 — Architecture diagram

- **Claude.ai**: paste the prompt. Claude generates the SVG via
  either:
  1. Hand-drawn SVG paths (gives you full control)
  2. Mermaid diagram (faster, less control)

  For brief-04 explicitly, Mermaid is too rigid — ask for raw SVG.
- **Iteration prompt**: _"Show me the same diagram but with the
  middleware chain expanded to name every middleware
  (PatrolGuard, RateLimiter, ProgressLog, OutputTruncation,
  ImageSafetyNet, TraceRecorder, AutoNarrate)."_
- **Compact variant**: _"Now produce the 800×450 compact variant
  with only the load-bearing labels — keep the loop visible at
  400px width."_

### brief-05 — Demo video

Claude doesn't generate videos directly. Use this loop:

1. **Claude.ai**: paste the prompt. Claude produces the captions
   + the timing script + a shot list.
2. **Record** the actual screen + phone yourself (or use
   QuickTime + a phone-mirroring app like Vysor for Android).
3. **Edit in iMovie / DaVinci Resolve / CapCut** with the
   timing script as your storyboard.
4. **Claude Code** for caption review: `/ux-copy critique on the
   .srt file — keep captions under 35 chars per line, 2 lines
   max`.

### brief-06 — Pitch deck

- **Claude.ai**: paste the prompt. Claude generates HTML/CSS
  slide layouts that you screenshot per slide, OR Markdown that
  you import into Keynote / Figma Slides via the markdown-to-
  slides path.
- **Best workflow**: ask Claude to produce the deck as a series
  of artifacts, one per slide. Easier to iterate on individual
  slides without re-rendering the whole deck.
- **Claude Code** for the comparison-table slide (slide 8):
  ```
  Help me make the comparison table in slide 8 truth-first —
  every competitor needs at least one ✓ next to their name.
  ```

## Iteration patterns that work

**Pattern 1 — "show me three options, I'll pick"**

> _"Generate three variants of the logo concept. Don't try to be
> safe; show me one minimal, one bold, one weird. I'll pick a
> direction."_

Useful when you don't know what you want yet.

**Pattern 2 — "critique then re-render"**

> _"Critique this draft like you're a senior brand designer at
> Linear. List the three biggest issues. Then re-render fixing the
> top one."_

Useful when you have something close but not right.

**Pattern 3 — "constraints first"**

> _"Before producing anything, list the 5 hardest constraints in
> this brief that the design will need to satisfy. Then show me
> the design only AFTER you've stated which constraint was hardest
> to satisfy and how you addressed it."_

Useful for high-stakes assets (logo, landing hero). Forces
explicit reasoning.

**Pattern 4 — "stress test at the extremes"**

> _"Render this logo as: a 16×16 favicon, a 1024×1024 splash, a
> monochrome silhouette, an animated GIF morphing between concepts
> 1 and 2. If any version breaks, identify which constraint is
> the load-bearing one."_

Useful for finding which design decisions can't survive contact
with reality.

## Common pitfalls

| Pitfall | Fix |
|---|---|
| Claude generates marketing-tropes (AI brain, robot, gradient mesh) | Re-paste the "anti-patterns" section of the brief; ask Claude to acknowledge it explicitly before generating |
| Output looks generic / startup-y | Add to your prompt: _"this should look like Linear or Vercel, not a Web3 launch. Show me 3 inspirations from real shipped products and explain which one matches our tone"_ |
| Colors drift from the palette | Re-state the palette explicitly in every iteration prompt; don't trust memory across turns |
| Logo concept 1 keeps mutating across iterations | Save each version as a separate artifact name; refer back to "draft-v1" specifically |
| Landing page feels like a tutorial | Add: _"this is a conversion surface, not docs. Each section needs ONE CTA, not three"_ |
| Architecture diagram becomes a UML monster | Constrain: _"max 12 boxes, max 8 arrows. If you need more, the abstraction level is wrong"_ |

## When to NOT use Claude

- **For the final hero image of the landing page** — once you
  pick a direction, hand it to a real designer for the last 10%.
  Claude is great for 0 → 80%; 80 → 100% benefits from human
  taste.
- **For the video edit** — Claude can write the script, you cut
  the video.
- **For brand strategy** — Claude can refine an existing brand;
  it's a poor first-mover on "who are we?"

## Where the assets live

Once shipped, the layout is:

```
docs/design/
├── README.md                     # brand foundations + index
├── brief-01-logo.md              # this is the brief
├── brief-02-social-preview.md
├── …
├── HOW-TO-USE-CLAUDE-DESIGNER.md # this file
├── handoff-logo.md               # dev-handoff specs (post-design)
├── handoff-landing.md
└── assets/
    ├── logo/
    │   ├── mark.svg
    │   ├── wordmark-light.svg
    │   ├── wordmark-dark.svg
    │   ├── favicon.ico
    │   └── mark@1024.png
    ├── social-preview.png
    ├── architecture.svg
    └── …
```

Commit each asset with a short message:
`design: ship <asset> per brief-NN`. Reviewers can verify the
asset against the brief without needing to see the design tool.

## Cost / time benchmarks

Rough numbers from doing this kind of pack with Claude:

| Asset | Claude turns | Your time | Quality ceiling |
|---|---|---|---|
| Logo (icon + wordmark) | 10-15 | 30-60 min | ~85% of what a freelancer at $80/h delivers in a week |
| Social preview | 3-5 | 15-30 min | ~95% — Claude is great at fixed-layout typography |
| Architecture diagram | 8-12 | 45-90 min | ~80% — domain accuracy is the issue, not aesthetics |
| Landing page | 30-50 | 4-8 hours | ~70% — needs human taste for the final hero + spacing |
| Pitch deck | 20-30 | 2-4 hours | ~85% — text-heavy, Claude excels |
| Demo video | n/a (manual edit) | 4-8 hours of editing | depends entirely on the raw footage |

Free Claude.ai tier gets you ~10 messages per few hours, enough
for ~1-2 assets per session. Pro tier lets you do the whole pack
in a single afternoon if you push.

## TL;DR

1. Open `docs/design/brief-01-logo.md`.
2. Copy the `## Claude prompt` block at the bottom.
3. Paste into Claude.ai.
4. Iterate using the patterns above (3-5 turns).
5. Save the SVG, run `/design-critique` here in Claude Code.
6. Apply critique, save final, commit.
7. Move to brief-02. Repeat.

Total time: ~7 days for the full pack solo, ~3 days with a
freelancer doing the polish. Either way, you're shipping the
visual layer in less than two weeks.
