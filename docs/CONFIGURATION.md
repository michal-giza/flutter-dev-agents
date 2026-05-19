# Configuration reference

Every environment variable `mcp-phone-controll` honors, grouped by
when you'd reach for it. Defaults are chosen so most users never
need to set anything beyond `MCP_TOOL_TIER`.

## Tier 1 — the four you might actually want to set

### `MCP_TOOL_TIER` — curate the tool surface
- **Values**: `basic` (26 tools) · `intermediate` (~40) · `expert` / `all` / unset (110)
- **Default**: unset (all 110)
- **Why you set it**: Claude Desktop's UI silently drops tool listings above an undocumented ceiling. Cursor caps at 40. Small local LLMs (4B class) get overwhelmed past ~30 tools. `basic` is the right default for new users.
- **Case-insensitive.** Unknown values fail-open (no filter) so a typo doesn't strip every tool.

### `MCP_WDA_TEAM_ID` — Apple Developer Team ID for iOS device control
- **Values**: 10-character alphanumeric (e.g. `ABCDE12345`)
- **Default**: unset
- **Why you set it**: Building WebDriverAgent for a **physical** iPhone needs `DEVELOPMENT_TEAM` for code signing. Without it, `setup_webdriveragent` fails with `provide_team_id`. Find yours in Xcode → Settings → Accounts → Manage Certificates.

### `MCP_HTTP_API_KEY` — auth for the HTTP adapter
- **Values**: any string (recommend `openssl rand -hex 32`)
- **Default**: unset (no auth)
- **Why you set it**: Required when running the HTTP adapter behind a network boundary (Docker / k8s / shared dev box). Clients send `X-Api-Key: <key>` or `Authorization: Bearer <key>`. Stdio mode ignores it.

### `MCP_LOG_FORMAT` — structured vs human-readable logs
- **Values**: `text` (default) · `json`
- **Why you set it**: `json` pipes one event per line to Datadog / Honeycomb / Loki / your aggregator of choice. Use `text` for local development.

---

## Tier 2 — operational tuning

