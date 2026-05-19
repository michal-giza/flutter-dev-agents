# Launch checklist — before publishing to LinkedIn

Honest pre-flight checks. Two tiers: **blockers** (post will underperform
without them) and **nice-to-have** (post still works either way).

Total work to clear blockers: ~2-3 hours.

## Tier 0 — blockers (do before posting)

### 1. Repo metadata on GitHub (5 minutes)

On https://github.com/michal-giza/flutter-dev-agents → ⚙ Settings:

- [ ] **Description field** (one-liner under the repo name):
      *"MCP server that lets autonomous agents build, deploy, and
      test Flutter apps on real iPhones + Androids."*
- [ ] **Website URL** field — point at the landing once it exists,
      or the README anchor `#getting-started-developer-machine-macos`
      for now.
- [ ] **Topics** (tags) — add 8-10:
      `mcp` · `model-context-protocol` · `flutter` · `android` ·
      `ios` · `claude` · `anthropic` · `patrol` · `mobile-testing` ·
      `agent`
- [ ] **Pin the most important file** to the top of the README
      (currently first link is `packages/phone-controll/` — that's
      right).

### 2. GitHub social preview image (30-60 minutes)

The 1280×640 PNG that LinkedIn unfurls when you paste the repo URL.

- [ ] Generate it via `docs/design/brief-02-social-preview.md` —
      paste the prompt block into Claude.ai, save the result.
- [ ] Upload via Settings → Social preview.
- [ ] Verify on https://www.opengraph.xyz/url/... against your repo
      URL — it should render with logo + tagline + stats.

**Without this, LinkedIn shows the default GitHub avatar (your
profile picture). Single biggest lift for click-through rate.**

### 3. README top-of-fold review (15 minutes)

When LinkedIn visitors land on the README, the first 600 vertical
pixels determine bounce. Right now:

- [ ] Update the headline to be one sentence that converts. Current:
      *"Umbrella repository for **MCP servers and agent tooling** that
      drive the full Flutter dev-and-test workflow…"* — too long.
      Try: *"**MCP server for autonomous Flutter testing on real
      iPhones and Androids. 109 tools, Apache 2.0, production-ready
      v0.2.0.**"*
- [ ] Add the social preview image at the top of the README so
      mobile-browser visitors see it before scrolling.
- [ ] Add 4 badges right under the headline — they're a known
      conversion signal:
      ```
      ![tests](https://img.shields.io/badge/tests-507_passing-A6E22E)
      ![license](https://img.shields.io/badge/license-Apache_2.0-F76C28)
      ![mcp](https://img.shields.io/badge/MCP-2025--06--18-F76C28)
      ![python](https://img.shields.io/badge/python-3.11+-3B4252)
      ```
- [ ] Add a "Try it in 5 minutes" anchor link near the top that
      jumps to the install snippet.
- [ ] Move the cross-link to `INTEGRATIONS.md` into the
      top-of-fold — currently buried.

### 4. Verify the install instructions work on a fresh machine (30 minutes)

The fastest way to underperform: someone copies your install snippet
and it fails on line 3.

- [ ] Spin up a clean macOS user (or a fresh Docker container) and
      run `./scripts/install.sh` step by step. Note any deviation.
- [ ] Confirm `phone-controll status` works at the end and reports
      the new version (0.2.0) + git_sha.
- [ ] If you hit anything, fix it BEFORE posting.

### 5. The post text itself (30 minutes)

Draft below in §"LinkedIn post draft". Tune the audience-targeting
words (Flutter dev / mobile-QA / agent builder) to match the
specific group you're posting in.

---

## Tier 1 — high-value (do same day if possible)

### 6. A demo GIF or 60-second clip

LinkedIn posts with embedded video get 3-5× engagement. Even an
animated GIF helps.

- [ ] Record yourself running through brief-05's "Act 1 + Act 2"
      (~30 seconds): paste a prompt, watch the agent drive the S25.
