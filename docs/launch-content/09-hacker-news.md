# 9 · Hacker News — Show HN

**URL:** https://news.ycombinator.com/submit
**Effort:** 5 minutes to submit + 1-2 hours actively engaging
**Why:** HN's audience skews exactly into "developer with strong opinions about MCPs and dev tooling." A front-page Show HN is genuinely transformative for an indie tool — but only if you're available to answer comments.

## When to submit

**Tuesday or Wednesday, 14:30 CET (08:30 ET).** This catches:
- US East Coast morning coffee scroll (08:30 ET).
- US West Coast pre-work catch-up (05:30 PT).
- EU afternoon work break (14:30 CET).

Avoid Friday afternoon (lowest engagement) and Monday morning (HN traditionally slow).

## The submission

### Title (HN allows max 80 chars; punchy beats descriptive)

Pick ONE — A is the recommended starting point.

**Title A (recommended — most discoverable):**
```
Show HN: MCP server for autonomous Flutter testing on real phones
```

**Title B (alternative — engineering-heavy crowd):**
```
Show HN: Production MCP server with 110 tools for mobile device testing
```

**Title C (alternative — agent-builder framing):**
```
Show HN: Let Claude drive your Flutter app's tests on a real iPhone
```

### URL field

```
https://github.com/michal-giza/flutter-dev-agents
```

### Text field — leave EMPTY

HN convention: Show HN submissions use the URL, not the text field. The first comment from you (see below) is where you describe the project.

## The first comment (paste immediately after submitting)

HN expects the submitter's first comment to be a deeper "why this exists" — not a marketing pitch. Paste this verbatim within 60 seconds of the submission landing:

```
Hi HN — solo maintainer here. Background: I've been testing Flutter
apps daily for years and 30-50% of my engineering time was selector
maintenance (Drizz industry survey 2026 backs this up — it's not
just me). The "ai will fix testing" wave kept producing tools that
were iOS-simulator-only, web-only, or wrapped a cloud farm with
$$/test-minute.

flutter-dev-agents is the MCP I wished existed: real iPhones + real
Androids, 110 tools spanning Patrol/WDA/uiautomator2, cross-session
device locks so 4 concurrent Claude windows can drive 4 phones
without colliding. Apache 2.0, 556 hermetic tests, MCP 2025-06-18
compliant.

Three concrete things I'm proud of after a month of dogfooding:

1. The "tiered tool surface" (BASIC=26 / INTERMEDIATE / EXPERT=110)
   solves the Claude Desktop "no tools visible" problem caused by
   the host's undocumented tool-count ceiling. Configurable via
   MCP_TOOL_TIER=basic.

2. Defense-in-depth on the screenshot pipeline (per-use-case cap +
   dispatcher safety net + post-cap verification) survived three
   production "2000 px API limit" incidents. The `inspect_image_safety`
   + `compress_png` BASIC-tier escape hatches handle the case where
   an agent fetches a 2400px screenshot from another MCP.

3. iOS 17+ developer-tier routing via tunneld's HTTP API instead of
   the deprecated `--tunnel UDID` shortcut. Cost me a weekend to
   figure out; documented as ADR + a tripwire test.

Things I'd love HN feedback on:

- Is the "tiered surface" the right model, or should small-LLM
  agents bring their own filter?
- Should the inspect_image_safety / compress_png pattern become a
  cross-MCP convention?
- What's the cleanest way to bridge to BrowserStack-style cloud
  farms without compromising the local-first security model?

Install:    pip install mcp-phone-controll
Docs:       https://github.com/michal-giza/flutter-dev-agents/blob/main/docs/GETTING-STARTED.md
Roadmap:    https://github.com/michal-giza/flutter-dev-agents/blob/main/ROADMAP.md
```

## Engagement strategy (first 2 hours)

**Reply to every comment within 5-10 minutes.** HN's algorithm
weights early engagement heavily — your reply rate in the first
hour decides whether you stay on the new page or move to front-page
contention.

**For each comment type, the playbook:**

| Comment type | Response pattern |
|---|---|
| Technical question | Answer concretely. Link to the exact file / line / ADR. |
| Comparison to X tool | Stay genuine — "X is great for Y, this MCP is for Z." Never trash competitors. |
| "Why not just use Maestro?" | The FAQ entry. Maestro is YAML-driven, you write tests; this is agent-driven, agent writes tests. Different use cases. |
| Concern about cost / lock-in | Emphasize Apache 2.0, local-first, no SaaS. Point at ROADMAP "Not on the roadmap" → SaaS. |
| Skeptical: "AI testing is overhyped" | Agree partially. Share the 30-50% selector-maintenance number, link to your eventual case study. Don't oversell. |
| "How do you handle [edge case]?" | If it's documented, link to operational-gotchas.md. If not, say "good question — filing an issue, will track." |
| Hostile / drive-by negativity | Don't engage. HN moderators handle this; your job is to model good behavior. |
| "How can I contribute?" | Point at ROADMAP "Now" + the "help wanted" labels (you can add these AFTER submission). |

## Things HN will likely ask you about

Have responses ready (don't pre-paste — type them live, but rehearse):

- **"Why a new MCP — couldn't this be a Patrol/Appium plugin?"** Patrol/Appium speak the webdriver protocol; MCP is the bidirectional, agent-shaped protocol. Different layer. You wrap them; they don't wrap you.
- **"Doesn't Claude already have computer-use for this?"** computer-use drives desktops. This drives phones. They compose well — the inspect_image_safety + compress_png tools specifically handle the multi-MCP screenshot case.
- **"How much does it cost to run?"** Apache 2.0, free. The MCP is local; the LLM is yours to choose (Claude or local). Cost = $0 for the MCP itself.
- **"Production-ready?"** Define production. For "an indie dev uses it daily on a real Galaxy S25" — yes, that's me, daily. For "a 50-engineer mobile team in production CI" — not yet, that's why the roadmap calls out the Linux-container-on-CI work as "Next."
- **"Why Python and not Dart?"** The MCP protocol's reference SDK is Python; Patrol is Dart. The MCP wraps Patrol; you don't write the MCP in Dart any more than you write a webserver in HTML.

## What success looks like

- **Top 30 of /newest within 30 minutes** → you're on the radar.
- **Top 10 of /newest within 1 hour** → you're heading for front-page contention.
- **Front page** → 2,000-10,000 unique visitors, 100-500 stars overnight, several real users emerging within a week.
- **Top 5 with > 200 comments** → genuine community moment, expect inbound contributors + DMs about consulting / employment.

Most Show HN posts don't make it past /newest. That's fine — the
**comments stay searchable forever** and become long-tail SEO.

## If it doesn't get traction

Don't resubmit the same project to HN within 90 days. Don't ask
people to upvote (HN flags this; the post gets killed). Just let
it ride and move to the next channel — the Reddit / dev.to / LinkedIn
distribution doesn't depend on HN traction.
