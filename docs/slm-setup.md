# Running with small / local models (SLMs)

> How phone-controll — and the composed stack (Google's `dart
> mcp-server`, Chrome DevTools MCP, Playwright MCP, Maestro) — adapts to
> **small / local models** (Ollama, vLLM, LM Studio, llama.cpp, 4–14B
> open weights), not just Claude. The constraints are **operational**,
> not capability-based: every piece is model-agnostic; the work is
> keeping the tool surface and outputs small enough for a small model to
> reason over.

## The one rule: budget the tool surface

A small model handed 140+ tool schemas reasons badly — it picks wrong
tools, hallucinates arguments, or stalls. **Scope the surface.**

phone-controll has a built-in tiering lever on **both** transports:

| Transport | How to scope |
|---|---|
| **stdio** (Cline, Continue, LM Studio, Claude Desktop) | `MCP_TOOL_TIER=basic` env on the server process |
| **OpenAI-compat HTTP adapter** (the usual SLM path) | `GET /tools?tier=basic` query param, **or** the `MCP_TOOL_TIER` env |

Tiers: **`basic`** (~26 tools — discovery + device control + the audit
entry points), **`intermediate`** (~59), **`expert`/unset** (all ~143).
The full dispatcher is always wired — a tool not in the advertised list
still dispatches if the agent names it. The long tail is reachable
on-demand via **`describe_capabilities(level="basic"|"intermediate"|
"expert")`**, which returns the tool subset for a level — the
universal discovery entry point that works on every transport.

**Recommendation:** start an SLM at `tier=basic`, let it call
`describe_capabilities` to pull in more tools only when a task needs
them.

## Composing other MCPs with an SLM

The catch: each extra MCP adds its own tools to the model's list. Adding
**all** of dart mcp-server (~24) + chrome-devtools (~26) + playwright
(~25) + our 143 = 200+ schemas — far past what a small model handles.
So with an SLM, **load only the MCPs a task needs**, not the whole stack.

| Need | SLM-friendly choice | Notes |
|---|---|---|
| Audit / grade / release-readiness | **phone-controll** (`tier=basic`) | pure-compute, concise outputs, no device, no roots — the safest SLM surface |
| Web *driving* (login/scroll/import) | **Playwright MCP** | vision-free **accessibility-tree** snapshots (~200–400 tokens, deterministic refs) — built for non-vision models; lighter than Chrome DevTools MCP |
| Web *debug / frames / network* | **Chrome DevTools MCP** | richer (perf traces, network) but heavier per call — add only when you need it, not by default |
| SDK plumbing (analyze/fix/format/pub) | **Google's `dart mcp-server`** *or* our commodity tools (below) | |

### `dart mcp-server` with an SLM

It's model-agnostic (MCP protocol), so any SLM that runs an MCP client
can use it — but two operational notes:

1. **Roots fallback.** It expects MCP "roots"; many SLM agent
   frameworks don't implement roots. Launch it with
   **`dart mcp-server --force-roots-fallback`** so it works without them.
   ```bash
   claude mcp add dart -- dart mcp-server --force-roots-fallback
   ```
2. **Verbose output.** `analyze_files` / the widget inspector can emit
   large payloads that blow a small context window. Use them
   surgically; prefer scoped paths.

### If your SLM speaks only ONE MCP (our HTTP adapter)

A common local setup is "one model → one MCP endpoint" — it hits our
`/tools` and nothing else, so `dart mcp-server` isn't reachable. That's
fine: **our SDK-plumbing commodity tools cover it** —
`dart_analyze`, `dart_fix`, `dart_format`, `flutter_pub_get`,
`flutter_pub_outdated`. We marked these "prefer Google's `dart
mcp-server` when both are registered," but when it *isn't* (the
single-MCP SLM case) they are the intended path. So a lone SLM on the
HTTP adapter still gets analyze/fix/format/pub + the whole audit suite +
device control — no composition required.

## Why our audit layer is the SLM sweet spot

The audit + ingest tools (`audit_code_seniority`, `audit_security`,
`audit_performance`, `audit_release_readiness`, `ingest_har`,
`ingest_frame_timeline`, …) are:

- **pure-compute** — no device, no VM, deterministic;
- **concise** — they return a grade + a bounded findings list, not raw
  dumps, so they fit a small context;
- **judgment offloaded to rules** — the *senior-engineer reasoning* is
  encoded in the rubric, so a 7B model gets staff-level findings without
  having to reason it out itself.

That last point is the real win for SLMs: they don't need to *be* a
senior reviewer — they call a tool that already is one.

## Quick reference

```bash
# stdio (Cline / LM Studio / Continue): scope the server
MCP_TOOL_TIER=basic <your-mcp-launch-command>

# HTTP adapter (vLLM / Ollama / llama.cpp agent frameworks):
GET /tools?tier=basic            # 26 tools
GET /tools?tier=intermediate     # 59 tools
# then, on demand:
POST /tools/describe_capabilities  {"level": "intermediate"}

# compose a web driver only when needed:
claude mcp add playwright    --scope user -- npx -y @playwright/mcp@latest
claude mcp add dart -- dart mcp-server --force-roots-fallback
```

See [`docs/the-stack.md`](the-stack.md) for the full composition map and
[`docs/web-logged-in-flow.md`](web-logged-in-flow.md) for the web loop.
