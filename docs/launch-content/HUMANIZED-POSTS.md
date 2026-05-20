# Humanized launch posts — ready to paste

Rewritten to sound like a real person telling a real story, not a
press release. Each version:

- Leads with a specific moment, not a feature list.
- Uses "I" naturally.
- Acknowledges weaknesses honestly.
- Mentions multiple real devices (Galaxy S25, Pixel 8 emulator, iPhone 15, iPhone 17 sim) as examples.
- Asks ONE specific question, not three vague ones.
- Avoids "revolutionary / game-changing / 10x" entirely.

**Choose the title that feels closest to how you'd actually
introduce this in person.** Don't second-guess; honesty reads.

---

## 1. r/FlutterDev — POST NOW

### 🏷️ Setup

- **URL**: https://www.reddit.com/r/FlutterDev/submit
- **Flair** (mandatory): pick `Plugin`
- **No tags** on Reddit beyond the flair

### TITLE — pick ONE (don't add emoji)

Variant 1 (recommended, story-driven):

```
After a month dogfooding it, I open-sourced the MCP server I built to let Claude drive my Flutter tests on real phones
```

Variant 2 (problem-led, shorter):

```
I got tired of debugging selector breaks at 2am, so I built an MCP that lets Claude test my Flutter app on a real Galaxy S25
```

Variant 3 (lowest-key — Reddit sometimes prefers understated):

```
Open-sourced today: flutter-dev-agents — an MCP server for testing Flutter apps on real iOS and Android devices
```

### BODY

```
Hey r/FlutterDev. Solo dev, been shipping Flutter apps for a few years. Posting because I open-sourced something today that I genuinely couldn't have launched without it being already battle-tested for a month against my own apps.

**The thing that broke me.**

You know that bug where the Android permission dialog button changes wording across OS versions — "Allow" on Android 13, "While using the app" on 14, and in Polish it's "Podczas używania aplikacji" but encoded with NBSP between words, so your tap_text fails byte-equality silently and the test just hangs there pretending everything's fine?

I lost half a Sunday to that one. Different version on iOS 17 vs iOS 26. The fix isn't hard, but the diagnosis is hours of "why is nothing happening" because the screenshot still shows the dialog and the logs still say "Tap dispatched" and the test still passes its 30-second wait. Selector maintenance was eating ~40% of my testing time and I was getting bitter about it.

**What I built.**

`flutter-dev-agents` — an MCP server that lets autonomous agents (Claude Desktop, Claude Code, Cursor, any OpenAI-compat local LLM) drive my Flutter apps on real Galaxy S25s, real iPhone 15s, Pixel 8 emulators, iPhone 17 simulators, whatever's plugged in. 110 tools across:

- **Android**: uiautomator2 + raw `adb` fallback (Samsung One UI sometimes drops accessibility taps; adb-shell input bypasses that).
- **iOS**: WebDriverAgent on the device, pymobiledevice3 for lockdown services. The iOS 17+ `--rsd` routing through tunneld's HTTP API took me a weekend to debug — it's now documented as an ADR so nobody else has to.
- **Flutter-specific**: Patrol integration, `flutter run --machine` for hot-reload control, debug-log streaming, widget tree dumps.

The `tap_text` thing I described above? Fixed properly now — NFC normalization plus folding NBSP/NNBSP/thin-space/zero-width-space, with case-fold fallback in substring mode. `tap_text("Podczas używania aplikacji", system=True)` just works regardless of which Unicode whitespace variant the Android Settings team decided to ship that week.

**What's genuinely different vs other mobile MCPs**

I checked the existing landscape before posting — there are mobile MCPs out there. Most are iOS-simulator-only (mobile-next/mobile-mcp, ambar/simctl-mcp), or Android-only (martingeidobler/android-mcp-server), or Figma→Flutter codegen (mhmzdev/Figma-Flutter-MCP, different use case).

What this one does that I didn't find elsewhere:

- **Cross-session device locks**: I run 3 Claude Code windows at once, one per project, sometimes on the same physical device pool. Filesystem-coordinated locks mean window 2 doesn't grab the S25 while window 1 is mid-tap. Stale-lock cleanup when a holder process dies.
- **Tiered tool surface**: 110 tools is too many for Claude Desktop's UI ceiling and Cursor's 40-tool cap. `MCP_TOOL_TIER=basic` exposes a curated 26-tool subset. Small local LLMs (Qwen 3B class) work with the basic tier; larger models get the full catalog.
- **Defense-in-depth screenshot pipeline**: Anthropic's API rejects images > 2000px on any edge. I hit this three times in production before getting the cap pipeline right. Now: per-use-case cap at 1600px, dispatcher safety-net at 1900px, BASIC-tier `compress_png` + `inspect_image_safety` so the agent has a recovery path even when an external MCP (computer-use, raw adb screencap) feeds in a 2400px PNG.

**Honest gaps I'm not pretending don't exist**

- iOS device control needs Xcode → macOS-only for iOS work. Linux is fine for Android-only.
- I'm a solo maintainer. PRs welcome, co-maintainers especially.
- No hosted SaaS planned. The MCP protocol is local-first; SaaS would break the security model. Documented in the ROADMAP's "Not on the roadmap" section.
- Patrol-dependent for true UI tests on Flutter. If you're not using Patrol, you get device-level control (taps, screenshots, logs, app lifecycle) but not Flutter-aware test orchestration.

**Try it (genuinely 5 minutes)**

```bash
pip install mcp-phone-controll
claude mcp add phone-controll -- python -m mcp_phone_controll
```

Then in Claude Code:

> *Using phone-controll, run mcp_ping, pick my Android device, take a screenshot.*

You should see three tool calls returning `ok: true` and a PNG in `~/.mcp_phone_controll/sessions/`. If anything's red, the structured `next_action` field tells you what to do — that's the whole MCP contract.

**Links**

- GitHub: https://github.com/michal-giza/flutter-dev-agents
- PyPI: https://pypi.org/project/mcp-phone-controll/
- 15-min onboarding: https://github.com/michal-giza/flutter-dev-agents/blob/main/docs/GETTING-STARTED.md
- The 4 operational gotchas that cost me an hour each the first time: https://github.com/michal-giza/flutter-dev-agents/blob/main/docs/operational-gotchas.md
- Roadmap: https://github.com/michal-giza/flutter-dev-agents/blob/main/ROADMAP.md

**The one question I'd love your input on**

When you're writing a Patrol integration test today and it fails mid-flow, what's the failure mode that wastes the most time? Mine is "the test "passed" because a step silently no-op'd and the next step's assertion happens to match anyway." Curious if I'm alone on that or if it's the whole community's pain.
```

