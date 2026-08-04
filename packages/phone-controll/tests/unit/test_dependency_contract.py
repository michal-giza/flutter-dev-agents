"""Guards on the dependency contract that a fresh `pip install` resolves.

These exist because two classes of bug are invisible to every other test in
this suite — they only bite a NEW user on a clean machine:

  1. An unbounded major. `mcp>=1.2.0` happily resolved mcp 2.0.0, which
     REMOVED the low-level decorator API (`@server.list_tools()` /
     `@server.call_tool()`) that presentation/mcp_server.py is built on, in
     favour of constructor callbacks. Our own CI never saw it because the
     venv had 1.x pinned by the lockfile.
  2. A security floor that drifts below a known-vulnerable release.

Both are properties of pyproject.toml, so we assert on pyproject.toml.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _deps() -> dict[str, str]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    groups = [data["project"]["dependencies"]]
    for extra in (data["project"].get("optional-dependencies") or {}).values():
        groups.append(extra)
    for group in groups:
        for spec in group:
            name = (
                spec.split(">=")[0].split("==")[0].split("<")[0].split("[")[0].strip()
            )
            out[name.lower()] = spec
    return out


def test_mcp_is_capped_below_2():
    """mcp 2.0.0 removed the decorator API mcp_server.py uses. Without a
    ceiling, `pip install mcp-phone-controll` gives a server that
    AttributeErrors at boot."""
    spec = _deps()["mcp"]
    assert "<2" in spec.replace(" ", ""), (
        f"mcp must stay capped below 2.0.0 until presentation/mcp_server.py "
        f"migrates from @server.list_tools()/@server.call_tool() to the 2.x "
        f"Server(on_list_tools=..., on_call_tool=...) callbacks. Got: {spec!r}"
    )


@pytest.mark.parametrize(
    ("pkg", "floor"),
    [
        # 8 advisories against 12.2.0, several heap OOB writes reachable
        # straight from image data. We push screenshots through PIL.
        ("pillow", (12, 3, 0)),
        # 1.27.0: unverified principal on HTTP session requests, cross-client
        # task read/cancel, no Host/Origin validation on the WS transport.
        ("mcp", (1, 29)),
        # SSRF/NTLM via UNC paths in StaticFiles; getattr method dispatch;
        # form() size limits ignored.
        ("starlette", (1, 3, 1)),
        # CVE-2026-44431 / CVE-2026-44432.
        ("urllib3", (2, 7, 0)),
    ],
)
def test_security_floor_holds(pkg: str, floor: tuple[int, ...]):
    spec = _deps()[pkg]
    assert ">=" in spec, f"{pkg} needs an explicit lower bound; got {spec!r}"
    raw = spec.split(">=")[1].split(",")[0].strip()
    got = tuple(int(p) for p in raw.split(".") if p.isdigit())
    assert got >= floor, (
        f"{pkg} floor {raw} is below the security floor "
        f"{'.'.join(str(p) for p in floor)} — a fresh install would resolve a "
        f"known-vulnerable release."
    )


def test_installed_mcp_still_exposes_the_decorator_api():
    """Fails loudly if the environment is on an mcp that dropped the API we
    build on — the exact break the cap prevents."""
    mcp_server = pytest.importorskip("mcp.server")
    server_cls = mcp_server.Server
    for attr in ("list_tools", "call_tool"):
        assert hasattr(server_cls, attr), (
            f"installed mcp SDK has no Server.{attr} — this is the mcp 2.x "
            f"callback API. presentation/mcp_server.py cannot run on it."
        )