### `MCP_MAX_IMAGE_DIM` — long-edge cap for screenshots (pixels)
- **Default**: `1600` · **Allowed**: 800 – 1900 (the dispatcher's hard ceiling)
- **Why you'd change it**: lower to save tokens; higher if you're doing visual-diff work and need more fidelity. The pipeline preserves the original at `<path>.orig.png` regardless.

### `MCP_MAX_IMAGE_BYTES_KB` — per-image byte budget
- **Default**: `250` · **Floor**: 50
- **Why you'd change it**: a screenshot that passes the dimension cap can still be hundreds of KB in true-color PNG. Above this threshold the pipeline re-encodes as palette + max zlib. Bigger value = more fidelity, smaller compressed payloads under accumulation.

### `MCP_ANDROID_PREFER_ADB_TAP` — bypass uiautomator2 for taps
- **Values**: `1` / `true` / `yes` / `on` enable
- **Default**: off (auto-enabled for Samsung manufacturer)
- **Why**: Samsung One UI sometimes drops taps through the Accessibility layer. `adb shell input tap` bypasses it. Auto-detected so you rarely set this manually.

### `MCP_AUTO_NARRATE_EVERY` — auto-narration cadence
- **Default**: `0` (off) · **Values**: positive int = every N tool calls
- **Why**: useful for autonomous agent loops — forces a checkpoint summary every N tool calls so the agent can self-correct.

### `MCP_REFLEXION_RETRIES` — auto-retry budget for failing tools
- **Default**: `0` (no auto-retry; the agent decides) · **Values**: 0 – 3
- **Why**: pure-autonomous loops sometimes want one automatic retry on transient failures. Most interactive use should leave this off — the agent's `next_action` field is more informative than blind retry.

### `MCP_STRICT_TOOLS` — refuse-unknown vs warn-unknown
- **Default**: warn · **Values**: `1` = refuse calls to unknown tools with a typed error
- **Why**: tighten for production; loosen for prompting experiments.

### `MCP_ORIG_RETENTION_DAYS` — `.orig.png` cleanup window
- **Default**: `14`
- **Why**: every capped screenshot preserves the full-res original. They accumulate. `prune_originals` deletes anything older than this many days.

### `MCP_QUIET` — suppress startup banner
- **Values**: `1` to silence
- **Why**: cleaner output in CI / piping; default `0` shows version + git-sha on boot for debugging.

---

## Tier 3 — paths & filesystem

### `MCP_ARTIFACTS_DIR` — where sessions are stored
- **Default**: `~/.mcp_phone_controll/sessions/`
- **Why**: redirect to a custom location (shared NFS for a team, /tmp for ephemeral CI, etc.).

### `MCP_TRACE_DB` — session-trace SQLite path
- **Default**: `~/.mcp_phone_controll/trace.db`
- **Why**: rarely set; `session_summary` reads from here.

### `MCP_SKILL_LIBRARY_DB` — Voyager-style skill library
- **Default**: `~/.mcp_phone_controll/skill-library.db`
- **Why**: rarely set; agents that promote successful sequences with `promote_sequence` write here.

### Path-traversal allowlists

Several tools rewrite files on disk and refuse paths outside known-safe roots. Override via colon-separated env vars:

| Tool | Env var | Default roots |
|---|---|---|
| `compress_png` | `MCP_COMPRESS_ALLOWED_ROOTS` | session dir + `/tmp` + `/var/folders` |
| `fetch_artifact` | `MCP_FETCH_ARTIFACT_ALLOWED_ROOTS` | session dir only |
| `install_app` | `MCP_INSTALL_APP_ALLOWED_ROOTS` | cwd + `/tmp` |
| `grep_logs` | `MCP_GREP_LOGS_ALLOWED_ROOTS` | session dir only |

### `MCP_PROJECT_PATHS_ROOTS` — Flutter project path validation
- **Default**: `~/Desktop` + `~/Documents` + `~/Projects` + cwd
- **Why**: where `inspect_project` / `build_app` / `start_debug_session` accept project paths from. Add a colon-separated list to extend.

### `MCP_WEBHOOK_ALLOWLIST` — `notify_webhook` destination filter
- **Default**: empty (all denied)
- **Values**: colon-separated host:port allowlist (e.g. `slack.com:443:discord.com:443`)
- **Why**: the only tool that makes outbound HTTP requests. Off by default so a prompt-injection upstream can't ping arbitrary URLs.

---

## Tier 4 — HTTP adapter

### `MCP_HTTP_HOST` — bind address
- **Default**: `127.0.0.1` (loopback only)
- **Why**: the Docker image overrides to `0.0.0.0` so the container's port mapping works. Don't bind to `0.0.0.0` on a public box without `MCP_HTTP_API_KEY` set.

### `MCP_HTTP_PORT`
- **Default**: `8765` · CLI alternative: `--port`

### `MCP_LLM_BASE_URL` / `MCP_LLM_MODEL` — agent-proxy backend
- **Default**: unset (the `/agent/chat` endpoint is disabled)
- **Why**: when set, the HTTP adapter forwards `/agent/chat` requests to any OpenAI-compat LLM (Ollama, vLLM, LM Studio, OpenAI itself). Lets you build agentic loops from any client that can speak HTTP.

---

## Tier 5 — iOS / WDA specifics

### `MCP_IOS_SIM_WDA_PORT` — WebDriverAgent port on simulator
- **Default**: `8100`
- **Why**: rarely changed; the default matches Appium convention.

### `PYMOBILEDEVICE3_TUNNEL` (upstream var)
- Honored by the underlying `pymobiledevice3` CLI. Lets you pin a tunnel target without passing `--tunnel UDID` every call. Useful for single-device dev boxes.

---

## Tier 6 — observability / RAG / advanced

### `MCP_PROGRESS_LOG`
- **Default**: `0` · **Values**: `1` = emit `tool_dispatch_start` events before long-running tools (build / install / patrol).
- **Why**: pair with `MCP_LOG_FORMAT=json` for live progress in Datadog without waiting for `tool_dispatch_end`.

### `MCP_QDRANT_URL` — vector store for `index_project` / `recall`
- **Default**: `http://localhost:6333` (Qdrant default)
- **Why**: only relevant when you've installed the `[rag]` extra.

### `MCP_RAG_EMBED_MODEL`
- **Default**: `BAAI/bge-small-en-v1.5` (via fastembed)
- **Why**: trade speed for retrieval quality. Heavier models help for code search.

---

## Tier 7 — testing / development

### `MCP_REAL` and `MCP_REAL_DEVICE`
- Both default off. Set to `1` to enable the 5 real-device tests in CI (`tests/integration_real/`). These need an actual phone plugged in.

### `MCP_FUZZ` / `MCP_FUZZ_DEEP`
- Both default off. Enable the Hypothesis dispatcher property test (~90s) / deep-fuzz mode (~10 min).

### `MCP_HTTP_BASE_URL`
- Used by tests that exercise the HTTP adapter. Default points at a hermetic in-process server.

---

## Where these get set

| Surface | How |
|---|---|
| **Claude Desktop** | The `env: { ... }` block in `claude_desktop_config.json` |
| **Claude Code** | `claude mcp add phone-controll -e MCP_TOOL_TIER=basic ...` |
| **Local shell** | `export MCP_TOOL_TIER=basic` in `~/.zshrc` or `~/.bashrc` |
| **Docker** | `-e MCP_TOOL_TIER=basic` on `docker run` |
| **Kubernetes** | Standard env block in the Pod spec |
| **CI** | GitHub Actions `env:` key or repo secrets for sensitive values |

## Verifying a config is active

```
mcp_ping
```

The response includes the active `image_cap_px`, `tool_tier`, `n_tools`, `git_sha`, and `version`. If these don't match what you set, you're talking to a stale subprocess — see [`runbook.md`](runbook.md) §1 for the relaunch playbook.
