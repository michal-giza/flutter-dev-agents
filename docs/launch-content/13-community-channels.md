# 13 · Community channels — Patrol Slack + Flutter Discord

**Effort:** 15 minutes total
**Why:** These are the highest-signal-to-noise audiences for this specific tool. People in the Patrol Slack are literally building Flutter integration tests today — most likely to become real users.

---

## A · Patrol Slack

**Channel:** `#general` and `#help`
**Join URL:** https://patrol.leancode.co/community — official Patrol community link
**Audience:** Patrol maintainers + every team using Patrol in production
**Audience size:** ~3,000 members at the time of writing

### Etiquette

Patrol Slack is **maintained by LeanCode** (the company behind Patrol). They're friendly toward MCP/agent-driven testing — your MCP literally uses their framework — but the community norm is **provide value first, plug second**.

**Don't**:
- Post the LinkedIn copy verbatim.
- @ -mention the maintainers asking for amplification.
- Cross-post to every channel.

**Do**:
- Lead with a genuine question or technical observation.
- Frame this as "I built something on top of Patrol" not "look at my project."
- Be available to answer questions — Slack threads die fast.

### Message to post in #general

```
👋 Long-time Patrol user here. Open-sourced something today that builds on Patrol —
flutter-dev-agents (https://github.com/michal-giza/flutter-dev-agents), an MCP
server that lets Claude / Cursor / local LLMs drive Patrol tests on real iPhones +
Androids.

Cross-session device locks so multiple Claude windows can run different Patrol
tests on different devices without colliding. Apache 2.0.

Genuinely curious for the Patrol community's opinion on two things:

1. Should the agent surface `run_patrol_test` as a single tool, or break it
   into start_patrol_session / send_command / read_outcome so agents can interact
   with the test mid-run? Today I went with the single-tool approach but I'm not
   sure that's right for longer Patrol flows.

2. The MCP wraps the Patrol CLI invocation. Would it be useful to skip the CLI
   and talk to Patrol's host server directly? I avoided that because the CLI is
   the documented stable surface, but happy to go deeper if anyone has been doing
   this.

Happy to demo via DM if anyone wants to see it in action against a real device.
```

### Message to post in #help (separate post)

Only do this if you genuinely want help. Don't promote here.

```
For folks running Patrol in CI: how are you handling the "Android emulator on
Linux runner" topology today? I'm working on a Linux container path for my MCP's
CI integration (docs link in profile) and curious what's working / breaking for
people in production.
```

### What to do after the message lands

- Reply to anyone within 30 minutes during the window after posting.
- If a Patrol maintainer engages, ask them — privately, via DM — if a brief technical conversation about cross-tool integration would be useful. **Don't ask for amplification.**
- If they offer to RT / cross-post unsolicited, accept graciously.

---

## B · Flutter Community Discord

**Server invite:** https://discord.gg/flutter (official invite)
**Audience:** ~50,000 members; mix of beginners and pros
**Where to post:**
  - `#showcase` — explicit "show your work" channel
  - `#testing` — relevant subject channel (NOT `#help`)

### #showcase post

```
**flutter-dev-agents** — first MCP server for autonomous Flutter testing on real
phones, just open-sourced.

Lets Claude / Cursor / local LLMs build, deploy, and run Patrol tests on real
iPhones + Androids. 110 tools, Apache 2.0, MCP 2025-06-18 compliant.

📦 `pip install mcp-phone-controll`
🐙 https://github.com/michal-giza/flutter-dev-agents
🚀 5-min onboarding: github.com/michal-giza/flutter-dev-agents/blob/main/docs/GETTING-STARTED.md

Built solo over the past month while dogfooding on a Galaxy S25 + iPhone 15. Real
production fixes already merged: Polish-localization tap_text (NBSP fold), iOS
17+ RSD routing, cross-session device locks, BASIC/INTERMEDIATE/EXPERT tool tiers
for hosts with tool-count ceilings.

Would love feedback from anyone building production Flutter test suites. PRs and
issues welcome.
```

### #testing post (more targeted, slightly different framing)

