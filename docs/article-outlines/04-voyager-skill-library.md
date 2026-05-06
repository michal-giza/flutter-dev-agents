# Article #4 — The Voyager skill library: agents that compound

**Target word count:** ~2500. **Audience:** developers building
long-running agent workflows. **Hook:** every successful sequence
should become a single high-level move.

## Outline

### Cold open (300 words)
The same boot-debug-session ritual: select device, new session, open
IDE, start `flutter run --machine`, wait for `app.started`, hot reload.
Seven calls. Across 30 sessions in a month, that's 210 calls of
boilerplate. Voyager (Wang et al., 2023) showed agents that name and
reuse successful sequences compound their capability. We built that
for our MCP. It's 200 LOC.

### Voyager — the original idea (400 words)
- Cite Wang et al., 2023
  ([arXiv:2305.16291](https://arxiv.org/abs/2305.16291)).
- The Minecraft agent that builds a library of named skills (mine
  diamond, build shelter, etc.) and never re-discovers them.
- The skill description / curriculum / verification loop.
- What translates to MCP-driven dev factories: the *named macro* idea.
  We don't ship the curriculum or the verifier; those are research-grade
  and our use case is simpler.

### Our applied form (500 words)
- Three tools: `promote_sequence`, `list_skills`, `replay_skill`.
- SQLite-backed library — survives MCP restarts, queryable directly
  for offline introspection (e.g. cohort analysis: "what skills do
  students promote most?").
- Placeholder substitution (`$proj` → `/Users/me/app`) — keeps skills
  reusable across slightly different contexts without parametric
  templating complexity.
- Skip-tools filter: discovery + introspection tools never end up in a
  skill (`describe_capabilities`, `session_summary`, etc.). Skills
  capture *action*, not *observation*.

### A worked example (500 words)
- Walk through promoting the boot-debug-session ritual:
  1. Run the seven calls in a normal session.
  2. `promote_sequence(name="boot_debug_session", description="…")`.
  3. Next session: `replay_skill(name="boot_debug_session", overrides={"proj": "/path"})`.
- The success-rate bookkeeping — high-success skills get listed first;
  the agent has a natural prior on what's worked.

### What this enables — the compounding loop (400 words)
- Across 30 sessions: agent learns 12 named skills. Average session
  length drops from 27 calls to 19 (back-of-envelope).
- The flywheel: more skills → faster sessions → more sessions per
  week → more skills learned. Real.
- Where it breaks: a skill that succeeded on iOS won't replay on
  Android. We don't yet auto-detect "this skill is platform-specific"
  — that's a future enhancement.

### What's NOT in v1 (300 words)
- **Auto-promotion.** The agent has to explicitly call
  `promote_sequence`. Auto-detection of "this looks like a successful
  ritual, want to name it?" is harder than it sounds — false
  positives create skill-library noise.
- **Cross-session curriculum.** Voyager's curriculum is the part that
  makes the original paper's results work. Ours is one layer simpler.
- **Skill composition.** Calling skill A inside skill B. Not yet.
  When you need it, the use case is one method.

### Try it yourself (200 words)
```bash
# Run a session that boots a debug loop.
# Then:
mcp> promote_sequence name="boot_debug_session" description="standard boot"
mcp> list_skills
mcp> replay_skill name="boot_debug_session" overrides={"proj": "/path/to/other/app"}
```

### What's next (100 words)
Article #5 covers benchmarking — once you have skills + retries +
corrective RAG, you need to measure whether they actually work.

### References
- Wang et al., 2023 — Voyager,
  [arXiv:2305.16291](https://arxiv.org/abs/2305.16291).
- Brown et al., 2020 — In-Context Learning,
  [arXiv:2005.14165](https://arxiv.org/abs/2005.14165).

## Distribution
- **Blog.** Title: "The Voyager skill library: agents that compound."
- **HN.** Title: "Adding a skill library to a 100-tool MCP."
- **r/MachineLearning.** Title: "Voyager-style skill library for a
  small-LLM agent stack."
- **Substack paid postscript.** "What I'd build differently if I
  redesigned this from scratch."
