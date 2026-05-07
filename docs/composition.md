# Composition: `flutter-dev-agents` × `rag-search`

How the two repositories relate, what depends on what, and where the
boundaries live. Keep this doc current; if you can't explain a coupling
in one paragraph, the coupling is wrong.

## The two projects

| Repo | Role | Lives at |
|---|---|---|
| **`flutter-dev-agents`** | The MCP — drives Flutter dev workflows on real devices | `~/Desktop/flutter-dev-agents/` |
| **`rag-search/codebase-rag`** | The RAG-to-agents course + a working agent capstone | `~/Desktop/projects/rag-search/codebase-rag/` |

They are **independently runnable**. Neither imports the other at
runtime. The course teaches the patterns; `phone-controll` ships a
small, production-grade subset of those patterns under
`packages/phone-controll/src/mcp_phone_controll/data/`.

## Why duplicate the RAG implementation?

Reading the course explore agent's report: `rag-search` is structured
as 4 teaching modules + a capstone — `requirements.txt`-based, no
`pyproject.toml`, not pip-installable as a library. Importing from it
would couple `phone-controll` to a non-versioned source tree.

The right boundary: **`phone-controll` ships its own minimal RAG layer
inspired by the course, not bound to it.** Concrete pieces:

- `data/chunker.py` — language-aware chunker (md / dart / py / fixed
  fallback), 200 LOC, no external deps.
- `data/repositories/qdrant_rag_repository.py` — Qdrant + FastEmbed
  adapter, ~280 LOC, optional `[rag]` extra.
- `data/repositories/null_rag_repository.py` — informative-failure
  fallback when extras aren't installed.
- `domain/usecases/recall.py` — `Recall`, `IndexProject`.

The course's chunking strategies, hybrid search, and ReAct multi-agent
patterns are taught in `rag-search`. `phone-controll` doesn't try to
re-teach them; it uses the smallest correct subset.

## The bridge in one diagram

```
┌──────────────────────────────────────────────────────────────────┐
│ Claude (or local 4B agent) — sole consumer of both MCPs           │
└──────────────────────────────────────────────────────────────────┘
              │                                       │
              │ stdio (mcp add)                       │ stdio (mcp add — opt)
              ▼                                       ▼
┌──────────────────────────┐         ┌────────────────────────────────┐
│   phone-controll         │         │   rag-search/ai_project_root   │
│   (92 + 2 = 94 tools)    │         │   (search_codebase, agent UX)  │
└──────────────┬───────────┘         └────────────────────────────────┘
               │                                       
               │ (in-process)
               ▼
┌──────────────────────────┐    ┌────────────────────────┐
│ QdrantRagRepository      │───▶│ Qdrant (Docker, 6333)  │
│ FastEmbed (ONNX)         │    │ collections/*           │
└──────────────────────────┘    └────────────────────────┘
```

Two MCPs, one Qdrant. The agent picks which to call based on the
question:
- "where in this Flutter project is X defined?" → `search_codebase`
  (rag-search) — has the agent capstone's metadata schema, knowledge
  graphs, and Dart-specific tuning.
- "what does the SKILL say about UMP_GATE?" → `recall(scope="skill")`
  (phone-controll) — locally indexed SKILL.md and docs.

Same Qdrant binary; different collections; no contention.

## Optional dependency model

`phone-controll` declares the RAG stack as an **opt-in extra**:

```toml
[project.optional-dependencies]
rag = [
    "qdrant-client>=1.9",
    "fastembed>=0.3",
]
```

Default install is unaffected. Without `[rag]`:

- `recall` returns `RagUnavailableFailure` with
  `next_action="install_rag_extra"` and an exact `fix` command in
  `details`.
- `index_project` does the same.
- All other 92 tools work normally.

With `[rag]` and Qdrant running:

- `Recall` and `IndexProject` route to `QdrantRagRepository`.
- The choice happens once in `container.py:build_runtime()` via
  `rag_extras_available()` — no runtime branching after that.

## Versioning

| Repo | Version policy |
|---|---|
| `flutter-dev-agents/packages/phone-controll/pyproject.toml` | Semver-ish; bump when tool surface changes |
| `rag-search/codebase-rag` | Course versioning (Module N), no semver |

The two are loosely coupled by contract: `phone-controll` requires only
a Qdrant server reachable at `MCP_QDRANT_URL` (default
`http://localhost:6333`) and the `BAAI/bge-small-en-v1.5` embedding
model. Both ship with the `rag-search` capstone too — that's the only
point of overlap, and it's a static config, not an API.

### Environment variables (all optional)

| Variable | Default | Purpose |
|---|---|---|
| `MCP_QDRANT_URL` | `http://localhost:6333` | Qdrant server for `recall` / `index_project`. |
| `MCP_RAG_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | FastEmbed model name. |
| `MCP_TRACE_DB` | (unset → in-memory ring) | Path to SQLite file for cross-session trace persistence. |
| `MCP_SKILL_LIBRARY_DB` | (artifacts root) | Path to SQLite file backing the Voyager skill library. |
| `MCP_AUTO_NARRATE_EVERY` | `0` (off) | Attach a one-line `narrate` field every Nth dispatcher call. Recommended `5` for 4B agents. |
| `MCP_REFLEXION_RETRIES` | `0` (off) | Retry budget per failed retryable phase in the plan walker. |
| `MCP_STRICT_TOOLS` | unset (off) | When truthy, the OpenAI function-call adapter advertises `strict: true` — sampler-side schema enforcement. |
| `MCP_MAX_IMAGE_DIM` | `1920` | Long-edge cap for screenshots returned to the agent. Claude rejects multi-image conversations where any image exceeds 2000px; LLaVA / Qwen-VL prefer ≤1024px. Set `MCP_MAX_IMAGE_DIM=896` for tight local-vision-model context budgets, `0` to disable. Originals are preserved at `<path>.orig.png` so `compare_screenshot` and golden-image diffs stay full-resolution. |

## What lives where

| Concern | Owner |
|---|---|
| Drive a phone, hot-reload, run Patrol | `phone-controll` |
| Multi-window VS Code orchestration | `phone-controll` |
| Plan walker, JUnit emission, device locks | `phone-controll` |
| **Retrieve a SKILL chunk for the agent** | `phone-controll` (`recall`) |
| **Index a project once for retrieval** | `phone-controll` (`index_project`) |
| Teach RAG end-to-end (M1–M4) | `rag-search` |
| 5-level memory hierarchy, knowledge graphs | `rag-search` |
| Search a Flutter codebase semantically | `rag-search` (`search_codebase`) |
| LangGraph agent + Chainlit UI | `rag-search` |

When in doubt: anything that touches the device, the IDE, or the dev
loop is `phone-controll`. Anything that's about teaching, deep agent
loops, or course material is `rag-search`.

## Future split — if/when this grows

If `phone-controll`'s RAG layer outgrows the chunker + Qdrant client
(e.g. needs hybrid retrieval, re-ranking, GraphRAG), the right move is
to pull it into a third workspace package
`packages/mcp-rag-bridge/` and have `phone-controll` depend on it as a
sibling. Tracked in `docs/next-session-enhancements.md`. Don't do this
yet — premature.