```
For anyone who's been writing Patrol tests and feeling the "selector maintenance
tax" (30-50% of mobile QA hours per Drizz 2026): I open-sourced a tool today that
lets autonomous agents drive Patrol on real devices.

It's `flutter-dev-agents` on GitHub — an MCP server. Works with Claude Desktop,
Claude Code, Cursor, or any OpenAI-compat local LLM via the HTTP adapter.

The headline win for me: tap_text auto-handles NFC normalization + NBSP fold +
case-fold fallback. The Polish "Podczas używania aplikacji" dialog (which is
encoded with NBSP between words) now works without manual escape sequences.

Curious if anyone is running Patrol against Polish/French/German locales today
— would love to compare notes.

Repo: https://github.com/michal-giza/flutter-dev-agents
```

### Etiquette

- Don't cross-post to >2 channels in the same hour.
- Don't @ -everyone or @ -mods.
- Use Discord's native code block syntax for the install command — it auto-formats.

---

## C · Anthropic Discord

**Server invite:** https://discord.gg/anthropic (official)
**Channel:** `#mcp` — the MCP-specific channel
**Audience size:** ~10,000 members; concentrated around MCP builders

### Message

```
Hey 👋 — just released a production MCP server I built over the past month:
**flutter-dev-agents** (https://github.com/michal-giza/flutter-dev-agents),
Apache 2.0, 110 tools for driving real iPhones + Androids via MCP.

Notable from an MCP-spec implementation standpoint:

• Implements MCP 2025-06-18 including tool annotations (readOnly /
  destructive / idempotent / openWorld) on all 110 tools.
• outputSchema infrastructure with a regression-prevention test that
  scans every descriptor — caught two array-typed schemas I shipped that
  would have silently dropped the server in Claude Code's Zod validator.
• Tiered tool surface (MCP_TOOL_TIER=basic|intermediate|expert) for hosts
  with undocumented tool-count ceilings. Anyone else thinking about this
  as a spec-level concern, or is it strictly a host-by-host issue?
• Cross-session locks (filesystem-coordinated) so concurrent MCP servers
  can share underlying resources safely. Documented as an ADR.

The repo's docs/ has 7 ADRs documenting the load-bearing decisions if
anyone's into that kind of writeup.

Genuinely curious if my approach to the tool-count ceiling makes sense, or
if there's a cleaner pattern emerging from your projects.
```

### Etiquette

- This community is technical-first. Cut the marketing language.
- Don't expect virality — expect 2-5 thoughtful responses, which is the actual goal.
- Anthropic devrel sometimes engages — if so, treat it as a peer conversation, not a sales opportunity.

---

## D · MCP-specific community channels (lower volume, high signal)

These are smaller but **everyone in them is building MCPs**:

- **mcp-meet Discord** (community-run): https://discord.gg/mcp
- **r/ModelContextProtocol** subreddit: less active but indexable
- **Hacker News thread on MCP** (when a relevant one is active)

Use these as **follow-up** during week 1, not launch day. Spread out the engagement.

---

## E · Direct outreach (DM, post-launch)

A handful of people whose work yours complements directly. **Do this on day 2-3, after the main launch wave**, not day 1:

| Person/Project | Channel | Why |
|---|---|---|
| **LeanCode Patrol team** | Patrol Slack DM or GitHub issue | Your MCP literally uses their framework; they may RT or feature on their changelog |
| **Maintainer of mobile-mcp** (iOS sim only) | GitHub | Complementary projects; suggest a cross-link |
| **Whoever wrote the most-starred awesome-mcp list** | GitHub | Friendly head-up that you've PR'd it |
| **Drizz** (if you cite their survey) | Their landing-page contact form | Courtesy notification + offer to provide data back |

Tone for these DMs is "fellow indie builder," not "potential customer / partner." Be specific about what you appreciate about their work, what you've built, and zero asks. If they engage, great; if not, no follow-up.

---

## What success looks like across community channels

Different success criteria than HN / LinkedIn:

- **Patrol Slack**: 1-2 thoughtful technical questions from real Patrol users → that's a win. A maintainer DM is a major win.
- **Flutter Discord**: 5-15 reactions to the showcase post; 1-3 follow-up questions in thread.
- **Anthropic Discord**: 1-2 spec-level technical conversations. The Anthropic team occasionally engages directly.

These channels deliver **the highest-quality users** but the **lowest absolute numbers**. The post-launch DMs that turn into "I'm using this in production at $COMPANY" almost always trace back to one of these channels, not LinkedIn.
