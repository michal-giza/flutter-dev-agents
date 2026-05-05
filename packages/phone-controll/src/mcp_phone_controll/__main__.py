"""Entrypoint: `python -m mcp_phone_controll`."""

from __future__ import annotations

import asyncio

from .container import build_runtime
from .presentation.mcp_server import serve_stdio


async def _run() -> None:
    _, dispatcher = build_runtime()
    await serve_stdio(dispatcher)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
