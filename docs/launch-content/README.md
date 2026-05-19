# Launch content — ready-to-paste

Every file in this folder is the **exact text + step-by-step
instructions** for one launch destination. Copy → paste → submit.

> **For the day-of execution order + timing**, read
> [`LAUNCH-DAY-RUNBOOK.md`](LAUNCH-DAY-RUNBOOK.md) first.

## All 13 destinations

| # | File | Destination | Audience | Effort |
|---|---|---|---|---|
| 00 | **[`LAUNCH-DAY-RUNBOOK.md`](LAUNCH-DAY-RUNBOOK.md)** | Master runbook | — | read first |
| 01 | [`01-modelcontextprotocol-servers.md`](01-modelcontextprotocol-servers.md) | github.com/modelcontextprotocol/servers | Anthropic-curated list | 20 min (PR) |
| 02 | [`02-pulsemcp.md`](02-pulsemcp.md) | pulsemcp.com | Feeds Claude Desktop connectors | 5 min |
| 03 | [`03-mcp-so.md`](03-mcp-so.md) | mcp.so | Community marketplace | 5 min |
| 04 | [`04-smithery.md`](04-smithery.md) | smithery.ai | Agent-builder discovery | 5 min |
| 05 | [`05-glama.md`](05-glama.md) | glama.ai/mcp | Search-driven directory | 5 min |
| 06 | [`06-awesome-mcp-prs.md`](06-awesome-mcp-prs.md) | 3 awesome-mcp lists on GitHub | Long-tail SEO | 10 min total |
| 07 | [`07-linkedin-post.md`](07-linkedin-post.md) | LinkedIn (3 variants A/B/C) | Mobile QA / MCP builders / enterprise | 5 min/post |
| 08 | [`08-github-repo-metadata.md`](08-github-repo-metadata.md) | Your repo's About panel | Every visitor's first impression | done ✅ |
| 09 | [`09-hacker-news.md`](09-hacker-news.md) | Hacker News Show HN | AI engineers + tool builders | 5 min + 2h engagement |
| 10 | [`10-reddit-flutterdev.md`](10-reddit-flutterdev.md) | r/FlutterDev | Flutter community (200K) | 10 min + 2h engagement |
| 11 | [`11-dev-to-article.md`](11-dev-to-article.md) | dev.to | Long-form, SEO compounds | 20 min |
| 12 | [`12-twitter-launch.md`](12-twitter-launch.md) | Twitter / X | AI / DevTool Twitter | 5 min + 1h engagement |
| 13 | [`13-community-channels.md`](13-community-channels.md) | Patrol Slack + Flutter Discord + Anthropic Discord | Highest-quality users | 15 min |

## Suggested day-1 sequence (from `LAUNCH-DAY-RUNBOOK.md`)

**Wave 1 — directory submissions (no engagement needed)** — 30 min total starting 08:00 CET:
1. PulseMCP → mcp.so → Glama → Smithery → 3× awesome-mcp lists → modelcontextprotocol/servers

**Wave 2 — social with comment windows** — staggered over the day:
- 09:00 — LinkedIn Variant A
- 10:30 — Hacker News
- 12:30 — r/FlutterDev
- 14:00 — dev.to
- 15:30 — Twitter thread
- 17:00 — Patrol Slack + Flutter Discord

**Wave 3 — week 2 follow-ups:** LinkedIn Variant B (MCP builders), Variant C (enterprise), Flutter Weekly newsletter, mcp.so / glama / smithery profile polish.

## Single source of truth

Anywhere you see one of these placeholders, swap in:

- **`{REPO_URL}`** → `https://github.com/michal-giza/flutter-dev-agents`
- **`{PYPI_URL}`** → `https://pypi.org/project/mcp-phone-controll/`
- **`{RELEASE_URL}`** → `https://github.com/michal-giza/flutter-dev-agents/releases/tag/v0.2.2`
- **`{VERSION}`** → `0.2.2`
- **`{TAGLINE_SHORT}`** → *"The first MCP server for autonomous Flutter testing on real iPhones and Androids."*
- **`{TAGLINE_LONG}`** → *"Build, deploy and test Flutter apps on real iPhones and Android devices from Claude Desktop / Claude Code / any MCP-aware host. 110 tools, 556 tests, Apache 2.0."*

## ASO discipline (applied throughout)

Every text follows three rules:

1. **First 80 characters carry the value prop.** Some directories truncate after that.
2. **Three keyword clusters appear in every description**: `MCP / Model Context Protocol`, `Flutter / mobile`, `Claude / agent / autonomous testing`.
3. **One concrete number per description** (110 tools, 556 tests, etc.). Numbers convert; adjectives don't.

## Verify before going live

Run this checklist from `LAUNCH-DAY-RUNBOOK.md`:

```bash
# All three should succeed:
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

## Pre-flight (tonight, < 10 minutes)

1. **Upload `docs/design/social-preview.png`** via GitHub Settings → Social preview. Without this, every paste-link unfurls as your avatar — the single biggest CTR lift.
2. **Fill in today's case-study journal entry** (`./scripts/case_study_today.sh`). 5 minutes; locks in the same-day concreteness that makes week-1 case study credible.
3. **DM 3-5 supporters** asking them to comment (not just like) in the first hour of LinkedIn Variant A. Template in `LAUNCH-DAY-RUNBOOK.md`.