- [ ] Compress to under 8 MB so LinkedIn auto-plays it inline.
- [ ] Caption-hardcode every key tool name so it reads on mute.

### 7. Logo / icon-mark (1-2 hours)

Even a temporary one is fine — paste brief-01's prompt into Claude.ai,
pick one of the two concepts, save as `docs/design/assets/logo/mark.svg`,
reference it from the README.

### 8. A pinned issue or Discussion (10 minutes)

People who land on the repo from your post will look for "how do I
get involved?" Create one of:

- A pinned Issue titled "Feedback wanted — first-100-users program"
  with a checklist of what you'd like feedback on.
- A pinned Discussion titled "Roadmap + open questions" with the
  Tier-2 items from the code reviews.

Without it, interested visitors have no entry point and bounce.

### 9. Cross-link from key docs (10 minutes)

- [ ] README → INTEGRATIONS.md (top-of-fold, not buried)
- [ ] README → docs/design/ (design briefs available for designer-
      audience)
- [ ] README → SECURITY.md (signals to enterprise readers)

---

## Tier 2 — nice-to-have (skip if pressed for time)

- **VS Code extension** stub or screenshot — not needed for v0.2.0
- **Hosted documentation site** — README is fine for now
- **A Discord/Slack community** — start one after you see if there's
  traction; doing it before posting is premature
- **A blog post** — the runbook + the article in `docs/article/`
  cover this; a separate blog post can wait

---

## LinkedIn post draft

Copy-paste-ready. Tune for the specific group / audience you're
posting to. Three variants below — pick the one that matches the
group.

### Variant A — Flutter dev group (P1 audience)

> Shipped this weekend: **flutter-dev-agents** — an MCP server that
> lets Claude (or any agent) drive your Flutter app on a real phone.
>
> 109 tools. Patrol-aware. Handles selector hygiene (`list_missing_widget_keys`),
> token-budget-aware screenshots (palette-mode PNG compression, hard
> 1900-px cap), and the hidden weirdness of Samsung One UI tap
> reliability (fallback to `adb shell input tap` when accessibility
> events drop).
>
> I built it because 30-50% of my Flutter testing was selector
> maintenance (per Drizz, May 2026), and agents should be able to
> close that loop.
>
> Apache 2.0. SBOM in CI. 507 hermetic tests + 5 real-device tests
> gated on `MCP_REAL_DEVICE=1`. Runs on Claude Desktop / Claude
> Code / Cursor / any MCP-aware host.
>
> Try the 5-min install + GitHub Action recipe at
> github.com/michal-giza/flutter-dev-agents
>
> #Flutter #MCP #MobileQA #Claude

### Variant B — Agent-building / MCP community (P3 audience)

> Production MCP server for mobile-app testing, just shipped v0.2.0:
> **flutter-dev-agents**
>
> Reference implementation for the patterns the MCP 2025-06-18 spec
> introduced:
> - Tool annotations (readOnly/destructive/idempotent/openWorld) on
>   all 109 tools via a centralised classifier
> - `outputSchema` infrastructure + 6 BASIC tools migrated as
>   proof-of-pattern
> - Contract snapshot test (`docs/tools-contract.json`) fails CI on
>   silent drift
> - Path-traversal guards (two-tier: strict for content/code,
>   permissive for project paths)
> - Hypothesis-based dispatcher fuzz (opt-in via `MCP_FUZZ=1`)
> - Prometheus `/metrics`, structured JSON logs, SIGTERM-graceful
>
> Bonus: documents WHY each architectural choice (7 ADRs covering
> the image-cap saga, middleware chain, version handshake, path
> guard injection audit).
>
> Apache 2.0, 507 hermetic tests, on PyPI as `mcp-phone-controll`.
>
> github.com/michal-giza/flutter-dev-agents
>
> #MCP #ModelContextProtocol #Claude #AgentDevelopment

### Variant C — Enterprise dev-platform group (P2 audience)

