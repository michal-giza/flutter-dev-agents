# Brief 04 — Architecture diagram

## Goal

A single SVG diagram that explains the **agent → MCP → device** loop
in 5 seconds. Becomes the landing-page hero visual and the GitHub
README header image. Saves us 200 words of explanation.

## Audience

Primarily P3 (agent-builders evaluating MCPs) and P2 (dev-platform
engineers). P1 doesn't need this — they just want the install.

## What it must communicate

1. The agent runs in a host (Claude Desktop, Claude Code, Cursor,
   or a custom loop) — separate process from the MCP.
2. The MCP is the **boundary** between the agent's reasoning and
   real devices. It exposes 109 typed tools.
3. The middleware chain (rate limit → image cap → trace recorder)
   sits inside the MCP, on every dispatch.
4. The router branches by platform: Android (adb), iOS physical
   (pymobiledevice3 + WDA), iOS sim (xcrun simctl + WDA-TCP).
5. Real phones, simulators, and emulators are the leaf nodes.
6. **Side channels**: `MCP_LOG_FORMAT=json` → log shipper;
   `/metrics` → Prometheus; `notify_webhook` → n8n / Slack.

## Layout

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   ┌─────────────────┐         ┌──────────────────────────────┐   │
│   │ HOST            │ stdio   │ MCP — mcp-phone-controll     │   │
│   │  Claude Desktop ├────────▶│                              │   │
│   │  Claude Code    │  or     │  ┌── middleware chain ──┐    │   │
│   │  Cursor         │  HTTP   │  │ rate-limit            │    │   │
│   │  (custom loop)  │         │  │ image-cap (1900 hard) │    │   │
│   │                 │         │  │ output-truncate       │    │   │
│   │  ▼ agent loop   │         │  │ patrol-guard          │    │   │
│   │   tool call →   │         │  │ trace-recorder        │    │   │
│   │   envelope ←    │         │  └──────────────────────┘    │   │
│   └─────────────────┘         │             ▼                │   │
│                               │     ┌── 109 tools ──┐         │   │
│                               │     │  basic (24)    │         │   │
│                               │     │  intermediate  │         │   │
│                               │     │  expert        │         │   │
│                               │     └────────────────┘         │   │
│                               │             ▼                  │   │
│                               │   ┌─ platform router ─┐         │   │
│                               │   │  android | ios-d  │         │   │
│                               │   │  ios-sim | wda    │         │   │
│                               │   └───────────────────┘         │   │
│                               └────────────┬────────────────────┘   │
│                                            │                        │
│            ┌──────┐    ┌─────────┐    ┌────▼─────┐    ┌─────────┐  │
│            │ adb  │    │  pmd3   │    │  simctl  │    │  WDA-TCP │  │
│            └──┬───┘    └────┬────┘    └────┬─────┘    └────┬─────┘  │
│               ▼              ▼              ▼               ▼       │
│         [Android]      [iPhone-15]      [iOS-sim]      [iOS-sim]    │
│         [emulator]                                                  │
└──────────────────────────────────────────────────────────────────┘

  Side channels:
    JSON logs → Sentry / Datadog / Honeycomb
    /metrics  → Prometheus
    notify_webhook → n8n / Slack / Linear / Discord
```

## Visual treatment

- **Style**: line-art / blueprint aesthetic. Single weight (1.5px),
  rounded corners (4px), boxes with thin borders, no fills (except
  for visual emphasis on the MCP boundary itself).
- **Box hierarchy**: HOST + MCP are the primary boxes (thicker
  border, slate fill at 8% opacity). Middleware chain + tools +
  router are secondary (thinner). Devices are leaf nodes (smallest,
  with a tiny silhouette icon — phone, simulator window).
- **Arrows**: thin (1px), with small arrowheads. Bidirectional where
  appropriate (request + response). Annotated with "stdio" / "HTTP"
  / "adb shell" labels in 11px JetBrains Mono.
- **Color usage**:
  - Primary orange `#F76C28` for the MCP boundary border and the
    "109 tools" emphasis.
  - Lime `#A6E22E` ONLY on the success-path arrow from envelope
    back to host.
  - Coral `#FF6E6E` ONLY on a small "blocked" annotation showing
    `WdaUnreachable` / `PathGuardFailure` as examples of typed
    rejections.
  - Everything else: slate grey `#3B4252` / off-white `#F4F0EA`.

