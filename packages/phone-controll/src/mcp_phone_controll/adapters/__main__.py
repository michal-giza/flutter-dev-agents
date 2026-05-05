"""Entrypoint: `mcp-phone-controll-http` (or `python -m mcp_phone_controll.adapters`).

Boots the FastAPI HTTP adapter on a configurable port. Defaults to localhost:8765.
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="mcp-phone-controll HTTP adapter")
    parser.add_argument(
        "--host", default=os.environ.get("MCP_HTTP_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("MCP_HTTP_PORT", "8765"))
    )
    parser.add_argument(
        "--no-agent-proxy",
        action="store_true",
        help="Disable the /agent/chat proxy endpoint",
    )
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "uvicorn is not installed. Install with: uv pip install -e \".[http]\""
        ) from None

    from .openai_compat import create_app

    app = create_app(allow_agent_proxy=not args.no_agent_proxy)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