> If your mobile-QA team is on Flutter, this might save them weeks:
>
> **flutter-dev-agents** — an MCP server that lets autonomous
> agents drive your test suite on real iPhones + Android. Shipped
> v0.2.0 today, Apache 2.0.
>
> Production-ready out of the gate:
> - CycloneDX SBOM generated per commit
> - pip-audit gating in CI (caught 2 real CVEs on first scan, fixed
>   same commit)
> - SECURITY.md with 3-day ack / 10-day triage / 5-day critical
>   patch SLAs
> - Production runbook covering the top-10 failure modes with
>   concrete fixes
> - Prometheus /metrics, k8s /health + /ready, Docker image, GitHub
>   Action wrapper
> - 7 ADRs documenting the load-bearing decisions
>
> One-line CI integration:
> ```yaml
> - uses: michal-giza/flutter-dev-agents/.github/actions/run-test-plan
>   with:
>     plan: integration_test/plans/smoke.yaml
> ```
>
> Demos and a 90-second walkthrough at the repo:
> github.com/michal-giza/flutter-dev-agents
>
> Happy to chat through your specific test stack — drop a comment
> or DM.
>
> #FlutterDev #MobileTesting #DevPlatform #CI

---

## What I'd cut from each variant

The biggest mistake on launch posts: trying to say everything. Each
variant above is ~120 words. Anything longer and LinkedIn truncates
it behind "see more" — losing the CTA.

Tune to ONE persona and stay under 1300 characters. Three groups =
three posts, spread across a week, not one mega-post.

## Comments-section preparation (15 minutes)

People will ask these. Have draft answers ready in a notes app:

| Q | A |
|---|---|
| "Isn't this just a wrapper for Patrol?" | "No — Patrol writes tests; this lets agents WRITE and RUN test plans. Patrol is one driver we route to (next to flutter_test, native, Appium-style)." |
| "How is this different from Appium-MCP?" | "Same shape, different focus. Appium-MCP is platform-generic; we're Flutter-aware (selector-hygiene tool, key-detection, dart_analyze gate). And we ship the agent-side discipline (runbook, ADRs, observability) — most MCPs don't." |
| "Production-ready?" | "v0.2.0, Apache 2.0, SBOM in CI, 507 tests, runbook with 10 failure modes. Use it. If you find a bug, SECURITY.md has the disclosure policy." |
| "Why Flutter specifically?" | "Because selector-maintenance is 30-50% of Flutter QA time (Drizz, May 2026). The list_missing_widget_keys tool alone saves teams hours." |
| "Can I use this with Cursor / Claude Code / Claude Desktop?" | "Yes — all three. MCP is the wire protocol. See INTEGRATIONS.md for the recipe per host." |
| "Open to contributors?" | "Yes — CONTRIBUTING.md has the recipe. Start with an Issue describing what you'd add." |

## Final 5-minute check before hitting publish

- [ ] Open your draft post in LinkedIn's preview (the "Preview"
      button before publishing).
- [ ] Does the GitHub link unfurl with the social preview image? If
      not, Tier 0 #2 isn't done.
- [ ] Does the first line hook BEFORE the "see more" cutoff
      (~210 characters)?
- [ ] Is there ONE clear CTA in the post (a URL to click)? Multiple
      CTAs reduce click-through.
- [ ] Are the hashtags on a separate line at the end (not inline)?
      LinkedIn weights hashtag placement.
- [ ] Is the repo set to **public** on GitHub?
- [ ] Is the LICENSE file rendering correctly on the repo's main
      page (GitHub auto-detects it)?

If all checks pass: hit publish.

## After publishing

- Pin the post to your LinkedIn profile for a week.
- Reply to every comment within the first 2 hours (algorithm
  signal).
- DON'T cross-post the same text to three groups in the same hour
  — LinkedIn deboosts duplicate content. Stagger by 24-48 hours.
- Cross-post the same content to:
  - HackerNews (Show HN: …)
  - Reddit r/FlutterDev (different framing — less "I built", more "I needed")
  - Twitter/X thread (split into 5-7 tweets, each one of the value bullets)
  - Anthropic's MCP community Discord
