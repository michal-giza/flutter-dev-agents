# n8n integration

n8n is a self-hostable workflow automation tool. It speaks plain HTTP
and the `phone-controll` MCP exposes plain HTTP via the
`mcp-phone-controll-http` adapter — so the two integrate without
custom plugins. Two directions:

- **Inbound** — n8n calls our tools. Use n8n's "HTTP Request" node
  pointed at `http://localhost:8765/tools/<name>`.
- **Outbound** — our tools call n8n. Use the new `notify_webhook`
  tool inside the MCP, pointed at an n8n "Webhook" trigger node URL.

Two starter workflow templates ship alongside this doc in
[`integrations/n8n/`](../integrations/n8n/). Drag the `.json` files
into your n8n canvas to import.

## Outbound — `notify_webhook`

The new tool ships in BASIC/expert tier:

```
notify_webhook(
  url="https://n8n.example.com/webhook/abc-123",
  event="release_ready",
  payload={"version": "1.4.0", "apk": "build/app/outputs/.../app-release.apk"},
  auth_bearer="<optional>",
  timeout_s=10,
)
```

### Hosts allowlist (recommended for production)

Set `MCP_WEBHOOK_ALLOWLIST` to a comma-separated list of allowed
hostnames. Empty = open (default; fine for dev). Example:

```bash
export MCP_WEBHOOK_ALLOWLIST="n8n.example.com,hooks.slack.com"
```

`http://` URLs are only permitted to `localhost` / `127.0.0.1` — to
hit a remote n8n instance you must use `https://`.

### Two starter workflows

1. **`green-build-to-slack.json`** — receives a `release_ready`
   webhook, posts to a Slack channel via Incoming Webhook node, and
   logs to a Google Sheet. ~6 nodes, 3-minute import.
2. **`release-batch-to-drive.json`** — receives a `release_screenshots`
   event with paths, uses n8n's "Move Binary Data" + "Google Drive"
   nodes to upload them into a per-version folder. Useful for batched
   store-listing prep.

## Inbound — n8n calls our tools

n8n's HTTP Request node is enough. Point at:

```
POST http://localhost:8765/tools/take_screenshot
Body (JSON): { "label": "smoke" }
```

If `MCP_HTTP_API_KEY` is set, add an `X-Api-Key` header.

### Example: nightly smoke from an n8n cron node

1. **Cron** node — fire at 02:00 daily.
2. **HTTP Request** node — `POST /tools/run_test_plan` with the
   project's smoke YAML path.
3. **IF** node — branch on `body.ok`.
4. **HTTP Request** node (on failure) — `POST /tools/notify_webhook`
   with `event=nightly_smoke_failed`, `payload={"errors": [...]}`.
5. Email node ingesting the previous step's body for the human.

The MCP doesn't care which agent is driving — for a scheduled n8n
workflow, n8n IS the agent.

## Security checklist

- Bind `mcp-phone-controll-http` to `127.0.0.1` (default). Don't
  expose to the LAN/internet without TLS + auth.
- Set `MCP_HTTP_API_KEY` once your workflow is in a shared n8n.
- Set `MCP_WEBHOOK_ALLOWLIST` to restrict outbound notify-webhook
  destinations.
- Audit the `audit_artifact_dimensions` script before any flow that
  sends screenshots to n8n / Slack / Drive — capped 1920px shots
  are fine; full-res `.orig.png` from `release_dir` is what you
  actually want for store listings.

## Related env vars

| Variable | Default | Purpose |
|---|---|---|
| `MCP_HTTP_API_KEY` | (unset) | Required header value if set |
| `MCP_WEBHOOK_ALLOWLIST` | (open) | Comma-separated hostname allowlist |
| `MCP_QUIET` | `0` | `1` silences the boot self-check + log lines |
| `MCP_LOG_FORMAT` | `text` | `json` for Datadog/Honeycomb ingest |

## Troubleshooting

- `WebhookFailure: host '...' not in MCP_WEBHOOK_ALLOWLIST` — add
  the host or unset the allowlist for local dev.
- `WebhookFailure: plain http is only allowed for localhost` —
  switch to https or test against a localhost n8n.
- Slow webhook (>2s) → the new `ProgressLogMiddleware` will emit a
  `level=warn` event in the boot log. Helpful when debugging
  unresponsive integrations.
