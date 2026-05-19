# 6 · awesome-mcp lists — three quick PRs

**Effort:** 30 minutes total (10 min each)
**Why:** awesome-* lists rank highly in GitHub search and dominate
the "what MCP server should I use for X?" query. One bullet each
buys you long-tail discovery for years.

## The three lists to target

| Repo | URL | Section to add to |
|---|---|---|
| `punkpeye/awesome-mcp-servers` | https://github.com/punkpeye/awesome-mcp-servers | "Testing" or "Mobile" (closest match — pick whichever exists) |
| `appcypher/awesome-mcp-servers` | https://github.com/appcypher/awesome-mcp-servers | "Developer Tools" or "Testing" |
| `wong2/awesome-mcp-servers` | https://github.com/wong2/awesome-mcp-servers | "DevTools" |

Check each repo's current section structure before submitting —
they shift around. The principle: find the section closest to
"mobile testing" or "developer tools".

## The bullet (use exactly the same in all three)

```markdown
- [flutter-dev-agents](https://github.com/michal-giza/flutter-dev-agents) - 🔌 MCP server for autonomous Flutter testing on real iPhones and Android devices. 110 tools across Patrol, WebDriverAgent, and uiautomator2. Cross-session device locking, tiered tool surface for small LLMs. Apache 2.0.
```

If the list uses emoji prefixes (some do — 🔌 for Python servers,
📱 for mobile, etc.), match their convention by skimming nearby
entries.

## Submission workflow (per repo)

For each list:

1. Fork the repo.
2. Edit `README.md` in the GitHub UI.
3. Find the right section (alphabetical or chronological — match
   whatever the list uses).
4. Insert the bullet.
5. PR title:
   ```
   Add flutter-dev-agents (Flutter / mobile-device MCP server)
   ```
6. PR description (paste verbatim):

```markdown
Hi! Adding `flutter-dev-agents` — an MCP server that lets autonomous agents drive real iPhones and Android devices for Flutter app testing.

## Why it fits this list

- First MCP for real-device Flutter testing (everything else in this space is iOS-simulator-only or web-only).
- 110 tools, MCP 2025-06-18 compliant.
- Apache 2.0.
- Production-grade: CycloneDX SBOM, CVE gating, structured logs, Prometheus metrics, Docker image, GitHub Action wrapper.
- 556 hermetic tests + 5 real-device tests.
- Documented top-10 failure modes with concrete fixes.

Happy to adjust the description or move the entry if you'd prefer a different section.
```

## Bonus lists (lower priority, do if time)

- `mcpservers.org` — community-maintained, sometimes accepts PRs
  via their site.
- `awesome-claude` lists (several exist on GitHub) — broader scope
  than just MCP servers but worth a one-bullet add if the
  curator's responsive.
- `awesome-flutter` lists — these are Dart-focused so your Python
  MCP doesn't fit the "tools written in Flutter" criterion, but
  some sub-sections accept "tools that help Flutter devs" — worth
  scanning. Recommended: `Solido/awesome-flutter`.

## After the PRs merge

Star each parent repo (signals to other curators you're part of
the community). Reply in the PR thread when someone comments —
maintainers notice responsive contributors and prioritize their
future PRs.

## If a maintainer declines

Take the feedback graciously. Common reasons:

- **"Too niche."** Counter: link your stargazer count + PyPI
  download stats once you have them. Re-submit in 3 months.
- **"Description too long."** Re-submit with a trimmed version:
  ```
  - [flutter-dev-agents](https://github.com/michal-giza/flutter-dev-agents) - Test Flutter apps on real iPhones + Android from any MCP-aware host.
  ```
- **"Add a screenshot."** Add a small (1-frame) PNG of the README's quick-start under `docs/` and reference it inline.
