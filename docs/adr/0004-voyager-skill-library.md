# ADR-0004: Voyager-style skill library, SQLite-persistent

**Status:** accepted
**Date:** 2026-05-14

## Context

Across a week of multi-project sessions, the same boilerplate
sequences appeared dozens of times: "select device, open IDE, start
flutter run --machine, wait for app.started, hot reload". An agent
discovering this from scratch every session is waste. Voyager (Wang
et al., 2023, [arXiv:2305.16291](https://arxiv.org/abs/2305.16291))
demonstrated that an agent that names and reuses successful
sequences compounds capability across sessions in ways a stateless
agent cannot.

## Decision

Three tools backed by SQLite:

- **`promote_sequence(name, description, from_seq, to_seq, only_ok)`**
  — capture a slice of the current session trace as a named macro.
- **`list_skills()`** — return library entries ordered by use count.
- **`replay_skill(name, overrides)`** — re-execute through the
  dispatcher; `$`-prefixed args substituted from `overrides`.

Persistence via `SqliteSkillLibraryRepository` at
`<artifacts>/skill-library.db` by default; configurable via
`MCP_SKILL_LIBRARY_DB`.

Use count + success count tracked per skill. Discovery/introspection
tools (`describe_*`, `session_summary`, `narrate`) are filtered out
of promoted sequences automatically — skills capture *action*, not
*observation*.

**Out of scope (deliberate):**
- Auto-promotion. Agents call `promote_sequence` explicitly. False
  positives in heuristic detection would pollute the library.
- Cross-session curriculum (Voyager's "skill graph"). We do flat
  named macros, not parametric programs.
- Skill composition (skill A calling skill B). Add when needed.

## Consequences

**Easier.** Repeated rituals collapse to one tool call. The
audit-trail value is also high: a skill named `boot_debug_session`
is a self-documenting unit of factory work.

**Harder.** Skill names must be globally unique (snake_case enforced).
Replay assumes the device + IDE state matches what the skill
expects — no auto-precondition checks yet.

**Accepted.** SQLite as a runtime dep (already pulled in by the
sqlite-trace work in ADR-N). Skill staleness: a skill promoted
against iOS won't replay against Android.

## Alternatives considered

- **YAML plans only** — they're declarative but verbose; not
  suitable for the boilerplate-collapse use case.
- **JSON skill library in artifacts dir** — less queryable; worse
  for cross-machine sync.
- **Auto-promotion via heuristic** — false-positive cost too high
  for v1. Revisit if we run a quantified study.

## References

- `src/mcp_phone_controll/domain/usecases/skill_library.py`
- `src/mcp_phone_controll/data/repositories/sqlite_skill_library_repository.py`
- `tests/unit/test_skill_library.py`
- Wang et al., 2023, Voyager — [arXiv:2305.16291](https://arxiv.org/abs/2305.16291)
