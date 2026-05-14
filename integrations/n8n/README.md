# n8n workflow templates

Drag-import-ready n8n workflow JSON files. See
[`docs/n8n-integration.md`](../../docs/n8n-integration.md) for setup.

| File | Trigger | Effect |
|---|---|---|
| `green-build-to-slack.json` | Webhook (event=`release_ready`) | Posts to Slack + logs to Google Sheets |
| `release-batch-to-drive.json` | Webhook (event=`release_screenshots`) | Uploads each screenshot to a Drive folder |
| `nightly-smoke.json` | Cron (02:00 daily) | Calls `run_test_plan` then `notify_webhook` on failure |

## Import

In n8n: **Workflows → Import from File** → pick the JSON.
Update the credentials (Slack/Google) and the MCP host URL.
