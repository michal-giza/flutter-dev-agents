# Brief 01 — Logo + brand mark

## Goal

A wordmark + an icon-only mark that work across:
- GitHub repo avatar (full square)
- README header
- Landing-page nav bar
- VS Code extension activity-bar icon (when shipped)
- PyPI / npm package logo (16×16, 32×32, 256×256)
- Favicon (32×32 ICO)

## Audience

All three personas (P1, P2, P3). The mark needs to read as
"infrastructure for engineers", not "consumer app" or "AI startup".

## Concept direction

The product is a **bridge** between agents and physical mobile
devices. Two visual metaphors that work:

1. **Tap-target with telemetry.** A phone-screen silhouette with a
   precise tap-target reticle overlay, suggesting "guided control".
   Geometric, not skeuomorphic.
2. **Signal-tower glyph.** A stylised antenna / cross emitting two
   directional pulses (out to a phone, back to a brain/CLI). Conveys
   the bidirectional dispatch contract without being literal.

Pick ONE — don't ship both.

## Specs

### Wordmark

- `flutter-dev-agents` rendered in **Inter Tight 700**.
- Lowercase, hyphens preserved (this is the package name; consistency
  beats prettiness).
- Optionally: the `-` glyphs can be replaced with a single 2-pixel
  custom connector for tighter rhythm.
- Color: `#F76C28` (primary orange) on light, `#F4F0EA` (off-white)
  on dark. Never both at once.
- Inline icon-mark sits to the LEFT of the wordmark with 16px gap.

### Icon mark

- Square canvas, designed in a **32×32 grid** so it renders crisply
  at favicon sizes.
- Single-color SVG (primary orange) for light backgrounds, single-
  color off-white for dark backgrounds.
- A second "two-color" variant is OK for the landing-page hero —
  primary orange + slate grey accent — but the icon must remain
  recognizable in mono.
- No gradients. No drop shadows. No emoji-style 3D.

## Deliverables

- `logo-mark.svg` (icon only, 32×32 viewbox)
- `logo-mark.png` at 16, 32, 256, 1024 px (transparent bg)
- `logo-wordmark.svg` (full lockup, no fixed pixel size)
- `logo-wordmark-light.png` (1200px wide, dark-text-on-transparent)
- `logo-wordmark-dark.png` (1200px wide, light-text-on-transparent)
- `favicon.ico` (32×32)
- A short `design/logo-usage.md` explaining safe-area / minimum size

## Definition of done

- Mark is recognisable at **16×16** without anti-aliasing breakdown.
- Wordmark reads cleanly at **80px height** on a typical 1440px-wide
  laptop screen.
- Both monochrome variants exist; no asset relies on color alone.
- Files committed to `docs/design/assets/logo/` with a snapshot
  PNG at the top of `docs/design/README.md`.

## Claude prompt (paste into a Designer skill)

```
You are designing a logo for `flutter-dev-agents`, an MCP server
that lets autonomous agents build, deploy, and test Flutter apps on
real iPhones and Android phones.

Audience: engineering-credible developers (think Linear, Vercel, not
SaaS-marketing). Mature, confident, not loud.

Concept: pick ONE of these two directions and produce both an
icon-only mark and a wordmark in that direction:

1. "Tap-target with telemetry" — phone-screen silhouette with a
   precise reticle overlay, geometric not skeuomorphic.
2. "Signal-tower glyph" — stylised antenna / cross with two
   directional pulses (to a phone, back to a brain).

Constraints:
- Single primary color: #F76C28 (orange). Off-white #F4F0EA for
  dark variants.
- No gradients, no drop shadows, no 3D.
- Icon must read at 16×16 px.
- Wordmark uses Inter Tight 700, lowercase, hyphens preserved
  (`flutter-dev-agents`).
- Square 32×32 grid for the icon mark.

Output:
- The icon mark as an SVG.
- The wordmark with the icon to the left, 16px gap.
- A short paragraph explaining your choice between concept 1 or 2.
- Three failure-mode sketches: what would make this logo wrong
  (too cute, too literal, too generic) — so I know what to avoid
  in iterations.
```
