# 12 · Twitter / X launch thread

**URL:** https://twitter.com/compose/tweet
**Effort:** 5 minutes to compose + ~1 hour reply window
**Why:** AI / dev-tool Twitter still drives meaningful inbound for technical products. A well-structured thread can pull 500-5000 impressions even from a small follower base because retweets compound.

## When to post

**Tuesday-Thursday, 15:30 CET (09:30 ET).** US East morning + EU late-afternoon overlap. Avoid Friday afternoon entirely.

## The thread structure

Twitter rewards: hook → context → punchline → CTA. 4-6 tweets is the sweet spot. Below is the recommended version — adjust for your style but keep the structure.

### Tweet 1 (the hook — most important)

```
Just open-sourced the first MCP server that lets Claude test my
Flutter app on a real Galaxy S25.

Cross-session device locks. 110 tools. Apache 2.0. PyPI today.

🧵👇
```

Notes:
- First 2 words are "Just open-sourced" — Twitter's algorithm boosts news-shaped tweets.
- The 🧵 emoji explicitly tells readers "thread" — opens the dropdown.
- No screenshot in tweet 1 — keep the text minimal. Reserve images for tweets 3 + 5.

### Tweet 2 (the why)

```
The problem: mobile QA spends 30-50% of engineering hours on
selector maintenance (Drizz 2026).

testWidgets pass today, break tomorrow because Android moved a
permission button from "Allow" to "While using the app."

Agents can close the loop. They just needed an MCP.
```

### Tweet 3 (the punchline — what makes this different)

Attach a screenshot of the README's headline + badges + "Why it
matters" section.

```
Every "AI mobile testing" tool I could find was iOS-sim-only,
web-only, or wrapped a cloud farm with $/minute pricing.

This MCP is real iPhones + real Androids, fully local, MCP
2025-06-18 compliant.

556 tests passing. First green CI today.

[screenshot of README hero]
```

### Tweet 4 (the technical bit — for the engineer audience)

```
Three design wins from a month of dogfooding:

• Tiered tool surface (BASIC=26 / EXPERT=110) for Claude Desktop's
  silent tool-count ceiling
• Filesystem-coordinated device locks (multi-Claude safe)
• Defense-in-depth cap pipeline that survived 3 production incidents

ADRs for each in the repo.
```

### Tweet 5 (the install — make it easy)

Attach the social preview PNG (`docs/design/social-preview.png`).

```
Install:
  pip install mcp-phone-controll
  claude mcp add phone-controll -- python -m mcp_phone_controll

Then ask Claude:
  "Run mcp_ping, pick my Android, take a screenshot."

5-min onboarding:
github.com/michal-giza/flutter-dev-agents
```

### Tweet 6 (CTA — engagement-oriented)

```
What I'd love feedback on:

• The tiered tool surface — server-side filter or let clients
  bring their own?
• inspect_image_safety + compress_png in BASIC — should this
  cross-MCP convention exist?
• How do you handle multi-project mobile testing today?

Replies open.
```

## Hashtags

Drop these in tweet 1 only (Twitter penalizes hashtag-stuffed
threads):

```
#Flutter #MCP #BuildInPublic
```

Skip `#AI`, `#Claude` — too broad, dilutes signal.

## Mentions (use sparingly)

Don't @ Anthropic / @AnthropicAI in tweet 1 — looks like
attention-bait. If a thoughtful response from Anthropic-ecosystem
folks materializes naturally, that's organic.

Do consider @ -ing in tweets 4-5 if relevant:
- `@leancodepl` (Patrol maintainers) — courtesy mention, they may RT.
- `@flutterdev` (official Flutter account, low chance of engagement
  but free if it lands).

## Quote-tweet / reply strategy

For the first hour after posting:

1. **Reply to every reply within 5 minutes.** Even a "thanks!"
   counts — Twitter's engagement signal is raw reply count.

2. **Don't quote-tweet your own thread.** Looks desperate; the
   algorithm flags it.

3. **DM 3-5 supporters before posting** asking them to retweet
   tweet 1 specifically (not the whole thread — tweet 1's RT
   count is what the algorithm sees).

## What to do with link previews

Twitter's link unfurl uses the GitHub repo's social preview image
— which is why uploading `docs/design/social-preview.png` to the
repo BEFORE posting matters. Verify the unfurl at
https://www.opengraph.xyz before publishing tweet 5.

## If you have < 100 followers

Twitter rewards networks more than content. With a small
following:

- Reply to other people's launch tweets / Show HN threads earlier
  in the day — your reply visibility on a big thread > your own
  tweet's visibility to your 50 followers.
- Tag 2-3 specific projects/people whose work yours genuinely
  complements (not "please RT" — "here's a piece I think Patrol
  users will appreciate").
- Don't expect Twitter alone to drive the launch. The thread is
  long-tail signal; HN + dev.to + LinkedIn carry the volume.

## What success looks like

- **Tweet 1 above 100 impressions in 30 min**: thread is moving.
- **Tweet 5 (install) gets retweeted by anyone with > 1000
  followers**: thread is winning.
- **A direct reply from a real engineer with a real question**:
  more valuable than 1,000 likes. That's the thread genuinely
  reaching its audience.

Most launches don't go viral. Two-three real-engineer replies +
50-200 impressions per tweet is a successful indie thread. Treat
the durable wins as the metric, not the dopamine spike.
