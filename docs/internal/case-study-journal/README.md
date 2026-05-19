# Case-study journal — raw notes for the eventual published case study

This folder captures **raw, dated, candid** notes from real-world
daily use of `mcp-phone-controll`. After ~7 days of entries, the
patterns get extracted into a polished case study at
`docs/case-study-week-1.md` that's safe to share publicly (LinkedIn
post + blog post + the README's "production use" badge).

The point: **published case studies that were written from memory
2 months later are always boring and vague.** Journal entries
written same-day are concrete. Concrete wins.

## How to use this

Every day you do real work with the MCP, run:

```bash
./scripts/case_study_today.sh
```

It creates today's entry from `_template.md` (or opens the existing
one if you already have entries today). 5 minutes of filling in.

Optional but useful: pipe `mcp_ping` output into the entry's
"environment" section so the post-extraction has version + git_sha
provenance.

## What to capture (template includes prompts for each)

- **Wins** — what the MCP made you do faster than you would have.
- **Surprises** — both good and bad. "I didn't expect X to work" or "X surprised me by failing this way."
- **Workarounds** — what you had to do around a missing feature or a quirk.
- **Pain points** — tools that should exist but don't, errors that weren't actionable, docs you couldn't find.
- **One concrete win number per day** — minutes saved, bugs caught, manual steps eliminated. Numbers convert; adjectives don't.

## What NOT to capture

- **App-specific details** that you wouldn't want public. Sanitize as
  you write — use `<my-app>` instead of real package IDs, redact
  any test credentials.
- **Long error stack traces** verbatim — summarize them, link to a
  gist if you need the full thing.
- **Other people's bugs** — if a teammate hit something, don't put
  their name in the public case study without consent.

## How extraction works

After ~7 days (or whenever you say "extract now"), I'll:

1. Read every dated entry in chronological order.
2. Identify 3–5 recurring themes (e.g. "iOS RSD routing kept breaking
   first try", "Polish localization bites about half of my sessions",
   "the BASIC tier was the right call for daily work").
3. Pick 1–2 standout stories per theme (the most concrete ones).
4. Draft `docs/case-study-week-1.md` as a public-facing narrative:
   intro → 5 stories → numbers → lessons learned → "would I
   recommend? (yes, with caveats X/Y)".
5. Produce a LinkedIn variant + a Twitter thread variant for
   distribution.

You review + edit before anything ships publicly. Nothing in this
folder ever auto-syncs to a public location.

## Day numbering

Entries are filed by ISO date: `2026-05-19.md`. The helper script
handles this automatically. If you have multiple "sessions" in one
day, put them as sub-headings inside the same date file.

## Existing entries

(Updated when you run the helper. Empty for now.)
