# Article #3 — Reflection, retry, and corrective RAG: what ReAct alone can't do

**Target word count:** ~3000. **Audience:** solo founders / small studios
running 4B-class local LLMs alongside Claude. **Hook:** ReAct isn't enough.

## Outline

### Cold open (300 words)
A real failure: the agent ran a Patrol test, it timed out, the agent
went straight to `VERDICT_BLOCKED` and gave up. The test was *flaky* —
running it once more would have passed. ReAct (Yao et al., 2022) gives
you reason+act, but it doesn't give you "look at what failed, write
one sentence about why, try again." That's Reflexion. We shipped it.

### Why ReAct is necessary but not sufficient (400 words)
- Cite Yao et al., 2022 ([arXiv:2210.03629](https://arxiv.org/abs/2210.03629))
  — interleave reason + act.
- The "decision drift" problem on long-horizon tasks (15+ tool calls).
- The "no retry" problem: a transient failure is functionally identical
  to a hard failure unless the agent can self-distinguish them.

### Reflexion in our stack (500 words)
- Cite Shinn et al., 2023 ([arXiv:2303.11366](https://arxiv.org/abs/2303.11366)).
- The implementation — `_REFLEXION_RETRYABLE` phases, the synthetic
  diagnosis stamped on a `REFLECTION` pseudo-phase, the `overall_ok`
  semantics that treat retried-successfully outcomes as recovered.
- Code excerpts from `yaml_plan_executor.py`.
- The `MCP_REFLEXION_RETRIES=2` environment knob — off by default for
  Claude (which doesn't need it), default `2` for Qwen-7B.

### CRAG — when to trust your retrieval (600 words)
- Cite Yan et al., 2024 ([arXiv:2401.15884](https://arxiv.org/abs/2401.15884)).
- The relevance-grading insight: an LLM can't tell when retrieval
  failed; the grader has to be downstream of retrieval, upstream of
  the answer.
- Our applied form — `recall_corrective` with lexical-overlap as the
  cheap relevance score, scope-fallback as the corrective action.
- Why we deferred LLM-based grading (it costs another model call;
  measure before adding).
- A war story: a 4B-model query for "UMP gate decline preconditions"
  retrieved generic Patrol guidance; CRAG fell back from `scope=trace`
  to `scope=skill` and got the right chunk.

### Numbers (400 words)
- Bench results: 10 tasks × {without Reflexion, with Reflexion=2} ×
  {without CRAG, with CRAG} = 4 conditions per task.
- Honest reporting: gains aren't uniform. Hot-reload retries help a
  lot; AR_SCENE_READY retries don't (a stable AR session needs human
  re-aim, not retry). Document where each helps.

### What this DOESN'T fix (300 words)
- A wrong PRE_FLIGHT (env issue) — retry won't help; the error message
  already points at `run_check_environment`.
- A genuinely-broken Patrol test — Reflexion will eat your N retries
  and still verdict blocked. Set N small.
- Hallucinated tool calls — orthogonal; the strict-schema flag (H5)
  attacks that one.

### Try it yourself (200 words)
```bash
MCP_REFLEXION_RETRIES=2 python -m mcp_phone_controll
# In your prompt: ask the agent to run a flaky Patrol test against
# your project. Observe REFLECTION phases in session_summary.
```

### What's next (100 words)
Article #4 covers the Voyager skill library — when retries succeed,
promote the sequence. When they fail, learn the negative pattern.
Compounding agents.

### References
- Yao et al., 2022 — ReAct, [arXiv:2210.03629](https://arxiv.org/abs/2210.03629)
- Shinn et al., 2023 — Reflexion, [arXiv:2303.11366](https://arxiv.org/abs/2303.11366)
- Yan et al., 2024 — CRAG, [arXiv:2401.15884](https://arxiv.org/abs/2401.15884)
- Wang et al., 2023 — Plan-and-Solve, [arXiv:2305.04091](https://arxiv.org/abs/2305.04091)

## Distribution
- **Blog (canonical).** Title: "Reflection, retry, and corrective RAG."
- **Hacker News.** Title: "Adding Reflexion + CRAG to a 100-tool MCP."
- **r/LocalLLaMA.** Title: "How my 4B agent stops giving up."
- **Substack.** Same as blog, plus a paid-only "what didn't work"
  postscript.
