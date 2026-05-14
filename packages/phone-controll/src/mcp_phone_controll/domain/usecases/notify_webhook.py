"""notify_webhook — POST a structured event to an arbitrary HTTP endpoint.

Primary integration target: **n8n** workflows. n8n exposes a "Webhook"
trigger node whose URL accepts POST JSON. Drop one of those URLs into
this tool and any event the agent generates becomes the input to a
no-code automation (Slack post, GitHub issue, Linear ticket, custom
HTTP call, …).

Also works for: Slack incoming webhooks, Discord webhooks, generic
HTTP destinations.

Auth options:
  - Bearer token via `auth_bearer`
  - Custom header via `auth_header_name` + `auth_header_value`
  - Allowlist of permitted hosts via MCP_WEBHOOK_ALLOWLIST env var
    (comma-separated). Empty allowlist (default) → any HTTPS host OR
    localhost is permitted. Set to e.g. `n8n.example.com,hooks.slack.com`
    to lock down.

Failure modes:
  - Non-2xx response → `WebhookFailure` with the upstream status + body.
  - Timeout (default 10s) → `next_action="retry_with_backoff"`.
  - Disallowed host → `next_action="add_to_allowlist"`.

By design this tool does NOT carry an artifact-path field — caller
must serialise paths into the `payload` dict so we never auto-embed
a PNG that would blow Claude's image limit.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlparse

from ..failures import Failure
from ..result import Result, err, ok
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class WebhookFailure(Failure):
    """An HTTP webhook call failed (non-2xx, network, timeout, or auth)."""

    pass


@dataclass(frozen=True, slots=True)
class NotifyWebhookParams:
    url: str
    event: str                           # snake_case event identifier
    payload: dict = field(default_factory=dict)
    auth_bearer: str | None = None
    auth_header_name: str | None = None  # paired with auth_header_value
    auth_header_value: str | None = None
    timeout_s: float = 10.0


@dataclass(frozen=True, slots=True)
class WebhookResult:
    status_code: int
    response_excerpt: str
    duration_ms: int


def _allowed_host(host: str) -> bool:
    """Return True iff the URL host passes the allowlist.

    Empty allowlist (default) permits any HTTPS host plus localhost
    variants. Explicit allowlist forces an exact match against any
    entry.
    """
    raw = os.environ.get("MCP_WEBHOOK_ALLOWLIST", "").strip()
    if raw:
        allow = {h.strip().lower() for h in raw.split(",") if h.strip()}
        return host.lower() in allow
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    return True  # default-open; tighten via env var


class NotifyWebhook(BaseUseCase[NotifyWebhookParams, WebhookResult]):
    """POST a structured event to an HTTP endpoint (n8n, Slack, etc.)."""

    async def execute(
        self, params: NotifyWebhookParams
    ) -> Result[WebhookResult]:
        if not params.url.strip():
            return err(
                WebhookFailure(
                    message="url is required",
                    next_action="fix_arguments",
                )
            )
        parsed = urlparse(params.url)
        if parsed.scheme not in ("http", "https"):
            return err(
                WebhookFailure(
                    message=f"unsupported url scheme: {parsed.scheme!r}",
                    next_action="fix_arguments",
                )
            )
        if parsed.scheme == "http" and parsed.hostname not in {
            "localhost", "127.0.0.1", "::1",
        }:
            return err(
                WebhookFailure(
                    message="plain http is only allowed for localhost",
                    next_action="use_https",
                )
            )
        if not _allowed_host(parsed.hostname or ""):
            return err(
                WebhookFailure(
                    message=f"host {parsed.hostname!r} not in MCP_WEBHOOK_ALLOWLIST",
                    next_action="add_to_allowlist",
                    details={
                        "host": parsed.hostname,
                        "allowlist": os.environ.get("MCP_WEBHOOK_ALLOWLIST", ""),
                    },
                )
            )

        body = {
            "event": params.event,
            "source": "mcp-phone-controll",
            "payload": params.payload,
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "mcp-phone-controll/1.0",
        }
        if params.auth_bearer:
            headers["Authorization"] = f"Bearer {params.auth_bearer}"
        if params.auth_header_name and params.auth_header_value:
            headers[params.auth_header_name] = params.auth_header_value

        # Use stdlib urllib so we don't add httpx to the core deps —
        # this tool must work without `[http]` extras.
        import asyncio
        import time

        loop = asyncio.get_event_loop()
        started = time.monotonic()
        try:
            data = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                params.url, data=data, headers=headers, method="POST"
            )

            def _do_request():
                with urllib.request.urlopen(req, timeout=params.timeout_s) as resp:
                    return resp.status, resp.read(2048).decode("utf-8", errors="replace")

            status, body_text = await loop.run_in_executor(None, _do_request)
        except urllib.error.HTTPError as e:
            body_text = (e.read() or b"").decode("utf-8", errors="replace")[:2048]
            return err(
                WebhookFailure(
                    message=f"upstream returned {e.code}: {body_text[:200]}",
                    next_action="check_webhook_target",
                    details={
                        "status_code": e.code,
                        "response_excerpt": body_text,
                    },
                )
            )
        except (urllib.error.URLError, TimeoutError) as e:
            return err(
                WebhookFailure(
                    message=f"network error: {e}",
                    next_action="retry_with_backoff",
                )
            )
        except Exception as e:
            return err(
                WebhookFailure(
                    message=f"unexpected error: {e}",
                    next_action="check_webhook_target",
                )
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        return ok(
            WebhookResult(
                status_code=status,
                response_excerpt=body_text[:512],
                duration_ms=duration_ms,
            )
        )