## Two density variants

Ship TWO versions of the same diagram:

1. **Detailed** (for the landing-page hero + docs/architecture.md
   header): includes all middleware names, the tier breakdown, side
   channels.
2. **Compressed** (for the README + social cards): boxes only,
   maybe 60% of the labels, fits in 800×450.

## Specs

- **Format**: SVG (resolution-independent for the web; embeds in
  Markdown via `![](docs/design/assets/architecture.svg)`).
- **Detailed canvas**: 1600 × 900, viewBox preserved.
- **Compressed canvas**: 800 × 450, simplified.
- **Dark-mode variant**: same SVG with CSS that respects
  `prefers-color-scheme: dark`. Or two separate files
  (`architecture-light.svg`, `architecture-dark.svg`).
- **Annotated source**: include the Mermaid / draw.io / Figma
  source file in `docs/design/assets/architecture.fig` so future
  edits don't require reverse-engineering.

## Anti-patterns

- ❌ Robot/brain icons for "agent". Just use the word `AGENT`.
- ❌ Cloud icons between host and MCP — the MCP is local.
- ❌ Color-coded "good vs evil" arrows. Information should be in the
  labels, not the colors.
- ❌ 3D isometric. The blueprint vibe is the right register.
- ❌ Animated GIF version. Save the animation budget for the demo
  video.

## Deliverables

- `docs/design/assets/architecture.svg` (detailed)
- `docs/design/assets/architecture-compact.svg` (compressed)
- `docs/design/assets/architecture.fig` (source)
- A snapshot PNG @ 1600×900 for hosts that don't render SVG
- `docs/architecture.md` updated to reference the new SVG

## Definition of done

- Diagram explains the host → MCP → device → host loop in under 5
  seconds of looking.
- Every named middleware in the real codebase is on the diagram
  (or deliberately omitted with a "...etc" note).
- Dark-mode variant maintains WCAG AA contrast.
- The compact variant still reads at 400px width.

## Claude prompt

```
Design an architecture diagram for `flutter-dev-agents` MCP server.

It must show this loop in one visual:
- HOST (Claude Desktop / Code / Cursor) on the left, runs an agent
  loop (tool call → envelope back).
- MCP server in the middle, with: a middleware chain
  (rate-limit, image-cap with 1900-px hard ceiling, output-truncate,
  patrol-guard, trace-recorder), 109 tools split into basic/inter/
  expert tiers, and a platform router branching to adb / pmd3 /
  simctl / WDA-TCP.
- Real devices on the right: Android phone + emulator,
  iPhone-15, iOS simulator (×2 — one with WDA-TCP).
- Side channels: JSON logs → log shippers, /metrics → Prometheus,
  notify_webhook → n8n/Slack/Linear.

Style: line-art / blueprint, 1.5px stroke weight, 4px corner
radius, thin arrows with tiny arrowheads + 11px JetBrains Mono
labels. Mostly monochrome (slate grey #3B4252 on off-white #F4F0EA).
Primary orange #F76C28 only on the MCP boundary border and "109
tools" emphasis. Lime #A6E22E only on the success-path return
arrow. Coral #FF6E6E only on a small "WdaUnreachable" rejection
annotation.

Output TWO variants:
1. Detailed: 1600×900 viewBox, all middleware named, tier
   breakdown visible.
2. Compact: 800×450 viewBox, boxes-only, 60% of labels.

Both as SVG. Plus a dark-mode variant maintaining WCAG AA.

No robot icons. No cloud icons between host and MCP. No 3D /
isometric. No animation.
```