### Tone notes

- "broke me" / "got bitter" / "lost half a Sunday" — vulnerable, real.
- Doesn't oversell. Names competitors honestly. Acknowledges Patrol dependency.
- The closing question is **specific** — about a real Flutter testing pain — not generic "feedback welcome."
- No call-to-action saying "please star," "please share." Reddit hates those.

---

## 2. LinkedIn Variant A — POST 13:30 Spain

### 🏷️ Setup

- **URL**: linkedin.com → "Start a post"
- **Image to attach**: `docs/design/social-preview.png`
- **Hashtags**: 4 max, at the bottom — `#Flutter #MobileQA #MCP #IndieDev`
- **NO emoji in the first line** (LinkedIn truncates emoji-led posts)

### POST

```
I just open-sourced something I've been quietly using for a month.

It's an MCP server that lets Claude (or any agent) build and test my Flutter apps on a real Galaxy S25, my iPhone 15, and a Pixel 8 emulator — all at the same time, from three different Claude Code windows, without colliding.

Why I built it: testing Flutter on real devices is brittle in a way nobody talks about. The Android permission dialog button changes wording across OS versions. iOS 17 changed how developer-tier commands route through tunneld. Polish localization uses NBSP between words — so tap_text("Podczas używania aplikacji") fails silently because the bytes don't match what the agent typed.

These aren't bugs in your app. They're bugs in the test layer. And selector maintenance was eating somewhere around 40% of my testing time according to Drizz's 2026 survey of mobile QA teams. My own number felt about right.

flutter-dev-agents is the MCP I wished existed:

→ 110 tools across Patrol, WebDriverAgent, uiautomator2
→ Cross-session device locks so multi-project work doesn't break
→ Tiered tool surface (26 / 40 / 110) for hosts with tool-count limits
→ Defense-in-depth screenshot cap that survived 3 production incidents
→ Apache 2.0, 556 tests, MCP 2025-06-18 compliant
→ Documented "this will probably go wrong" runbook with concrete fixes

What I'm proud of, after a month of using it daily:

The "tap-and-verify discipline" — every tap is paired with a follow-up assertion that the screen changed as expected. When it didn't, the structured failure tells you exactly what to do next instead of "tap failed somehow." This caught three regressions in my own apps that I would have shipped.

What I'm still figuring out:

How to make this useful for teams that don't already use Patrol. The MCP works without Patrol for device-level control, but the Flutter-specific value really comes from the Patrol integration. If you're not on Patrol, you might still get value from the iOS + Android device coordination layer — I'd love to hear if that's true.

If you've ever lost an evening debugging a selector that "should just work" — try this:

pip install mcp-phone-controll

Full setup in 15 minutes:
github.com/michal-giza/flutter-dev-agents/blob/main/docs/GETTING-STARTED.md

I'd love to know: what's the single test in YOUR suite that breaks most often for selector reasons? The next batch of tools is going to be shaped by the answers.

#Flutter #MobileQA #MCP #IndieDev
```

