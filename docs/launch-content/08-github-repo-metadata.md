# GitHub repo metadata — do this FIRST

Every other channel links to your repo, so it has to render
correctly before anyone arrives. 10 minutes total.

## Step 1 — repo "About" panel

Open https://github.com/michal-giza/flutter-dev-agents → click the
⚙ gear next to "About" (top-right of the code view).

**Description** (paste verbatim, 350 char limit on GitHub — this fits in 240):

```
The first MCP server for autonomous Flutter testing on real iPhones and Android devices. 110 tools across Android (uiautomator2 + adb), iOS (WebDriverAgent + pymobiledevice3) and Flutter (Patrol + flutter run --machine). Works with Claude Desktop, Claude Code, Cursor.
```

**Website** field:

```
https://pypi.org/project/mcp-phone-controll/
```

(Switch to a docs site URL once you build one. PyPI is the right
placeholder — it shows the package as installable.)

**Topics** (add these one-by-one; GitHub caps at 20):

```
mcp
model-context-protocol
flutter
android
ios
claude
anthropic
patrol
mobile-testing
ui-automation
agent
autonomous-testing
ai-agents
test-automation
appium
uiautomator2
webdriveragent
dart
```

Tick `[x] Releases`, `[x] Packages`, `[x] Used by`. Leave the rest
unchecked — they clutter the panel.

## Step 2 — social preview image (single biggest CTR lift)

GitHub's default preview shows your avatar. LinkedIn / Twitter /
Slack unfurl this when someone pastes your repo URL — replace it
with a real card.

**Spec:**
- 1280 × 640 px (2:1)
- < 1 MB
- PNG, sRGB

**Generate it:**

The prompt block in [`docs/design/brief-02-social-preview.md`](../design/brief-02-social-preview.md)
(if present) has the exact text — or use this minimal version:

```
A clean dark-mode developer-tool social preview card, 1280×640.
LEFT 60%: bold sans-serif headline in 3 lines —
  "flutter-dev-agents"
  "MCP server for autonomous"
  "Flutter testing on real devices"
Beneath the headline, one row of small stat badges:
  "110 tools" · "556 tests" · "Apache 2.0" · "MCP 2025-06-18"
RIGHT 40%: an iPhone and Android phone overlapping at a slight tilt,
with subtle Patrol-blue + Anthropic-orange accent glows.
Bottom-left corner: small "github.com/michal-giza/flutter-dev-agents"
in dim grey. Background: #0F1419 (near-black, slight blue tint).
No emoji, no clip art, no busy gradients.
```

Paste this into Claude.ai / ChatGPT image generation, save the
result as `social-preview.png`.

**Upload** via Settings → Social preview → Edit → drag-drop.

**Verify** it renders correctly:
https://www.opengraph.xyz/url/https%3A%2F%2Fgithub.com%2Fmichal-giza%2Fflutter-dev-agents

## Step 3 — pin the right thing in the README

GitHub already pins the README. Verify the top of the README
reads well in mobile width (the badges + tagline are the
above-the-fold content for every visitor).

## Step 4 — release on the right side

Confirm `Releases` panel on the right side shows `v0.2.1` with
the rich notes you published. If it shows the tag only without
notes, click `Edit release` and paste the GitHub-release body.

## Step 5 — pin labels

Add a `good-first-issue` label to anything that's a clean entry
point (the launch content's 3 awesome-mcp PRs each spawn natural
follow-up issues). Encourages community PRs.

---

**Sanity check before moving on:** paste your repo URL into Slack
or Discord. The unfurl should show:

- Title: `flutter-dev-agents`
- Description starting with "The first MCP server for autonomous Flutter testing…"
- A clean 2:1 preview image (NOT your avatar)
- Stars / forks / language stats

If any of those look off, fix before submitting anywhere else.
