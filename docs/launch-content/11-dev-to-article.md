# 11 · dev.to launch article

**URL:** https://dev.to/new
**Effort:** 20 minutes to publish (article is pre-written below) + occasional follow-up over a week
**Why:** dev.to articles get long-tail SEO. A LinkedIn post is dead in 72 hours; a dev.to post keeps pulling traffic for months because Google indexes it heavily and "mcp server flutter testing" has near-zero competition.

## When to publish

**Tuesday-Thursday, 14:00 CET.** dev.to traffic peaks during US business hours; this catches both ends.

## The article setup

### Title
```
I built an MCP server that lets Claude test my Flutter app on a real phone
```

### Cover image
Upload `docs/design/social-preview.png` as the cover. dev.to crops to ~16:9; the 1280x640 PNG fits cleanly.

### Tags (max 4 on dev.to — pick the highest-traffic combo)
```
flutter
mobile
ai
opensource
```

Skip `#mcp` — dev.to's tag is tiny (< 100 posts). The four above pull more readers.

### Series (optional but recommended)
Set series name to: **"Building flutter-dev-agents"**

This pre-claims the SEO real estate for follow-up articles (case-study, week-1 retrospective, etc.) so they all link together.

### Canonical URL
Leave EMPTY. Even if you cross-post to your own blog later, do this first on dev.to so dev.to gets the SEO weight initially.

---

## The article body — paste verbatim into the markdown editor

```markdown
After a month of dogfooding, I open-sourced `flutter-dev-agents`
today: an MCP server that lets autonomous agents build, deploy, and
test Flutter apps on real iPhones and Android devices. Apache 2.0,
on PyPI as `mcp-phone-controll`.

This post is the **"why this exists and how I built it"** writeup
— I'll cover the production case study (real-device dogfooding
data) in a follow-up at the end of week 1.

## The problem in one number

Drizz's 2026 industry survey: mobile QA spends 30-50% of
engineering hours on selector maintenance. My own number was
closer to 40% — `testWidgets` that pass green today break tomorrow
because some Android permission dialog moved from "Allow" to
"While using the app."

The fix isn't more tests. The fix is something that **observes** the
test breakage as it happens, **diagnoses** which selector silently
drifted, and **proposes** the patch — without you opening Android
Studio to debug a single label change.

Agents can do that. But until now, no production-grade MCP gave
them safe, structured access to a real phone. Everything mobile-
focused I could find was iOS-simulator-only (`mobile-mcp` via idb),
web-only (the Playwright MCPs), or wrapped a cloud farm with
$$/test-minute.

## What MCP is, in 30 seconds

MCP (Model Context Protocol) is Anthropic's open standard for
giving an AI agent tools and data. Claude Desktop, Claude Code,
Cursor — they all speak it. An MCP server exposes a set of named
tools with typed schemas; the agent dispatches them like function
calls.

Mine exposes 110 tools spanning Android (uiautomator2 + adb), iOS
(WebDriverAgent + pymobiledevice3), and Flutter (Patrol + `flutter
run --machine` for hot reload + debug-log streaming).

## Three design decisions worth talking about

### 1. Tiered tool surface

If you register 110 tools with Claude Desktop, the Connectors panel
silently shows "no tools available" — Anthropic has an undocumented
tool-count ceiling. Cursor is documented at 40. Small LLMs (Qwen
2.5 3B et al) start hallucinating tool names past ~30.

So the MCP exposes the catalog in three tiers:

- **BASIC (26 tools)** — the canonical happy path + recovery tools.
- **INTERMEDIATE (~40)** — adds build, install, debug sessions, IDE.
- **EXPERT (110)** — everything.

You set `MCP_TOOL_TIER=basic` in the env block and you're under
every host's ceiling without any code change.

The interesting twist: `compress_png` and `inspect_image_safety`
are in BASIC. They're "recovery tools" — when an agent grabs a
2400px screenshot via raw `adb screencap` (bypassing the MCP's cap
pipeline), it needs to be able to fix the situation without
escalating to EXPERT tier. The BASIC tier is the "I have to get out
of this hole" surface.

### 2. Cross-session filesystem locks

My factory laptop runs 3-4 Claude windows simultaneously, each in a
different Flutter project, each potentially driving a different
phone. Without locks, two agents grab the same device, one wins
adb's race, the other quietly fails.

The lock layer is **filesystem-coordinated** (not memory):
`~/.mcp_phone_controll/locks/<serial>.lock` with the holder's
session-id + pid. Stale locks auto-clean when `list_locks` notices
the holder pid is gone. `force_release_lock` for the truly stuck
cases.

Why filesystem, not a daemon? Two reasons:

1. **Survives MCP-server restarts.** If Claude Desktop crashes
   mid-test, the lock file still exists; next session's `list_locks`
   sees the dead pid and cleans up.

2. **No coordination service.** No port to allocate, no daemon to
   keep alive, no "which MCP wins?" between concurrent
   `pip install` versions.

The trade-off: filesystem locks are slower than in-memory mutexes
(~5ms acquire), and they require all processes to share the same
filesystem (so they don't survive remoting). For local-host
multi-window coordination — the actual use case — this is the
right call.

### 3. Defense in depth on the screenshot pipeline

The Anthropic API rejects images > 2000 px on any edge. After
3 production incidents, the cap pipeline has 4 layers:

1. **Per-use-case cap** in `take_screenshot` (1600 px default, env-
   configurable via `MCP_MAX_IMAGE_DIM`).
2. **Dispatcher safety net** scans every tool response envelope for
   PNG paths and re-caps any over the hard 1900 px ceiling
   regardless of the env setting.
3. **Post-cap verification** — after capping, the file is re-probed.
   If it's still over, the response is rewritten to remove the
   offending path and surface a structured error.
4. **`inspect_image_safety`** — a BASIC-tier pre-Read probe the
   agent can call against ANY PNG (including ones produced by
   `computer-use`, raw adb, or other MCPs) before trying to read it.

The last one — a checker tool the agent uses on images that didn't
come from this MCP — is unusual. It exists because the actual
production failures were all "an external MCP fed Claude a 2400px
screenshot" or "an overnight bot used raw `adb exec-out screencap`
and the 6th screenshot blew the limit." The cap pipeline can't help
if the image never passed through the MCP. So the agent has to
**ask** before reading. The BASIC-tier placement makes this
discipline frictionless.

## How does it compare to existing tools?

| Tool | This vs. |
|---|---|
| **Maestro** | Maestro is YAML-driven; you write tests. This is agent-driven; agent writes tests. Complement, not replacement. |
| **Appium** | Appium is the webdriver protocol several runners speak. WebDriverAgent (this MCP's iOS driver) was originally an Appium component. This wraps the same drivers but exposes them as MCP tools. |
| **Patrol alone** | Patrol is a Dart test framework. This MCP runs Patrol tests AND adds device locking, multi-project orchestration, agent-readable structured failures, screenshot/log capture. |
| **computer-use** | Drives desktops. This drives phones. They compose well — `inspect_image_safety` + `compress_png` specifically handle screenshots produced by other MCPs. |
| **BrowserStack / Sauce** | Cloud farm, $/minute, 50 OS combos. This is local, free, your laptop. Use a farm when you need the matrix; use this for the day-to-day. |

## What I'd love feedback on

1. **Is the tiered surface the right abstraction?** Or should small-
   LLM agents bring their own client-side filter? I lean toward
   server-side because it survives a model swap; clients lean
   toward "give me everything and I'll deal."

2. **The cross-MCP screenshot-safety pattern** (`inspect_image_safety`
   + `compress_png` in BASIC). I think this should become a
   convention across MCPs that traffic in images — every MCP exposes
   `inspect_<type>_safety` for the asset types it produces. Anyone
   else thinking along these lines?

3. **What's the cleanest way to bridge to BrowserStack-style cloud
   farms** without compromising the local-first security model?
   The current ROADMAP "Later" entry says "thin client over a
   network MCP" but the auth + latency story is gnarly.

## Try it in 5 minutes

```bash
pip install mcp-phone-controll
claude mcp add phone-controll -- python -m mcp_phone_controll
```

Then in Claude Code:

> *Using phone-controll, run mcp_ping, pick the first connected
> Android device, take a screenshot labeled "demo".*

You should see 3 tool calls returning `{ok: true, ...}` and a PNG
path under `~/.mcp_phone_controll/sessions/`.

**Full 15-minute walkthrough**:
https://github.com/michal-giza/flutter-dev-agents/blob/main/docs/GETTING-STARTED.md

**Three worked scenarios** (5-min smoke / Polish-locale repro /
multi-project debug loop):
https://github.com/michal-giza/flutter-dev-agents/tree/main/examples/scenarios

## Links

- 📦 PyPI: https://pypi.org/project/mcp-phone-controll/
- 🐙 GitHub: https://github.com/michal-giza/flutter-dev-agents
- 🗺 Roadmap: https://github.com/michal-giza/flutter-dev-agents/blob/main/ROADMAP.md
- ❓ FAQ:
  https://github.com/michal-giza/flutter-dev-agents/blob/main/docs/FAQ.md

The week-1 production case study (real numbers from real daily use)
will go up here as the next post in this series. Subscribe to the
series if you want the followup.
```

