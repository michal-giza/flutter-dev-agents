# Next-session enhancements

The list of work that's been scoped, isn't blocking anything tonight,
and should land in a future batch. Carved out of conversation history,
the article #1 / #2 backlog, and the arxiv literature review.

Format per item: a short title, why it matters, the rough shape of the
change, and the paper/source the design is grounded in (if any).

---

## Tier H — agent literacy (next batch)

### H1. Hybrid retrieval (dense + sparse) on `recall`

**Why.** Dense BGE-small handles "concept" queries (`UMP gate
preconditions`) well; BM25 wins on exact-token queries (`stop_app`,
`SerialNumber`). Hybrid retrieval is empirically dominant for both
(Karpukhin et al., 2020, [arXiv:2004.04906](https://arxiv.org/abs/2004.04906); Reichman & Heck,
2024, hybrid-RAG survey). **Shape.** Add `qdrant-client` BM25 sparse
index alongside the dense vectors; combine via reciprocal-rank fusion
(RRF). One method, one index.

### H2. CRAG (corrective RAG) on top of `recall`

**Why.** The agent currently trusts `recall` results blindly. CRAG
adds a self-grading step: if retrieved chunks score below a threshold,
fall back to a different scope or to web search (Yan et al., 2024,
[arXiv:2401.15884](https://arxiv.org/abs/2401.15884)). **Shape.** Wrap `Recall` in
`RecallWithGrade` that computes a relevance score and re-queries with a
different scope when the score is low. Article enhancement #6 ties in.

### H3. Reflexion-style retry loop in plan walker

**Why.** When `UNDER_TEST` fails, the plan walker today emits
`VERDICT_BLOCKED`. Reflexion (Shinn et al., 2023,
[arXiv:2303.11366](https://arxiv.org/abs/2303.11366)) shows a self-critique-and-retry
loop dramatically improves task success on long-horizon agent tasks.
**Shape.** Add a `_reflect` phase before `VERDICT_BLOCKED` that asks
the agent to write one sentence on why it failed, then attempts up to
2 retries with the new context. Gated by `MCP_REFLEXION_RETRIES`.

### H4. Voyager-style skill library

**Why.** Voyager (Wang et al., 2023,
[arXiv:2305.16291](https://arxiv.org/abs/2305.16291)) showed lifelong-learning
agents accumulate a per-task skill library that compounds over time.
We have a session trace; we don't yet promote successful sequences to
**reusable named skills**. **Shape.** Add `promote_sequence(name,
trace_slice)` that captures a successful tool sequence as a named
"macro" the agent can invoke. Lives in SQLite alongside the trace.

### H5. Pydantic + `outlines`-style grammar enforcement

**Why.** Article enhancement #2. Today the dispatcher coerces loose
types ("true" → True). Stronger: constrain the model's output at the
sampling layer so it can only emit schema-valid arguments
(Willard & Louf, 2023, "Efficient guided generation",
[arXiv:2307.09702](https://arxiv.org/abs/2307.09702)). **Shape.** A
`adapters/openai_compat.py` extension that ships JSON Schemas to
clients implementing OpenAI's `tools` field with `strict: true`. Stop
double-validating; trust the sampler.

---

## Tier I — productization (after Tier H)

### I1. Tool-usage benchmark suite

**Why.** Tool-LLM benchmarks (Qin et al., 2023,
[arXiv:2307.16789](https://arxiv.org/abs/2307.16789)) measure agent quality on a
fixed set of tasks. We don't have a benchmark; we should. **Shape.**
A `bench/` directory with 20 representative tasks (run a Patrol test,
hot-reload after edit, retrieve UMP guidance, scaffold a feature),
each with a deterministic expected envelope. Run nightly against
`qwen2.5:7b`, `qwen2.5:14b`, Claude Haiku, Claude Sonnet. Publish the
table.

### I2. CI Docker image

**Why.** Already noted in the umbrella plan as deferred. Now warranted:
the course publishes well in a container; consulting clients want a
hand-off they can run in GitHub Actions. **Shape.** Already specced —
`packages/phone-controll/docker/Dockerfile.ci`, headless Linux x86_64,
Android emulator + Flutter + Patrol + MCP. ~1 day of work.

### I3. Promote `mcp-rag-bridge` to its own package

**Why.** If hybrid + CRAG + grammar work lands, the RAG layer in
`phone-controll` becomes substantial. Tracking surfaces drift between
the course and the production code. **Shape.** Move `data/chunker.py`,
`data/repositories/{qdrant,null}_rag_repository.py`, and
`domain/usecases/recall.py` into `packages/mcp-rag-bridge/`. Re-export
from `phone-controll`. Versioned independently.

### I4. Indexing watcher

**Why.** `index_project` is one-shot. For real usage, the agent wants
the index to track edits. **Shape.** Add a thin CLI
`scripts/watch_index.py` that uses `watchdog` to re-index on file
modification, debounced. Optional dep.

---

## Tier J — research bets (when time permits)

These are 1–3 day investigations, not batches to ship blindly.

### J1. ReAct vs Plan-and-Solve for the dev loop

ReAct (Yao et al., 2022, [arXiv:2210.03629](https://arxiv.org/abs/2210.03629))
interleaves reasoning and action. Plan-and-Solve (Wang et al., 2023,
[arXiv:2305.04091](https://arxiv.org/abs/2305.04091)) plans the full sequence
upfront. We've leaned ReAct; when the agent has a strong prior (the
`recommended_sequence`, the SKILL), Plan-and-Solve may dominate. Run
both styles against I1's bench, publish results.

### J2. Long-context vs RAG ablation

Now that `recall` exists, we can measure: does feeding the whole
SKILL beat retrieving 3 chunks? Likely no on 4B — but it's testable.
"Lost in the Middle" (Liu et al., 2023,
[arXiv:2307.03172](https://arxiv.org/abs/2307.03172)) predicts RAG wins. Confirm
the prediction on our specific tasks; the answer becomes part of the
article.

### J3. Tree-of-Thoughts on plan validation

Tree-of-Thoughts (Yao et al., 2023,
[arXiv:2305.10601](https://arxiv.org/abs/2305.10601)) explores multiple branches
before committing. `validate_test_plan` could speculatively branch on
"what if this driver were `flutter_test` vs `patrol_test`?" and pick
the branch that scores highest before suggesting the fix. Probably
overkill, but worth measuring.

---

## Article queue

- **Article #2 (drafted in Tier G):** "8 KB SKILL is overkill — a RAG
  bridge for one-person Flutter dev factories." References Lewis 2020,
  Liu 2023, Karpukhin 2020.
- **Article #3 (Tier H):** "Reflection, retry, and corrective RAG —
  what ReAct alone can't do." References Shinn 2023, Yan 2024.
- **Article #4 (Tier I):** "How to benchmark your own agent stack."
  References Qin 2023; ToolBench, MetaTool benchmark methodology.
- **Article #5 (Tier J):** "ReAct vs Plan-and-Solve, measured against
  a real Flutter factory."

---

## Notes on the literature search

Re-check arxiv quarterly for these specific search terms to stay
current:

- "tool-augmented LLM" / "tool calling agent"
- "retrieval-augmented agent"
- "skill library lifelong learning"
- "code agent benchmark"
- "small language model 4B agent"
- "MCP / Model Context Protocol"

Citation-graph crawl from any new paper you read; track what cites
Toolformer, ReAct, Voyager. Most production-relevant work now sits at
the intersection of those three threads.

---

## Tier K — iOS reliability (real-user bug reports, May 2026)

These two issues were caught during hands-on testing against the
iPhone 17 simulator and a physical iPhone 15. Capture them here so
the fix is grounded in real failure modes, not theoretical worry.

### K1. iPhone 17 sim (iOS 26.5): `tap`/`swipe` crash with `'NoneType' object has no attribute 'make_http_connection'`

**Symptom.** Every UI control tool against the iPhone 17 simulator on
iOS 26.5 fails immediately. Trace ends in
`'NoneType' object has no attribute 'make_http_connection'`. UI control
is fully blocked — affects `tap`, `swipe`, `type_text`, `press_key`,
anything that routes through the WDA factory.

**Root cause (likely).**
`packages/phone-controll/src/mcp_phone_controll/infrastructure/wda_factory.py`
always constructs `wda.USBClient(udid)` regardless of whether the
target is a physical device or a simulator. `USBClient` connects over
**usbmux**, which doesn't exist for simulators. For simulators you
need `wda.Client("http://localhost:<wda-port>")` (the WDA server is
listening on a TCP port that `xcrun simctl launch …
WebDriverAgentRunner` exposes, not over usbmux). The `None` is the
result of the usbmux lookup silently failing; the next
`.make_http_connection()` call attribute-errors on it.

**Shape of fix.**
1. Teach the WDA factory to distinguish physical iPhone from simulator
   UDIDs. Cheapest check: ask `xcrun simctl list devices -j` and see
   if the UDID is in the booted-simulator set.
2. Branch: physical → `wda.USBClient(udid)`; simulator →
   `wda.Client(f"http://localhost:{port}")` where `port` is captured
   from the WDA server's startup log when we launch
   `com.facebook.WebDriverAgentRunner.xctrunner` via `simctl` (default
   8100, but Xcode auto-picks if 8100 is taken).
3. Add an integration test using a fake `simctl` runner + a fake
   `wda` module that asserts the right constructor is picked per
   target type.
4. Update `docs/ios_setup.md` with a one-paragraph "WDA on simulators
   vs. devices" section.

**Why now.** This is a *complete* block on iOS-simulator workflows —
the recommended dev loop for users without a physical iPhone.
Severity: critical for iOS adoption. Estimated effort: ½ day.

**Citations / source.** Real user bug report, May 2026. Cross-check
against Appium's
[WebDriverAgent docs](https://github.com/appium/WebDriverAgent#usage)
which document the same physical-vs-sim split.

---

### K2. Physical iPhone 15 (iOS 26.2.1): `take_screenshot` hint for missing tunneld is misleading

**Symptom.** `take_screenshot` against a real iPhone fails with the
`start_tunneld` next_action. The user follows our hint
(`sudo pymobiledevice3 remote tunneld`) and it fails immediately
because `pymobiledevice3` isn't installed — the system Python at
`/Applications/Xcode.app/Contents/Developer/usr/bin/python3` has no
such module.

**Root cause.** Our hint assumed `pymobiledevice3` is on PATH. On a
freshly-cloned dev machine it isn't — Xcode's bundled Python doesn't
ship it, and the MCP's venv is a separate world. We were documenting
the daemon-start step but skipping the install step.

**Shape of fix (partially landed — full fix outstanding).**
1. ✅ **Done in this commit.** The hint in `IOSObservationRepository`
   now lists the install command FIRST (`pipx install pymobiledevice3`
   or `pip3 install --user pymobiledevice3`), then the daemon start
   using `sudo $(which pymobiledevice3) remote tunneld`.
2. ⏳ **Still TODO.** `check_environment` (the doctor) should probe
   for `pymobiledevice3` explicitly and emit a red item with the same
   two-step fix when missing. Right now the doctor doesn't catch this
   — the install gap is only surfaced at first use, not at startup.
3. ⏳ **Still TODO.** `scripts/install.sh` should `pipx install
   pymobiledevice3` as part of fresh-laptop bootstrap so new devs
   never hit this.
4. ⏳ **Still TODO.** Update `docs/ios_setup.md#tunneld` with the
   install-first instructions verbatim.

**Why now.** This blocks the second-most-common iOS flow (physical
device screenshotting) until the user works out — through
trial-and-error — that they need a separate install step. Severity:
medium. Estimated effort: 2 hours for items 2–4 above.

**Open question.** Should `pymobiledevice3` be an explicit dependency
in `pyproject.toml`'s `[ios]` extra, so `uv pip install -e ".[ios]"`
during install just works? Argument *for*: zero-friction onboarding.
Argument *against*: tunneld still needs root (`sudo`), so installing
the library doesn't fully solve the UX — a privilege-escalation step
remains regardless. Probably still worth doing.

**Citations / source.** Real user bug report, May 2026. Confirmed by
inspecting Xcode's bundled Python on macOS — `import pymobiledevice3`
raises `ModuleNotFoundError`.
