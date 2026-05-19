# Launch day runbook — v0.2.2

The exact sequence + timing for hitting all 11 platforms in one
day. Designed for **tomorrow morning, Europe/Warsaw time**.

> **Pre-flight (do tonight, < 10 minutes total):**
> - Upload `docs/design/social-preview.png` via GitHub Settings → Social preview. Without this, every paste-link unfurls as your avatar. Single biggest CTR lift.
> - Fill in today's case-study journal entry (`./scripts/case_study_today.sh`).
> - Read this runbook end-to-end so you know what's coming.

---

## The constraint

LinkedIn / Twitter / HN / Reddit reward the first 60 minutes after
posting. If you submit everywhere at once, you can't reply to
comments in any of them — and the algorithms notice unresponsive
posters. So launch in **two waves**:

- **Wave 1 (~30 minutes, before any social):** 6 directory + list
  submissions. These don't need real-time engagement.
- **Wave 2 (timed to your timezone):** the social posts, one per
  hour, so you're at your laptop for the comment window of each.

---

## Wave 1 — 08:00 CET (30 minutes total, no engagement needed)

Order matters: smaller directories first to debug any "is `pip install`
working" issues, then the high-signal Anthropic-official PR last.

| # | Platform | File | Effort |
|---|---|---|---|
| 1 | PulseMCP | `02-pulsemcp.md` | 5 min |
| 2 | mcp.so | `03-mcp-so.md` | 5 min |
| 3 | Glama.ai | `05-glama.md` | 5 min |
| 4 | Smithery (just claim — `smithery.yaml` auto-detects) | `04-smithery.md` | 3 min |
| 5 | 3× awesome-mcp lists (identical bullet, 3 PRs) | `06-awesome-mcp-prs.md` | 10 min |
| 6 | modelcontextprotocol/servers (Anthropic-curated PR) | `01-modelcontextprotocol-servers.md` | 5 min |

### Confirm before starting

```bash
# All three should return "✓":
curl -fsS https://pypi.org/pypi/mcp-phone-controll/json | python3 -c 'import sys,json; print("✓ PyPI:", json.load(sys.stdin)["info"]["version"])'
curl -fsS https://api.github.com/repos/michal-giza/flutter-dev-agents/releases/tags/v0.2.2 | python3 -c 'import sys,json; print("✓ GitHub release:", json.load(sys.stdin)["name"])'
curl -fsSL -o /dev/null -w "%{http_code}" https://github.com/michal-giza/flutter-dev-agents && echo "  ← repo HTTP code"
```

Expected:
```
✓ PyPI: 0.2.2
✓ GitHub release: v0.2.2 — launch readiness (first PyPI release)
200  ← repo HTTP code
```

---

## Wave 2 — staggered, timed to your timezone

Each social post needs you at your laptop for ~1 hour after
posting. Stagger so the windows don't overlap.

| Time (CET) | Platform | File | Audience |
|---|---|---|---|
| **09:00** | LinkedIn Variant A | `07-linkedin-post.md` | Flutter / mobile-QA — your direct network |
| **10:30** | Hacker News "Show HN" | `09-hacker-news.md` | AI engineers + tool builders |
| **12:30** | r/FlutterDev | `10-reddit-flutterdev.md` | Flutter community (200K subscribers) |
| **14:00** | dev.to article | `11-dev-to-article.md` | Long-form, SEO compounds |
| **15:30** | Twitter/X | `12-twitter-launch.md` | AI / DevTool Twitter |
| **17:00** | Patrol Slack + Flutter Discord | `13-community-channels.md` | Direct contributor pipeline |

### The first-60-minute discipline

For every social post:

1. **Reply to every comment within 10 minutes** during the first hour. Set a phone timer.
2. **Don't share the post into private DMs** during the first 30 minutes — LinkedIn/Twitter mark that as inorganic distribution.
3. **Don't comment on your own post.** Self-comments dilute reach.
4. **DM 3-5 known supporters BEFORE posting** asking them to comment (not just like) within the first hour. Genuine comments lift reach 3-5×.

### Pre-write the support DMs (do tonight)

To 3-5 people who know the project:

```
Hey — launching flutter-dev-agents (the MCP for autonomous Flutter
testing) tomorrow morning. Going up on LinkedIn at 09:00 CET.

Would mean a lot if you could drop a real comment (not just a
like) in the first hour — even a one-line "looks useful, what
about X?" helps the algorithm.

Link: https://github.com/michal-giza/flutter-dev-agents
PyPI:  https://pypi.org/project/mcp-phone-controll/

No worries if not.
```

---

## Wave 3 — week 2 (don't try to fit this into day 1)

Save for ~7 days later when day-1 fatigue is wearing off:

- **LinkedIn Variant B** (MCP/agent builders) — different group, same project.
- **LinkedIn Variant C** (enterprise dev-platform) — different angle again.
- **Flutter Weekly newsletter** submission via flutterweekly.net/submit.
- **Mobile Native Foundation Discord** (if you've joined; tight community).
- **Anthropic Discord #mcp** channel.

---

## After all submissions — track the inbound

Watch these for the first 48 hours:

```bash
# Repo traffic (need write access — works for you):
gh api repos/michal-giza/flutter-dev-agents/traffic/views \
  | python3 -m json.tool

# PyPI downloads (24h lag):
curl -fsS https://pypistats.org/api/packages/mcp-phone-controll/recent \
  | python3 -m json.tool

# GitHub stars over time:
gh api graphql -f query='{
  repository(owner: "michal-giza", name: "flutter-dev-agents") {
    stargazerCount
  }
}'
```

Capture the day-1 / day-3 / day-7 numbers in your case-study
journal (`docs/internal/case-study-journal/`) — they're the
concrete numbers the published case study will need.

---

## If something breaks

| Symptom | Most likely cause | Fix |
|---|---|---|
| Someone says `pip install` fails | Their Python is < 3.11 | Tell them to use 3.11+; point at `docs/GETTING-STARTED.md` prerequisites |
| "I added the MCP to Claude Desktop but see no tools" | Tool-count ceiling | Tell them to set `MCP_TOOL_TIER=basic` — fully documented in `docs/runbook.md#0` |
| Someone reports an actual bug | Direct them to file via the issue template | The bug-report template captures everything you need for triage |
| Spam / hostile comment | Use GitHub's hide-comment + Discussion locking | Don't engage; you have CoC + branch protection |
| A directory rejects the submission | Check the file's "If maintainers ask for changes" section | Every launch-content file has a pre-trimmed backup version |

---

## What "winning day 1" looks like

These are **leading indicators**, not goals. Don't optimize for them.

- 50–200 unique visitors to the repo (from GitHub traffic).
- 5–25 new stars.
- 10–50 PyPI downloads.
- 1–3 quality comments on LinkedIn / HN that aren't friends.
- 0 sev-1 bug reports (the project is stable; if you see one, it's a config issue).
- 1+ "this is exactly what I need" reaction from a real user.

Don't worry if the numbers are smaller. **Indie dev-tools live or die
on week 4, not day 1.** The case study at week 1 carries more weight
than the launch post.
