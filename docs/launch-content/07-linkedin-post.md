# 7 · LinkedIn launch post

**Strategy:** post ONE variant today/tomorrow, then space the
other two by ~7 days each so they don't fight each other in
LinkedIn's feed algorithm.

**Best time to post (your time zone, Europe):**
- Tuesday/Wednesday/Thursday between **8:00–10:00 CET** —
  catches both EU and US-East morning scrolls.
- Avoid Friday afternoon and Monday morning (lowest engagement
  windows globally).

**Format rules LinkedIn rewards in 2026:**
- First 3 lines visible without "see more" — front-load the value prop.
- 1300–1900 chars total (the algorithm currently buries posts > 2200).
- 3–5 line breaks (LinkedIn now renders these as paragraph breaks).
- Ask one specific question in the last paragraph (≥ 1 comment lifts reach 2–3×).
- 3–5 hashtags MAX, at the end. More than 5 is now penalized.

---

## ⭐ Variant A — RECOMMENDED for the first post

**Audience:** Flutter devs + mobile QA leads. Highest reach in your
direct network. Post this one **first**.

```
I just shipped the first MCP server that lets autonomous agents test Flutter apps on real iPhones and Android devices.

It's called flutter-dev-agents — Apache 2.0, v0.2.1 today.

The wedge: every "AI-driven mobile testing" tool I could find was either iOS-simulator-only, web-only, or wrapped a cloud farm with $$ per test minute. None gave Claude (or any local LLM) safe, structured access to a phone on your actual desk.

So I built 110 tools across:
• Android — uiautomator2 + adb. Polish-localization-aware tap_text (NBSP + diacritic fold), Samsung One UI tap fallback.
• iOS — WebDriverAgent + pymobiledevice3. iOS 17+ --rsd routing, signing via team_id, DDI auto-mount.
• Flutter — Patrol + flutter run --machine. tap_and_verify, assert_no_errors_since, hot-reload, debug-log streaming.

Field-bug driven. Every fix in the 0.2.1 changelog came from a real overnight bot crash on a Samsung S25 or iPhone 15. The runbook walks through the top-10 failure modes with the exact remediation each one needs.

Production hardening that took longer than the tools themselves: CycloneDX SBOM, pip-audit CVE gating, JSON logs, Prometheus /metrics, k8s health/ready, Docker image, GitHub Action wrapper, 7 ADRs documenting load-bearing decisions, 556 hermetic tests + 5 real-device tests.

Works with Claude Desktop, Claude Code, Cursor — and any OpenAI-compat local LLM via the HTTP adapter.

5-minute install + the full integrations guide at:
github.com/michal-giza/flutter-dev-agents

Question for the Flutter community: what's the single test in your suite you'd most love to delegate to an agent? Reply in the comments — I'll prioritize the next batch of tools around the answers.

#Flutter #MCP #MobileQA #Claude #TestAutomation
```

**Character count:** ~1,820 (within the sweet spot)
**Why this works:**
- First line is one sentence and has the value prop.
- "wedge" framing — explains competitive positioning without naming competitors directly.
- Concrete bullets > adjective lists.
- Real bug stories (Samsung S25, iPhone 15) feel earned.
- Question at the end is specific and actionable (not "what do you think?").

---

## Variant B — for the MCP / agent-builder community

**Audience:** people building agents, AI engineers. Post 7 days
after Variant A in MCP-focused groups (Anthropic Discord, AI
Engineering subs, r/LocalLLaMA).

```
v0.2.1 of flutter-dev-agents shipped today — a production MCP server for autonomous Flutter testing on real mobile devices.

Useful as a reference implementation for the MCP 2025-06-18 patterns:

• Tool annotations (readOnlyHint, destructiveHint, idempotentHint, openWorldHint) on all 110 tools via a centralized classifier — hosts gate destructive ops at the UX layer.
• outputSchema infrastructure with dataclass_to_json_schema() helper. Migration to all tools planned; tripwire test guards against array-typed schemas (which would silently drop the server in Claude Code's Zod validator — bit me once).
• Contract snapshot test on tools/list — docs/tools-contract.json fails CI on silent drift.
• Path-traversal guards split into two tiers (strict for content/code, project-permissive for project paths) — generalized to all 9 path-accepting tools.
• Hypothesis-based dispatcher fuzz (opt-in via MCP_FUZZ=1).
• Tiered tool surface (MCP_TOOL_TIER=basic | intermediate | expert) so the 110-tool catalog fits under Cursor's 40-tool cap and Claude Desktop's undocumented UI ceiling.

Lessons learned the hard way (all documented as ADRs):

• Image-cap defense in depth — three production "2000 px API limit" incidents drove us to per-use-case + dispatcher safety-net + post-cap verification + a checker tool (inspect_image_safety) that agents call before Read on any image from another MCP.
• Cross-session device locks via filesystem (not memory) — 4 concurrent Claude windows can drive 4 phones safely.
• Patrol guard middleware refuses raw tap_text after prepare_for_test — prevents drift, with system=true escape hatch for OS dialogs.

Apache 2.0, 556 tests, on PyPI as mcp-phone-controll.

github.com/michal-giza/flutter-dev-agents

Curious — for anyone running production MCPs at scale: what's the failure mode you wish the spec made impossible? I'd love to fold the answer back into the contract tests we run on every commit.

#MCP #ModelContextProtocol #Claude #AgentDevelopment #AIEngineering
```

