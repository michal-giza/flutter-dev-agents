# Code review — 2026-05-18 (post enterprise sprint)

Fourth pass after the enterprise-readiness sprint (commits `db543f3 →
136184d`, ~6 commits). Focused on what the sprint *itself* shipped —
finding what slipped through during a fast multi-batch push.

## Headline

The sprint achieved its goal (procurement-ready, ops-ready, security-ready),
but seven specific things slipped that any next reviewer would call:

| # | Finding | Severity |
|---|---|---|
| 1 | `FastAPI(version="0.1.0")` not bumped to 0.2.0 | low — visible in /openapi.json |
| 2 | `adapters/__main__.py` at 0% coverage (HTTP entry point) | medium — same gap we just fixed for `mcp_server.py` |
| 3 | Hypothesis fuzz never runs in CI (`MCP_FUZZ=1` opt-in only, no scheduled job) | medium — produces zero CI signal |
| 4 | Docker image is amd64-only — no Apple Silicon builds | medium — local-dev developers can't pull-and-run |
| 5 | `/metrics` exposes only static gauges — no per-tool counters/histograms | low-medium — partial Prometheus value |
| 6 | `pip-audit` runs every push — slow path | low — should be weekly + on-demand |
| 7 | `docs/decisions/` directory exists but isn't linked from anywhere | trivial |

## Diagnosis per finding

### 1. FastAPI version string stale

```python
# packages/phone-controll/src/mcp_phone_controll/adapters/openai_compat.py:52
app = FastAPI(
    title="mcp-phone-controll HTTP adapter",
    version="0.1.0",   # ← should be 0.2.0 to match pyproject.toml
)
```
**Fix**: 1-line edit. Add a `from .. import __version__` and use it.
The next OpenAPI consumer reads this and thinks we're shipping 0.1.0.

### 2. `adapters/__main__.py` is 0% covered

The HTTP server entry point. Same class of gap as `mcp_server.py` was
before we fixed it. A bug in HTTP boot fails silently in CI.

**Fix**: replicate the `test_mcp_server.py` pattern — inject a fake
uvicorn runner, assert the app is built correctly + signal handlers
register.

### 3. Hypothesis fuzz never runs in CI

We added a real fuzz test but gated it behind `MCP_FUZZ=1`. CI doesn't
set the flag, so the test always skips. Zero CI value from the work.

**Fix**: either (a) add a `fuzz` CI job that sets `MCP_FUZZ=1` + runs
weekly via cron, or (b) inline 5-10 examples per tool fast enough that
it runs on every push.

### 4. Docker image is single-arch

`Dockerfile` uses `python:3.11-slim` directly — Docker buildx would
get us amd64+arm64 in one command but the CI workflow doesn't set up
buildx. Apple Silicon developers pulling the image get the slow
emulated amd64 binary.

**Fix**: switch the docker CI job to `docker/setup-qemu-action` +
`docker/setup-buildx-action` + `--platform linux/amd64,linux/arm64`.

### 5. `/metrics` lacks dispatch counters

Currently exposes `mcp_info`, `mcp_tools_total`, `mcp_image_cap_px`,
`mcp_image_backends_available`, `mcp_uptime_seconds`. Missing the
high-value Prometheus signals:
- `mcp_tool_dispatch_total{tool="…",status="ok|err"}` (counter)
- `mcp_tool_dispatch_duration_seconds{tool="…"}` (histogram)
- `mcp_image_cap_failures_total` (counter)
- `mcp_path_guard_rejections_total{tool="…"}` (counter)

These are the metrics real alerting needs.

**Fix**: wire a `prometheus_client.Counter` + `Histogram` from the
dispatcher middleware path. ~2 hours.

### 6. `pip-audit` runs every push

The CI workflow's `security` job runs `pip-audit` on every PR + every
push to main. The CVE database doesn't change minute-to-minute; this
adds ~30 s to every build for no incremental value.

**Fix**: split into two jobs — fast PR sanity (`pip-audit --dry-run`?
just check syntax) + scheduled weekly full scan + on-demand `workflow_dispatch`.

### 7. `docs/decisions/` undiscoverable

We created `docs/decisions/b2-topic-split-deferred.md` as a way to
prevent repeated discussion of a closed decision. But nothing links
to that directory, so the next reviewer won't find it.

**Fix**: README pointer + an index file like `docs/decisions/README.md`
mirroring the ADR setup.

## What was right about the sprint

To be fair to ourselves:

- **Real CVEs found + fixed in the same commit they were detected.**
  urllib3 caught and pinned forward; the meta-discipline is right.
- **The path-guard policy is well-shaped.** Two tiers (strict +
  permissive) + env-extensible — handles real dev paths without
  letting an attacker overwrite `/etc`.
- **`/ready` returns reasons, not just a status code.** Operations
  teams can see WHY readiness flipped (no backend / no tools), not
  just that it did.
- **The Hypothesis fuzz infra is good** — the gap is in *running* it,
  not in *writing* it. Easy fix.
- **Docker image runs as non-root.** ADR-0006 specifically called
  this out as a residual risk; we closed it.

## Numbers

```
477 hermetic tests, 6 skipped (5 real-device opt-in + 1 fuzz opt-in)
71% statement coverage (unchanged — new tests covered new code)
109 tools
0 ruff errors
0 pip-audit findings (after urllib3 pin + py ignore)
tool catalogue current
contract snapshot includes outputSchema for 6 tools
docker image builds + boots + responds 200 on /health
```

## Priority for the next batch

By impact-per-hour:

1. **GitHub Action wrapper** (~1 h) — the single biggest developer-
   adoption unblock. Wraps `run_test_plan` so users add 5 lines to
   their `.github/workflows/` and get autonomous mobile testing in
   CI. Closes the most-asked-for integration gap.
2. **n8n workflow templates** (~30 min) — JSON files users can
   `Import workflow` into n8n to wire phone-controll → Slack /
   Linear / GitHub Issues / etc. Already half-built (we have
   `notify_webhook`).
3. **MCP Inspector launch config + Makefile** (~20 min) — `make
   inspect` opens the Inspector UI pointed at our server for
   interactive debugging.
4. **`phone-controll` CLI** (~1 h) — `phone-controll status`,
   `phone-controll locks`, `phone-controll audit`. Ops convenience;
   ties the runbook commands into one binary.
5. **Bump FastAPI version + add adapters/__main__ tests** (~30 min)
   — close findings #1 + #2 above.
6. **Docker buildx multi-arch + scheduled pip-audit** (~30 min) —
   close findings #4 + #6.
7. **Prometheus dispatch counters/histograms** (~2 h) — close
   finding #5. Higher value but bigger surface.

Tier 2 (defer):
- VS Code extension (sidebar with live device locks + traces) — 2 days
- Helm chart for k8s
- Skills sharing registry
- Sentry/Datadog/Honeycomb integrations beyond raw JSON logs
- Postman collection
