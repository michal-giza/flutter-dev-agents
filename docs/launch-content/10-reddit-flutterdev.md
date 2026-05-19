# 10 · r/FlutterDev

**URL:** https://www.reddit.com/r/FlutterDev/submit
**Effort:** 10 minutes to write + 1-2 hours to engage in comments
**Why:** 200K+ subscribers; heavily skews toward people building production Flutter apps. The community is sharp on tooling and **brutal about marketing-speak** — keep the post honest and concrete.

## When to submit

**Tuesday-Thursday, 12:30-13:30 CET.** Catches both EU lunch break and US East Coast morning. Avoid weekends (low engagement on tooling posts) and Mondays (filtered out as low-energy).

## Subreddit etiquette

r/FlutterDev's rules forbid:
- Pure promotion without technical content (your post is fine — it has both).
- Asking for upvotes / "share if you like this" / engagement-bait CTAs.
- Cross-posting without flair.

**Required**: pick the **"Plugin"** flair when submitting (your MCP is effectively tooling for Flutter testing).

## The post

### Title (≤ 100 chars)

```
I built an MCP server that lets Claude test my Flutter app on a real Galaxy S25 — open-sourced today
```

Why this title:
- First-person framing — Reddit rewards authenticity.
- "Real Galaxy S25" beats "real devices" — concrete > abstract.
- "Open-sourced today" signals "this is news, not promotion."
- No clickbait verbs ("game-changing", "shocking", etc.) — Reddit punishes those.

### Body (paste verbatim)

```
Long-time Flutter dev here. For the past month I've been building an
MCP server that lets autonomous agents (Claude, local LLMs via the
HTTP adapter) drive my Flutter apps on real iPhones and Android
devices. Open-sourced it today as `mcp-phone-controll`, Apache 2.0.

**Why I bothered**

Drizz's 2026 industry survey says mobile QA spends 30-50% of
engineering hours on selector maintenance. My own number was closer
to 40% — testWidgets that pass green today break tomorrow because
some Android permission dialog changed from "Allow" to "While using
the app." Agents can close that loop, but until now there was no
production-grade MCP that gave them safe access to a phone.

**What it does**

- 110 tools across Android (uiautomator2 + adb), iOS (WebDriverAgent
  + pymobiledevice3), and Flutter (Patrol + `flutter run --machine`).
- Cross-session device locks so 4 concurrent Claude windows can
  drive 4 phones without colliding. This was the headline win for
  me — I have 3 Flutter projects open daily.
- A "tiered tool surface" (BASIC=26 / INTERMEDIATE / EXPERT=110)
  via `MCP_TOOL_TIER=basic` because Claude Desktop has an
  undocumented tool-count ceiling that drops servers > ~50 tools.
- Polish-localization-aware `tap_text` (NBSP fold + NFC
  normalization + case-fold fallback) — burned an evening on
  "Podczas używania aplikacji" before fixing it properly.
- `tap_and_verify` + `assert_no_errors_since` enforce the
  verify-after-action discipline so agents don't drift past
  silent failures.

**What this is NOT**

- Not a Maestro replacement — Maestro is YAML-driven, you write
  tests. This is agent-driven, agent writes tests.
- Not BrowserStack — local-only, runs on your laptop / your CI
  runner. There's an HTTP adapter for k8s but no SaaS.
- Not "AI will replace tests" — it accelerates the iteration loop,
  it doesn't eliminate the test discipline.

**What's actually new (vs existing MCPs)**

Every other mobile MCP I could find was iOS-simulator-only
(`mobile-mcp` via idb), web-only (Playwright MCPs), or
desktop-only (computer-use). This is the first real-device-first
Flutter-first MCP I'm aware of.

**Honest gaps (deliberately on the roadmap, not pretending these
don't exist):**

- macOS-only for iOS (Xcode). Linux works for Android-only.
- Single-author maintenance right now. PRs and co-maintainers
  welcome.
- No hosted SaaS planned — explicitly "Not on the roadmap." Local-
  first is the security model; SaaS would break it.

**Tomorrow's PyPI install + Claude Code registration:**

```bash
pip install mcp-phone-controll
claude mcp add phone-controll -- python -m mcp_phone_controll
```

Then ask Claude: *"Using phone-controll, run mcp_ping and take a
screenshot of my Galaxy S25."*

**Links**

- GitHub: https://github.com/michal-giza/flutter-dev-agents
- PyPI: https://pypi.org/project/mcp-phone-controll/
- First-15-minutes guide:
  https://github.com/michal-giza/flutter-dev-agents/blob/main/docs/GETTING-STARTED.md
- Roadmap:
  https://github.com/michal-giza/flutter-dev-agents/blob/main/ROADMAP.md

**What I'd genuinely value feedback on**

1. Is "tap_text(text, system=True)" the right convention for OS-
   level dialogs, or should it be a separate tool entirely?
2. The 4 most-common gotchas I documented
   (`docs/operational-gotchas.md`) — are these the same ones you
   hit on real-device testing, or are there bigger ones I'm
   missing?
3. Anyone using Patrol in production with a 10+ engineer team —
   what would make this MCP useful to you specifically?

Happy to dig into anything in comments.
```

## Engagement strategy

**Reply to comments within 30 minutes for the first 2 hours.**
Reddit's algorithm weights "OP responsive in comments" heavily —
threads where OP disappears die fast.

**Comment patterns**:

| Comment type | Response pattern |
|---|---|
| "Cool, will try!" | "Thanks — if you hit any rough edges, the runbook covers the top 10 issues. DM me or file an issue." |
| Detailed technical question | Answer concretely, link to ADR or source file. Reddit users notice when you've actually written the code. |
| "How is this different from [Maestro/Appium/Patrol]?" | The FAQ has direct answers — paste the relevant 1-2 sentence excerpt. |
| Reasonable skepticism | Acknowledge the trade-off, don't oversell. "Yeah, the macOS-only iOS thing is real, here's the path to Linux containers on the roadmap." |
| Spam / negativity | Don't engage. Other community members or mods handle it. |
| "Can I help?" | YES — point at ROADMAP "Next" + the "help wanted" issues you'll add. |

## What to do AFTER the comment window

Two follow-up moves that compound:

1. **Update the post with a small "Day 1 takeaways"** edit if you got
   real feedback worth surfacing. Reddit rewards posts that evolve.

2. **Save the best technical questions** for a "FAQ from r/FlutterDev"
   section you can add to `docs/FAQ.md`. Future visitors arriving from
   Google searches see real questions, real answers.

## If the post tanks

r/FlutterDev sometimes dislikes "look at my project" posts. Mitigations
if the post is under 5 upvotes after 1 hour:

- DO NOT delete + repost. Mods see this.
- DO NOT ask anyone to upvote.
- DO consider rewriting and reposting in 90+ days with the case-study
  numbers from week-1 production use (way more credible).
- DO try r/programming or r/coding for a wider audience next time.

The Reddit ecosystem rewards persistence over splash. One mediocre
launch doesn't close the door — it just delays a successful one.
