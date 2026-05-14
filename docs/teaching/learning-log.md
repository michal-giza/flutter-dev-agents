# Learning log — what we shipped, what it taught us

A living document. Each entry is one engineering session distilled
to its transferable lessons. The point is not to capture *what
happened* — the commits do that. The point is to capture *what we
now know better*.

Use this when writing course material: every lesson should have a
"what this taught us" section, and that section should pull from
here.

---

## 2026-05-14 / 15 — Tier H + I + diagnostics + n8n

**Shipped:**
- Hybrid retrieval (dense + lexical RRF) for `recall`
- CRAG self-grading wrapper (`recall_corrective`)
- Reflexion retry phase in plan walker
- Voyager-style skill library (`promote_sequence` etc.)
- `MCP_STRICT_TOOLS` schema enforcement
- Benchmark harness + 10 contract tasks
- Index-watcher script
- `mcp_ping` + boot self-check + version handshake
- `set_agent_profile` for 4B ergonomics
- `extract_ui_graph` + `ocr_screenshot` (visual UI agent SOTA)
- `ProgressLogMiddleware` for per-call latency
- JSON-line structured logging
- Tool catalogue auto-generator
- MLX example loop
- 5 ADRs documenting load-bearing choices
- `.mcpignore` + credential exclusion in indexer
- HTTP-adapter `MCP_HTTP_API_KEY` auth
- `notify_webhook` + 3 n8n workflow templates
- Senior code review with B+/A− grading

**What we learned:**

### 1. The platform-constraint trap

We hit the 2000px image limit four times. Each fix was real but
incomplete. The lesson: **when a platform has a hard rule, fix it
once at the most architectural layer you have.** The
dispatcher-level seatbelt — *not* per-use-case caps — is what
actually closed the issue. Per-use-case fixes scale by N callers;
N is unbounded as the project grows. One seatbelt scales by zero.

**Teach this in Lesson 6.** Frame: "the agent eats your context" is
the same pattern as "the agent breaks the image limit" — both are
platform constraints. The discipline is to put the constraint
enforcement at the architectural boundary, not at every caller.

### 2. Stale subprocess is the most common bug class

Three of this week's "this should work but doesn't" incidents were
the MCP subprocess running old code. The lesson: **make state
visible before debugging the symptom.** `mcp_ping` is the smallest
possible self-identification mechanism, and shipping it eliminated
an entire class of debugging round-trips.

**Teach this in Lesson 3 (failures + recovery).** Frame: "when the
agent says something is missing, the first question is whether
the runtime is up to date." Pair with `next_action: "restart_mcp"`.

### 3. Cognitive load is asymmetric across audiences

We wrote `mcp_ping`'s description in 45 words for the BASIC tier
ladder. The audit test failed (cap is 35). For Claude, 45 words
is fine. For Qwen 2.5-7B, those extra 10 words are 30% of its
working memory for the tool. The lesson: **the smallest LLM in
your supported set is your cognitive-load constraint.** Design
for it.

**Teach this in Lesson 6.** Frame: write descriptions for the 4B
model. Test on Claude. Don't do it the other way around.

### 4. Defense in depth, not defense in faith

The image-cap fix needed:
- Per-use-case caps (belt)
- Dispatcher seatbelt (seatbelt)
- Multi-backend fallback (cv2/PIL/sips)
- Hard-refuse with structured error
- Historical audit script for files captured before the fix

Each layer alone failed at some point. Together they're robust.
The lesson: **when a constraint is non-negotiable, don't trust
any single layer to enforce it.**

**Teach this in Lesson 2.** Frame: "the layers exist because no
single layer is trustworthy when the caller is an LLM." This is
*also* the answer to "why Clean Architecture for agent tooling."

### 5. ADRs are write-once-read-forever

Five ADRs in `docs/adr/` for the load-bearing choices. The cost
was ~2 hours of writing. The value: I just used them to write a
course catalogue, and I didn't have to re-derive any decision.
Six months from now, someone (probably me) will use them again.

**Teach this in Lesson 2 (introduce) and Lesson 8 (revisit).**
Frame: "the commit message is for your past self; the ADR is for
your future self."

### 6. The middleware refactor was overdue

`ToolDispatcher.dispatch` had grown to 120 LOC with 7 inline
concerns. Splitting it into a chain was a 1-hour refactor that
unlocked: independent unit testing of each concern, easy
addition of new cross-cutting concerns (ProgressLog landed in
30 minutes the next day), clean reasoning about ordering.

**Teach this in Lesson 4 or 5.** Frame: "when a function has 7
reasons to change, it has 7 modules waiting to be born."

### 7. The course-material gap is structural, not effortful

We had ~3000-word article #1 ready for 6 weeks and didn't ship a
single paid student. Article-to-course conversion isn't an
effort problem; articles can't *teach* without exercises and
feedback loops. The lesson: **content sells; teaching closes.**

**Teach this to yourself.** Don't conflate the two when planning
the launch funnel.

---

## What's NOT yet in the learning log (gaps to fill)

These would each be one entry once the work actually happens:

- "Splitting `tool_registry.py` into descriptors/*.py"
  (currently 2843 LOC; what we learned doing it)
- "Pre-commit hook landed"
  (what shipped through CI that pre-commit caught locally)
- "vm_service_client.py coverage filled"
  (what fake-WebSocket harness pattern emerged)
- "First cohort feedback"
  (what 30 students saw that we missed)

Fill these in as they happen. The log compounds.

---

## How to write a good entry

A bad entry: "We added X. It works."

A good entry has four parts:

1. **What we shipped** (one sentence per item).
2. **What we learned that we didn't know before.**
3. **Why it generalises** (why someone else would care).
4. **Where it should appear in teaching material.**

If an entry doesn't have part 4, it's a journal entry, not a
learning log. Journal entries are fine — they just go elsewhere.
