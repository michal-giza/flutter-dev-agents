# Integrations

Drop-in connectors that wire `mcp-phone-controll` into the rest of
the modern developer toolchain. Everything here is **shipped today**
— pull the file in, configure a webhook URL or API key, done.

## At a glance

| Integration | Use case | Status |
|---|---|---|
| **GitHub Actions** — `flutter-dev-agents/run-test-plan` | Run a YAML plan against an emulator in CI; fail the job if the verdict isn't green | ✅ shipped |
| **n8n** workflow templates | Fan agent events out to Slack / Linear / Drive / GitHub Issues / Discord | ✅ shipped (3 templates) |
| **MCP Inspector** | Interactive UI to poke at every tool without firing up Claude | ✅ shipped (`make inspect`) |
| **`phone-controll` CLI** | Ops binary for status / locks / artifact audit / session listing | ✅ shipped |
| **Slack** / **Discord** | One-step webhook configuration via `notify_webhook` | ✅ via webhook URL |
| **Generic HTTP** | Any system that accepts an HTTP POST | ✅ via `notify_webhook` |
| **Sentry** / **Datadog** / **Honeycomb** | Structured-log ingestion via `MCP_LOG_FORMAT=json` to stderr | ✅ via log shipper |
| **Prometheus** | `/metrics` endpoint with build info + dispatch gauges | ✅ via HTTP adapter |
| **Kubernetes** | `/health` + `/ready` probes + Docker image | ✅ shipped |
| **Cloudflare Pages** / **Vercel** | Static landing-page docs | optional — separate repo |
| **VS Code extension** | Sidebar for live locks + screenshots + traces | ⏳ planned |
| **JetBrains plugin** | Same UX for IDEA / Android Studio | ⏳ later |
| **Helm chart** | k8s deployment beyond raw manifests | ⏳ planned |
| **n8n custom node** | Typed node per tool (vs the webhook trick) | ⏳ on demand |

## GitHub Actions

The single biggest CI unblock — wraps `run_test_plan` so anyone can
add 5 lines to their workflow and get autonomous mobile testing.

```yaml
- uses: ./../flutter-dev-agents/.github/actions/run-test-plan
  with:
    plan: integration_test/plans/smoke.yaml
```

See `.github/actions/run-test-plan/README.md` for the inline-YAML
form, secrets handling, and Slack-on-failure recipe.

## n8n

Three importable templates under `integrations/n8n/`:
- `green-build-to-slack.json` — release-ready → Slack post + Google Sheet log
- `release-batch-to-drive.json` — release screenshots → Google Drive folder
- `nightly-smoke.json` — cron → `run_test_plan` → notify on fail

Agents POST to n8n via `notify_webhook` — no custom node required.

## MCP Inspector

```bash
make inspect       # uses npx + Node
```

Lists all 109 tools with their schemas; click any tool to invoke
it interactively. Best way to verify a new descriptor before
shipping it to agents.

## `phone-controll` CLI

```bash
phone-controll status      # version, tools, cap, backends
phone-controll locks       # active device locks
phone-controll locks --release <SERIAL>
phone-controll audit       # check oversized PNGs
phone-controll audit --cap # recap them in place
phone-controll tools --tier basic
phone-controll sessions --last 10
phone-controll describe <tool>
```

Installed by default when you `pip install mcp-phone-controll`.

## Slack / Discord (via `notify_webhook`)

```
notify_webhook(
  url="https://hooks.slack.com/services/T01/B02/abc123",
  event="release_ready",
  payload={"version": "1.4.0", "build": 1042}
)
```

Slack and Discord both accept standard webhook POSTs. Same call
shape for Discord — just swap the URL.

## Sentry / Datadog / Honeycomb

Set `MCP_LOG_FORMAT=json` and pipe stderr to your log shipper.
Every dispatch emits `tool_dispatch_start` + `tool_dispatch_end`
records with structured fields (`tool`, `duration_ms`, `ok`,
`error_code`, `next_action`). No SDK to wire in — your existing
agent picks it up.

## Prometheus

Hit `/metrics` on the HTTP adapter. Counters/gauges include:

```
mcp_info{version="0.2.0",git_sha="...",branch="main"} 1
mcp_tools_total 109
mcp_image_cap_px 1600
mcp_image_backends_available 3
mcp_uptime_seconds 1234.5
```

Scrape config:

```yaml
scrape_configs:
  - job_name: mcp-phone-controll
    static_configs:
      - targets: ['mcp:8765']
    metrics_path: /metrics
```

## Kubernetes

```yaml
livenessProbe:
  httpGet: { path: /health, port: 8765 }
readinessProbe:
  httpGet: { path: /ready, port: 8765 }
ports:
  - containerPort: 8765
    name: http
```

Image: `mcp-phone-controll:0.2.0` (multi-stage build, ~280 MB,
non-root user 1000). See `packages/phone-controll/Dockerfile`.

## How to add a new integration

Drop a folder under `integrations/<name>/` with:
- `README.md` — what it does + setup
- Any config files (workflow JSON, helm values, etc.)

Add a row to the table at the top of this file. Open a PR — small
ones get merged fast.

## What's intentionally NOT here

We deliberately don't ship integrations for:
- **CI vendors beyond GitHub Actions** — Jenkins/CircleCI/Buildkite
  all accept shell, so `pip install mcp-phone-controll && phone-controll …`
  covers them. No custom wrapper needed.
- **IDE-specific plugins beyond MCP Inspector** — the MCP protocol
  IS the IDE integration; Cursor / Continue / Claude Code / etc.
  pick us up automatically once configured.
- **Cloud-provider-specific deploys (AWS CDK, Terraform modules)** —
  the Docker image works on any container platform; the operator
  picks the deploy story.

Build these yourself if you need them — the surface is small. Open
a PR if you'd like us to upstream.
