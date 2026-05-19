<!--
PRs land cleanest when they include the three things below. Skip
the sections that don't apply (e.g. tests for docs-only).

For the title: use the `type: short description` convention from
recent commits:
   fix(ios): route developer-tier commands through --rsd
   docs: capture 4 operational gotchas
   release: 0.2.2 — launch readiness
-->

## Summary

<!-- 1-3 bullets. Why this PR exists in the user's words. -->

-

## What changed

<!-- Concrete list of files / behaviors. Skip if the diff is small
     and self-explanatory. -->

-

## Verification

<!-- How did you confirm this works? Required for code changes;
     skip for docs-only. -->

- [ ] `MCP_QUIET=1 pytest -q --no-cov` passes locally
- [ ] `ruff check src tests scripts` clean
- [ ] If new tools / changed schemas: `UPDATE_CONTRACT=1 pytest tests/unit/test_tools_list_contract.py` refreshed
- [ ] If new tools in BASIC tier: description ≤ 35 words, total BASIC ≤ 30 tools
- [ ] Tested manually on a real device (if device-touching code)

## Roadmap fit

<!-- Pick the closest. Skip if obviously a fix. -->

- [ ] Bug fix — addresses an existing issue (link below)
- [ ] On the roadmap's "Now" or "Next" — see `ROADMAP.md`
- [ ] New work not yet on the roadmap — explain why it should land before queued items

## Linked issues

<!-- `Closes #123` / `Refs #45` -->

-

## Notes for reviewers

<!-- Anything non-obvious. Decisions you made, alternatives you
     considered, things you're unsure about and want a second
     opinion on. -->