### Tone notes

- Opens with "I've been quietly using for a month" — anti-hype, signals "this isn't a launch stunt."
- Acknowledges multiple real devices (S25, iPhone 15, Pixel 8 emulator).
- The "selector maintenance was eating 40% of my time" is a number anchored to a citation.
- "What I'm still figuring out" is rare on LinkedIn and reads as confident-not-cocky.
- One question at the end. Specific. About their tests, not generic feedback.

---

## 3. dev.to article — PUBLISH 14:30 Spain

### 🏷️ Setup

- **URL**: dev.to/new
- **Tags** (max 4, dev.to's most-trafficked relevant ones):
  - `flutter`
  - `testing`
  - `ai`
  - `opensource`
  - (Skip `#mcp` — small tag, low traffic. Skip `#mobile` — less SEO-valuable than `#flutter`.)
- **Cover image**: `docs/design/social-preview.png`
- **Series**: `Building flutter-dev-agents`
- **Canonical URL**: leave EMPTY (dev.to keeps SEO weight)

### TITLE (pick ONE)

Variant A (recommended — search-friendly + emotionally honest):
```
The Flutter test that took me three hours to debug, and the MCP server I built so it never happens again
```

Variant B (more direct, SEO-strong):
```
How I built an MCP server to test Flutter apps on real iPhones and Android devices
```

Variant C (lowest-key, technical-audience):
```
Lessons from a month of agent-driven Flutter testing on real devices
```

### SUBTITLE / OPENING (this becomes the dev.to article preview text)

```
After three hours debugging why my Polish-locale tap_text was failing silently, I rewrote my entire mobile testing setup. It's now an Apache-2.0 MCP server, on PyPI today, and this is the writeup.
```

### Then use the FULL ARTICLE BODY from `docs/launch-content/11-dev-to-article.md`

It's already 1,800 words of solid material — the issue was the title and opener. With the new opener above, the existing body reads as a natural continuation. Paste them together in dev.to's markdown editor.

### Tone notes

- Title leads with the **specific moment** (3 hours debugging) — searchable AND emotional.
- Subtitle does the value prop in one sentence.
- The existing body has 3 design decisions + comparison table + install — that material is fine.

---

## 4. Hacker News Show HN — POST 15:30 Spain ⚠️ 2h engagement window

### 🏷️ Setup

- **URL**: news.ycombinator.com/submit
- **HN doesn't use tags** — only the title prefix `Show HN:`

### TITLE (pick ONE, max 80 chars including "Show HN:")

Variant A (recommended — concrete, lower-key):
```
Show HN: MCP server I built to let Claude test my Flutter app on real phones
```
(72 chars — under the limit ✓)

Variant B (technical curiosity):
```
Show HN: Cross-session device locks for AI-driven mobile test concurrency
```
(73 chars ✓)

Variant C (problem-led):
```
Show HN: Stop losing time to mobile-test selector maintenance (Flutter MCP)
```
(76 chars ✓)

### URL field
```
https://github.com/michal-giza/flutter-dev-agents
```

### Text field: LEAVE EMPTY (HN convention)

### FIRST COMMENT — paste IMMEDIATELY after submission

```
Hi HN — solo maintainer here.

Quick context: I've been building Flutter apps for a few years and the thing that quietly kills my productivity isn't writing tests, it's keeping them green. The Android permission dialog changes wording across OS versions. iOS 17+ changed how `pymobiledevice3` routes developer-tier commands. Polish localization uses U+00A0 between words so a Polish testWidget fails byte-equality and you can't see why.

Drizz's 2026 industry survey put selector maintenance at 30-50% of mobile QA hours. My number felt closer to 40%. Agents can close that loop — but until this MCP, nothing gave them safe structured access to a real phone. The mobile MCPs out there were iOS-simulator-only (mobile-next/mobile-mcp, ambar/simctl-mcp), Android-only (martingeidobler), or Figma-to-code (mhmzdev). None did real iOS + real Android + Flutter-aware as a coherent unit.

So I built flutter-dev-agents. Three things I'm proud of after a month of dogfooding on a Galaxy S25 + iPhone 15:

(1) **The tiered tool surface**. I have 110 tools. Claude Desktop's UI silently drops tool lists above an undocumented ceiling. Cursor caps at 40. Small LLMs (Qwen 2.5 3B) hallucinate past 30. So `MCP_TOOL_TIER=basic` exposes a curated 26-tool subset that fits every host. Tools earn their tier by being recoverable — `compress_png` and `inspect_image_safety` are BASIC even though they're "weird" because they're the recovery path when an external MCP feeds a 2400px PNG into Claude. Recovery tools belong in BASIC.

(2) **Filesystem-coordinated cross-session device locks**. I run 3 Claude Code windows daily. Filesystem locks (not memory) because they survive MCP restarts and don't need a coordination daemon. Stale-lock detection by polling the holder pid. The trade-off is ~5ms acquire vs in-memory mutexes — fine for the actual use case (local-host multi-window).

(3) **iOS 17+ routing via tunneld's HTTP API**. The deprecated `--tunnel UDID` shortcut in pymobiledevice3 silently fails on iOS 17+ for `developer dvt screenshot`. The right path is `--rsd HOST PORT` resolved from tunneld at 127.0.0.1:49151. Cost me a weekend; documented as ADR + tripwire test so it won't bite me again.

The genuine open questions I'd love HN's read on:

- Server-side tool-surface filtering (my approach) vs client-side filtering (small-LLM agent BYOM)? The conventional wisdom says clients should choose, but server-side survives model swaps and respects host capacity. I lean server-side but I'm not certain.
- The `inspect_image_safety` + `compress_png` pattern in BASIC — should this become a cross-MCP convention? Every MCP that produces assets exposes an `inspect_<type>_safety` probe?
- Cleanest path to a BrowserStack-style cloud-farm bridge that doesn't compromise local-first security? Current ROADMAP says "thin client over network MCP" but the auth + latency story is gnarly.

Install: `pip install mcp-phone-controll`
Docs: https://github.com/michal-giza/flutter-dev-agents/blob/main/docs/GETTING-STARTED.md
Roadmap (incl. "Not on the roadmap" — SaaS, Windows-iOS, OAuth in adapter, etc.): https://github.com/michal-giza/flutter-dev-agents/blob/main/ROADMAP.md

Apache 2.0, 556 tests, MCP 2025-06-18.

Happy to dig into anything in the thread.
```

### Tone notes

- Opens with "solo maintainer here" — HN responds well to honest founders.
- Cites the survey, names competitors specifically (HN rewards intellectual honesty).
- The 3 numbered design decisions are technical and specific.
- 3 open questions are real engineering trade-offs, not "what do you think?" softballs.
- "Apache 2.0, 556 tests" at the end as quiet proof, not headline.

---

## 5. Twitter / X thread — POST 17:00 Spain

### 🏷️ Setup

- **URL**: x.com/compose/post
- **Hashtags**: ONE in tweet 1 only — `#BuildInPublic`. Skip Flutter/MCP hashtags; they dilute.
- **Mentions**: optional `@leancodepl` (Patrol team) in tweet 4 or 5 — courtesy

### Tweet 1 (hook)

```
Three hours of my Sunday vanished into debugging why tap_text("Podczas używania aplikacji") was silently failing on a Polish-locale Galaxy S25.

The bytes didn't match. Android encodes NBSP between words.

So I rewrote my entire Flutter testing setup. Open-sourced today 🧵

#BuildInPublic
```

### Tweet 2 — click "Add" before posting

```
flutter-dev-agents is an MCP server that lets Claude — or any LLM with tool-calling — drive my Flutter apps on a real Galaxy S25, my iPhone 15, a Pixel 8 emulator, all at once from different Claude Code windows.

Cross-session device locks. 110 tools. Apache 2.0. PyPI today.
```

### Tweet 3 — attach a screenshot of the README hero (or social-preview.png)

```
The selector maintenance problem isn't unique to me — Drizz's 2026 survey put it at 30-50% of mobile QA engineering hours.

testWidgets that pass green today break tomorrow because the OS shipped a new button label. Agents can close that loop, but they needed an MCP first.
```

### Tweet 4 (technical bit — for the engineers in your follower base)

```
Three design wins after a month of dogfooding:

→ Tiered tool surface (26/40/110) so the catalog fits under Cursor's 40-tool cap and Claude Desktop's UI ceiling
→ Filesystem-coordinated device locks (multi-Claude window safe)
→ Defense-in-depth screenshot cap that survived 3 production incidents

Each one is an ADR in the repo.
```

### Tweet 5 — attach social-preview.png

```
Install:

  pip install mcp-phone-controll
  claude mcp add phone-controll -- python -m mcp_phone_controll

Ask Claude:
  "Run mcp_ping, pick my Android, take a screenshot."

15-min onboarding:
github.com/michal-giza/flutter-dev-agents
```

### Tweet 6 (CTA)

```
Genuinely curious:

If you write Patrol or Appium tests today, what's the single test in your suite that breaks most often for selector reasons?

That's where the next batch of tools is heading. Replies open.
```

Click **"Post all"** to publish atomically.

### Tone notes

- Tweet 1 leads with the specific Sunday moment + the technical detail (NBSP).
- "Three hours vanished" — visceral, not abstract.
- Tweet 2 names 3 specific devices.
- One hashtag total. No emoji spam.
- Tweet 6 question is specific.

---

## 6. Patrol Slack `#general` — POST 18:30 Spain (casual evening tone)

### 🏷️ Setup

- **Channel**: `#general` (NOT `#help` — that channel is for asking, not announcing)
- **Tone**: insider-casual. They built the framework you build on top of.

### MESSAGE

```
👋 Long-time Patrol user here. Open-sourced something today that builds on top of Patrol that I'd love folks' opinion on.

flutter-dev-agents — an MCP server (https://github.com/michal-giza/flutter-dev-agents). Lets Claude / Cursor / local LLMs run Patrol tests on real iPhones + Androids, with cross-session device locks so multiple Claude windows can drive different phones without stepping on each other.

Two questions I'd really value the Patrol community's take on:

1. The MCP wraps the Patrol CLI (`patrol test`) because it's the documented stable surface. Has anyone been talking to Patrol's host server directly instead? I avoided it because I assumed it'd be churn-prone, but if folks have done it, I'd love to learn.

2. For longer Patrol flows (auth → main app → settings → logout), should the agent run the whole flow in one `run_patrol_test` call, or break into start_patrol_session / send_command / read_outcome so the agent can react mid-flow? My current code does the former; the latter feels more agentic but I worry about state-handoff complexity.

I owe Patrol a lot for making this possible — the Dart-side OS-layer stuff is what makes this work at all. Happy to demo via DM if anyone wants to see the iOS 17+ RSD-routing or the multi-device-locks bit in action.

Apache 2.0 if anyone's curious about the license.
```

### Tone notes

- "👋 Long-time Patrol user here" — insider opener.
- "I owe Patrol a lot" — genuine appreciation without sycophancy.
- Two specific technical questions, not "thoughts?"
- Doesn't ask for stars/promotion.

---

## 7. Flutter Discord `#showcase` — POST 18:30 Spain

### 🏷️ Setup

- **Server**: discord.gg/flutter
- **Channel**: `#showcase` (designed for "here's what I built")
- **Discord auto-formats `**bold**` and `code` blocks**

### MESSAGE

```
**flutter-dev-agents** — open-sourced today. An MCP server that lets Claude (or any LLM with tool-calling) test my Flutter apps on a real Galaxy S25, an iPhone 15, a Pixel 8 emulator — three devices in three Claude Code windows simultaneously.

Built it because selector maintenance was eating ~40% of my testing time. Polish-locale `tap_text("Podczas używania aplikacji")` was failing silently because the OS encodes NBSP between words. Three hours of debugging that one led to rewriting my entire setup.

What's in the box:
• 110 tools across Patrol, WebDriverAgent (iOS 17+ RSD routing via tunneld), uiautomator2
• Cross-session filesystem device locks (multi-window safe)
• Tiered tool surface (26 BASIC / 40 INTERMEDIATE / 110 EXPERT) for hosts with tool-count limits
• Apache 2.0, 556 hermetic tests + 5 real-device tests
• Documented runbook for the top 10 things that go wrong

Install:
`pip install mcp-phone-controll`

Then in Claude Code:
*"Using phone-controll, run mcp_ping and take a screenshot of my Android."*

GitHub: https://github.com/michal-giza/flutter-dev-agents
First-15-min guide: https://github.com/michal-giza/flutter-dev-agents/blob/main/docs/GETTING-STARTED.md

PRs welcome if anyone wants to add a framework (Detox / XCUITest recipes are on the roadmap and only 5 files each).
```

### Tone notes

- Discord is casual — Markdown bullets, emojis allowed sparingly, code blocks supported.
- "What's in the box" is fine here (would be cringe on Reddit).
- Mentions "PRs welcome" naturally — Discord users are contributors.

---

## 🎯 Universal tone rules I'm applying

These are the patterns I'm using everywhere. Useful if you write a new post later:

| Pattern | Why it works |
|---|---|
| Lead with a specific moment ("Sunday afternoon," "lost three hours," "I got bitter") | Real. Searchable. Memorable. |
| Name actual devices (Galaxy S25, iPhone 15, Pixel 8 emulator) | Concrete > abstract. Reads as someone who actually uses it. |
| Acknowledge competitors by name | Reddit/HN/Discord all reward this. Looks honest. |
| Acknowledge weaknesses ("no SaaS planned," "macOS-only for iOS," "single maintainer") | Builds trust. People believe the wins more after honest losses. |
| ONE specific question at the end | Generic "feedback welcome" gets ignored. "What's the test in YOUR suite that breaks most often?" gets real replies. |
| No emoji spam, no hype words | "Revolutionary," "game-changing," "10x," "industry-shattering" — every one of these costs credibility. Cut them. |
| Numbers, not adjectives | "556 tests" > "comprehensive testing." "30-50% per Drizz 2026" > "lots of time." |

---

## 🚨 Common rookie mistakes I'd avoid

If you're new to publishing, the easiest ways to underperform are:

1. **Self-comments** ("Looks like this is taking off!" / "Glad people like it!"). Don't. Reads as desperate. Just respond to *real* comments quickly.
2. **Asking for upvotes / shares / stars.** Every platform punishes this. Reddit hides it, HN flags it, LinkedIn buries it.
3. **Cross-posting identical text to multiple subreddits / Discord channels in one go.** Mods see "low-effort poster" and remove. Space submissions ~hours apart.
4. **Engaging hostilely** with skeptical commenters. Even when wrong, the audience reads YOUR tone more than the critic's. "Fair point — here's the constraint I was working with" beats "you don't understand."
5. **Bragging metrics in real-time.** ("Already on the front page!"). Tacky. Let the numbers speak after — like in your week-1 case study.
6. **Disappearing after posting.** First 60 minutes are the algorithmic window. Set a timer. Reply to every comment.

You'll get this right. The fact that you asked for "more humanized" instead of "more aggressive marketing" tells me you already have the right instinct.

**Go.** 🚀
