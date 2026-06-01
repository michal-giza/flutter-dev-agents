# Case studies

Real Flutter projects audited with the `mcp-phone-controll`
audit suite. Each writeup documents the findings + paste-ready
remediation patterns + estimated fix effort.

These exist to demonstrate the audit suite **finds real
things**, not theoretical ones — and to give adopters a
template for what their own findings should look like.

## Available case studies

| Project | Audit run | Findings | FP rate | Effort | Status |
|---|---|---|---|---|---|
| [`bike-news-room`](bike-news-room.md) | `audit_code_seniority`, `min_level=senior` | **20** | **0%** | ~6h fix+test | findings documented, fixes pending |

## How to add your own

1. Run the audit against your project
2. For each finding, classify: real / acceptable / false-positive
3. Document the **rule slug, file:line, paste-ready remediation**
4. Estimate effort per type
5. Add a paragraph about "what this proves" (the meta-point)

The bike-news-room writeup is the canonical template.
