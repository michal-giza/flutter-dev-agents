# Brief 02 — GitHub social preview image

## Goal

The 1280×640 PNG that GitHub embeds when the repo URL is shared on
Twitter/X, LinkedIn, Slack, Discord, etc. This is the **first**
impression for 90% of new visitors.

## Audience

Primarily P1 (indie shipper) and P3 (agent-builder) — the people
who discover the repo through link-sharing. P2 (enterprise QA) gets
served via the landing page instead.

## Specs

- **Format**: PNG, 1280 × 640, sRGB, < 1 MB.
- **GitHub upload location**: Settings → Social preview → Upload.
- Must remain legible after social-platform compression and at
  small embed sizes (e.g. Slack unfurl ~400px wide).

## Layout

```
┌────────────────────────────────────────────────────────┐
│                                                        │
│  [LOGO MARK 96×96]   flutter-dev-agents                │
│                                                        │
│  Your factory of Flutter agents.                       │
│  Build, deploy, and test Flutter apps on real          │
│  iPhones + Androids — autonomously, from any agent.    │
│                                                        │
│  ────────────────────────────────────────────────      │
│                                                        │
│  ✓ 109 tools     ✓ MCP 2025-06-18      ✓ Apache 2.0    │
│  ✓ 491 tests     ✓ SBOM + CVE scan     ✓ 0.2.0         │
│                                                        │
└────────────────────────────────────────────────────────┘
```

## Visual treatment

- **Background**: solid `#0A0E1A` (deep blue-black) with a SUBTLE
  noise texture (3-5% opacity, monochrome). No gradients.
- **Logo mark**: top-left, 96×96, primary orange. Wordmark to the
  right in off-white.
- **Tagline + supporting line**: directly under the lockup, off-white,
  ~48px and ~24px respectively. Wrap to two lines max.
- **Stat strip**: at the bottom 1/3, in a single row, separated by
  generous space (~120px). Lime checkmarks (`#A6E22E`), off-white
  text. JetBrains Mono 500 for the stats numbers and codes (109,
  491, 0.2.0, MCP-version string).
- **Right edge** (optional): a faint silhouette of a phone screen
  with three small UI bounding-boxes overlaid (the agent's
  `dump_ui` view). Maximum 20% opacity, monochrome slate. Only if
  it doesn't crowd the typography.

## What NOT to do

- No big "AI-POWERED" stamp.
- No screenshots of CLI output here (that goes on the landing).
- No multi-color gradient backgrounds — feels like an NFT drop.
- No 3D / isometric phones — flat 2D only.
- No people / hands / brains.

## Deliverables

- `docs/design/assets/social-preview.png` (1280×640)
- `docs/design/assets/social-preview@2x.png` (2560×1280 for hi-DPI
  preview tools)
- A 600×400 "compact" variant for Slack unfurls if the GitHub
  default doesn't render cleanly.

## Definition of done

- Tested in the "social-share preview" tab of opengraph.xyz against
  the actual repo URL.
- Reads cleanly when zoomed to 400px width (Slack thumbnail size).
- All stat numbers are CURRENT — pull from the latest commit's
  numbers (109 tools, 491 tests, 0.2.0).
- Uploaded via GitHub Settings → Social preview.

## Claude prompt (paste into a Designer skill)

```
Design a GitHub social preview image (1280×640 PNG) for
`flutter-dev-agents`.

Layout from top to bottom:
1. Top-left: logo mark (96×96, orange #F76C28) + wordmark
   `flutter-dev-agents` in Inter Tight 700, off-white #F4F0EA.
2. Below the lockup: tagline "Your factory of Flutter agents." in
   ~48px off-white, then a 2-line description in ~24px:
   "Build, deploy, and test Flutter apps on real iPhones + Androids
    — autonomously, from any agent."
3. A horizontal divider in slate grey.
4. Bottom stat strip in JetBrains Mono, with lime check-marks
   (#A6E22E):
   ✓ 109 tools     ✓ MCP 2025-06-18      ✓ Apache 2.0
   ✓ 491 tests     ✓ SBOM + CVE scan     ✓ 0.2.0
5. Optional: faint phone-screen silhouette on the right edge at
   20% opacity in slate grey.

Background: solid #0A0E1A with 3-5% monochrome noise. No
gradients. No 3D. No people. No "AI-POWERED" badges.

Output: a 1280×640 PNG and an SVG source. Also produce a 600×400
compact variant for Slack thumbnails.
```