## After publishing

1. **First hour**: reply to every comment within 15 minutes. dev.to's
   "Trending" page weights early engagement, like every other
   platform.

2. **Cross-post link** to your LinkedIn post as the first comment:
   "Wrote up the 'why' behind this in a longer post —
   [dev.to link]." LinkedIn rewards posts that cite external sources;
   this also drives traffic across platforms.

3. **Add to "Series"** when you write the week-1 follow-up — they
   auto-link.

4. **Pin the article** on your dev.to profile (Settings → Profile)
   so anyone visiting your dev.to sees this first.

## What success looks like

dev.to is the slowest-burning platform of the launch but the most
durable.

- **Day 1**: 50-300 views, 5-20 reactions.
- **Week 1**: 500-2,000 views via search + the series compounding.
- **Month 1**: 2,000-10,000 views; the article still gets ~50
  views/week from Google searches for "MCP flutter testing" etc.
- **The case-study follow-up post** typically outperforms the launch
  post by 2-3x because it's grounded in concrete numbers.

## If dev.to flags the post as low-quality

Their auto-moderation occasionally flags first-time poster + lots of
links. Mitigations:

- Make sure your dev.to profile has a real photo + bio before
  publishing.
- Engage with 3-4 other articles in the same tags BEFORE publishing
  yours (comment thoughtfully, not just like).
- If flagged, dev.to's mod team is responsive — DM them via the
  contact form with the article URL + a 1-sentence explanation.
