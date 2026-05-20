# Roadmap

Public, honest roadmap. Three buckets — **Now**, **Next**, **Later** —
plus an explicit **Not on the roadmap** section so nobody wastes
time PR-ing things we won't merge.

> Last updated: **2026-05-19** (v0.2.2 shipped).
> Maintainer: [@michal-giza](https://github.com/michal-giza).
> Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Now (working on this in the open)

Things in flight right this week. Most have an open issue or PR
you can comment on or pick up.

- **Distribution wave — week 1 of public launch.** Submissions to
  PulseMCP, mcp.so, Smithery, Glama, 3 awesome-mcp lists, LinkedIn,
  Hacker News, dev.to, Twitter, Patrol Slack + Flutter Discord.
  Help wanted: confirm the `claude mcp add` and `pip install`
  instructions work clean on Linux + on a fresh Windows WSL2 box.
- **Week-1 production case study.** Daily journal entries in
  `docs/internal/case-study-journal/` will be extracted into a
  public `docs/case-study-week-1.md` once a week of real-use data
  is in.
- **Demo GIF for the launch post.** Script ready at
  `docs/design/demo-recording-script.md`; recording pending.

## Next (queued, ~4-8 week horizon)

Real intent to land. Order is rough priority but not strict.

- **0.3.0 — milestone**: smoothing the corners that
  came up during the v0.2.x patch series.
  - `inspect_image_safety` returning richer provenance (CRC of
    capped vs original, "produced-by-which-tool" trace).
  - `tap_text` + `find_element` returning the **top-3** candidate
    matches when ambiguity is detected, with confidence scores,
    so the agent can disambiguate without a second `dump_ui`.
  - `setup_webdriveragent` becoming idempotent on iOS major-version
    bumps (currently a manual prune of the cache marker is needed
    when the user upgrades iOS).
- **Linux-host Android emulator container** for CI scale. The
  current Dockerfile builds the MCP itself for Linux; what's
  missing is a sibling container running a headless Android
  emulator + adb-bridge so a GitHub Actions runner can do
  end-to-end Android testing without a Mac. Designed in
  `docs/architecture.md#container-topology`.
- **Detox framework recipe.** Same shape as the existing Patrol
  recipe; lets React Native teams adopt the same MCP surface.
  See `docs/adding_a_framework.md`.
- **XCUITest framework recipe.** Native iOS test runner for teams
  whose UI isn't Flutter.
- **More fully-worked scenarios in `examples/scenarios/`.** iOS
  flow, AR flow, CI flow, local-LLM flow. PRs especially welcome
  here — concrete user stories age well.

## Later (someday, fuzzy)

Real interest but not the right time. Don't expect these in
< 6 months.

- **Hosted device-farm bridge.** When the local-only model
  outgrows itself, expose a thin client that talks to a
  BrowserStack-style backend with the same tool surface. Note: the
  product remains local-first; this is an *escape hatch* for teams
  that genuinely need 50 OS-version combinations, not a SaaS pivot.
- **Native LSP MCP companion.** Watching the user's Dart files
  through the analysis server so the agent can read live
  diagnostics + provide code completions inline. Probably a
  separate package under `packages/lsp-companion/`.
- **IntelliJ / Android Studio openers.** Same shape as the existing
  VS Code openers; one method to add. Waiting on a user actually
  asking before building.
- **iOS Linux-container via remote tunneld.** The hard one. iOS
  device control requires Xcode → macOS host. There's a
  theoretical path via a macOS bastion serving remote tunneld over
  the network, but the latency + signing-chain complications make
  this strictly post-1.0.
- **`.code-workspace` multi-folder support.** Current
  `open_project_in_ide` opens one project per window. Multi-folder
  workspaces deferred because the cross-folder lock semantics
  aren't obvious.

## Not on the roadmap (won't merge — please don't PR)

- **A hosted SaaS version of the MCP.** The MCP protocol's whole
  point is local-first. A SaaS would defeat the safety model
  (filesystem locks, device USB, etc.) and add a vendor-lock-in
  layer this project explicitly avoids.
- **Windows-native iOS support.** iOS device control needs Xcode.
  Xcode is macOS-only. There is no path here. Windows users get
  Android via WSL2; iOS requires a Mac.
- **Closed-source plugins.** Apache 2.0 means inbound is the same
  license; we won't add a plugin loader that loads non-Apache
  code from the same process — security model can't survive it.
- **A custom auth layer for the HTTP adapter beyond API keys.**
  OAuth, SSO, mTLS — all out of scope. The HTTP adapter is meant
  to run behind your existing ingress (k8s gateway, nginx, Tailscale).
  Authentication is your ingress's job; the adapter's `MCP_HTTP_API_KEY`
  is the last-mile guard, not the front door.
- **A "smart agent" that pretends to be Claude.** The MCP exposes
  tools; it doesn't ship its own LLM-side agent. The bundled
  `examples/agent_loop*.py` are reference implementations, not
  shipping product. We won't merge a `phone_controll.agent` module
  that hides Claude/Ollama/etc. behind an opinionated wrapper.

## Versioning + release cadence

- **Patch** (`0.2.x`) — bug fixes, doc updates, CI changes,
  internal refactors. Released as needed, no calendar.
- **Minor** (`0.3.0`, `0.4.0`, ...) — new tools, new categories,
  additive features. Aim for one minor every ~6-8 weeks.
- **Major** (`1.0.0`) — when the public surface (tool names +
  envelope shapes) is judged stable enough to make breakage
  commitments. Currently targeting **Q4 2026** — the patch series
  is still finding real-world rough edges that occasionally
  require small breaking renames.

Breaking changes ride minor versions during pre-1.0; they ride
major versions post-1.0. Either way, every breaking change gets a
deprecation cycle through `describe_tool` warnings before removal.

## How to influence this roadmap

- **File an issue** with the `roadmap-input` label. Even a thumbs-
  up on an existing issue helps prioritize.
- **Pick a "Help wanted" issue.** Tagged on GitHub with
  `help-wanted`. Each carries an exit criteria the PR has to meet.
- **Write a scenario in `examples/scenarios/`** — concrete user
  stories are the strongest signal for "this should be a tool"
  decisions.
- **DM the maintainer** (`msquaregiza@gmail.com`) for anything
  enterprise-shaped or sensitive.

## Tracked publicly

The same buckets live as a GitHub Project:
https://github.com/users/michal-giza/projects/ (link will be added
once the project is created).

Items in **Now** should always match what's in flight on
github.com/michal-giza/flutter-dev-agents/pulls. If they don't,
the roadmap is stale — file an issue.