**Character count:** ~1,940
**Why this works:** technical-depth signals serious tool. Asks a question only experienced MCP builders can answer (filters for high-quality comments).

---

## Variant C — for enterprise dev-platform / QA-leadership audience

**Audience:** engineering managers, dev-platform leads. Post 14 days
after Variant A. Best for LinkedIn groups: "Mobile QA", "DevPlatform",
"Engineering Leadership".

```
If your mobile-QA team works in Flutter, this might be worth 15 minutes of their time:

flutter-dev-agents — an MCP server that lets autonomous agents drive your existing test suite on real iPhones + Android devices. Shipped v0.2.1, Apache 2.0.

The reality on most mobile-QA teams: 30–50% of engineering hours go to selector maintenance (Drizz 2026). Patrol/Appium tests pass green today, then break tomorrow because Android's permission-dialog label shifted from "Allow" to "While using the app" — and nobody catches it until the next regression run.

Agents close that loop, but until now there was no production-grade MCP that gave them safe, structured access to real phones.

What "production-grade" means in this release:

• CycloneDX SBOM generated per commit (Apache 2.0 supply-chain compliance).
• pip-audit gating in CI — caught 2 real CVEs on first scan, fixed same commit.
• SECURITY.md with 3-day ack / 10-day triage / 5-day critical patch SLAs.
• Top-10 production-failure runbook (docs/runbook.md) — covers iOS 17+ RSD routing, WDA team_id signing, Polish-localization tap failures, the 2000 px API limit recovery loop, and every real bug we hit in the first 30 days of overnight runs.
• Prometheus /metrics, k8s /health + /ready, Docker image with multi-arch build, GitHub Action wrapper for one-line CI integration.
• Multi-tenant safety: cross-session device locks so multiple agents don't collide.
• 556 hermetic tests + 5 real-device tests (gated on MCP_REAL_DEVICE=1).

One-line GitHub Actions integration:

  - uses: michal-giza/flutter-dev-agents/.github/actions/run-test-plan
    with:
      plan: integration_test/plans/smoke.yaml

90-second walkthrough + the full architecture write-up:
github.com/michal-giza/flutter-dev-agents

For QA leaders: what % of your team's hours go to selector / locator maintenance today? Genuinely curious where the real cost lives — happy to share the playbook we've used to cut it.

#FlutterDev #MobileQA #DevPlatform #EngineeringLeadership #TestAutomation
```

**Character count:** ~2,030 (right at the upper limit — slightly over but enterprise audience reads longer)
**Why this works:** leads with the cost narrative ("30–50% of hours"), then proves rigor with concrete compliance signals. Question is calibrated for people who own a budget.

---

## Image attached to the LinkedIn post

LinkedIn's algorithm rewards posts with an attached visual.
Options in priority order:

1. **Screenshot of the README hero** — easiest. Shows tagline + badges + first paragraph.
2. **30-second GIF demo** — record yourself: "select_device → take_screenshot → tap_text → tap_and_verify → release_device" sequence. Compress to < 8 MB so LinkedIn auto-plays it.
3. **The social preview card** (1280×640) — same image as the GitHub social preview. Reusable across all 3 posts.

If you have time for only one, do #1 today and add #2 to a
follow-up comment 24 hours later (separately-posted images extend
post lifespan).

## After posting — first 60 minutes are critical

LinkedIn's algorithm decides reach within the first hour:

1. **Reply to every comment within ~10 minutes** for the first hour.
2. **Don't share the post into private DMs immediately** — LinkedIn marks that as inorganic distribution.
3. **Like, don't comment, on your own post**. Self-comments dilute reach.
4. **DM 5–10 known supporters BEFORE posting** asking them to comment (not just like) within the first hour. Genuine comments lift reach 3–5×.

## What to do if a variant flops

Threshold: if a post gets <100 impressions in the first 6 hours,
LinkedIn has decided not to amplify it. Don't retry the same post —
the algorithm caches the verdict. Re-frame and publish a different
variant 2 weeks later from a different angle.
