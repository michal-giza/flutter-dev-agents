"""`phone-controll` — operations CLI.

The MCP server is what agents talk to. This CLI is what HUMANS talk
to for ops tasks: check what's running, view active device locks,
re-cap stray artifacts, force-release a stuck lock. Stdlib argparse;
pretty output via plain Python (no `rich` dep) so it runs in any
venv.

Subcommands map 1:1 to the runbook's diagnostic recipes so the
incident-response loop is short.

Usage:
    phone-controll status                  # version, tools, backends, cap
    phone-controll locks                   # active device locks
    phone-controll locks --release <UDID>  # force-release a lock
    phone-controll audit [--cap]           # check/recap session artifacts
    phone-controll tools [--tier basic]    # list tools at a tier
    phone-controll sessions [--last N]     # recent session ids
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from . import __version__


def _print_kv(rows: list[tuple[str, str]]) -> None:
    if not rows:
        return
    width = max(len(k) for k, _ in rows)
    for k, v in rows:
        print(f"  {k:<{width}}  {v}")


def cmd_status(args) -> int:
    """Show the running MCP's identity + readiness."""
    from .data.image_capping import _max_dim, available_backends
    from .version_info import version_info

    info = version_info()
    backends = available_backends()
    print(f"phone-controll {__version__}")
    _print_kv([
        ("git_sha", str(info["git_sha"]) + ("*" if info["git_dirty"] else "")),
        ("git_branch", str(info["git_branch"])),
        ("python", str(info["python_version"])),
        ("started_at", str(info["started_at"])),
        ("uptime_s", str(info["uptime_s"])),
        ("image_cap_px", str(_max_dim())),
        ("image_backends", ",".join(backends) or "NONE"),
    ])
    if not backends:
        print()
        print("  ⚠  no image-cap backends — screenshots will fail the 2000px gate.")
        print("     fix: pip install pillow")
        return 1
    return 0


def cmd_locks(args) -> int:
    """List active device locks. With --release, force-release one."""
    from .container import build_runtime

    async def _run():
        _, dispatcher = build_runtime()
        if args.release:
            res = await dispatcher.dispatch(
                "force_release_lock", {"serial": args.release}
            )
            if res["ok"]:
                print(f"released lock on {args.release}")
                return 0
            print(f"failed: {res['error'].get('message')}", file=sys.stderr)
            return 1

        res = await dispatcher.dispatch("list_locks", {})
        locks = res.get("data") or []
        if not locks:
            print("no active locks.")
            return 0
        print(f"{len(locks)} active lock(s):")
        for lock in locks:
            print()
            _print_kv([
                ("serial", lock["serial"]),
                ("session_id", lock["session_id"]),
                ("pid", str(lock["pid"])),
                ("started_at", lock["started_at"]),
                ("note", lock.get("note") or "—"),
            ])
        return 0

    return asyncio.run(_run())


def cmd_audit(args) -> int:
    """Walk the artifacts dir; report oversized + heavy PNGs."""
    from .scripts.audit_artifact_dimensions import main as audit_main

    sys_argv_backup = sys.argv[:]
    sys.argv = ["audit_artifact_dimensions", "--root", str(args.root)]
    if args.cap:
        sys.argv.append("--cap")
    sys.argv.extend(["--max-dim", str(args.max_dim)])
    sys.argv.extend(["--max-bytes-kb", str(args.max_bytes_kb)])
    try:
        return audit_main()
    finally:
        sys.argv = sys_argv_backup


def cmd_tools(args) -> int:
    """List tools registered at a given tier."""
    from .container import build_runtime
    from .domain.tool_levels import BASIC_TOOLS, INTERMEDIATE_TOOLS

    _, dispatcher = build_runtime()
    names = sorted(d.name for d in dispatcher.descriptors)
    if args.tier == "basic":
        names = [n for n in names if n in BASIC_TOOLS]
    elif args.tier == "intermediate":
        names = [n for n in names if n in INTERMEDIATE_TOOLS]
    print(f"{len(names)} tool(s){' at tier ' + args.tier if args.tier != 'all' else ''}:")
    for n in names:
        print(f"  {n}")
    return 0


def cmd_sessions(args) -> int:
    """List recent session directories on disk."""
    # Explicit empty-string check — Path("") is PosixPath(".") which
    # evaluates truthy, so an `or` chain would never reach the
    # fallback default. The bug surfaced in a smoke run that started
    # listing CWD entries.
    env_dir = os.environ.get("MCP_ARTIFACTS_DIR", "").strip()
    root = (
        Path(env_dir).expanduser()
        if env_dir
        else Path.home() / ".mcp_phone_controll" / "sessions"
    )
    if not root.is_dir():
        print(f"no sessions dir at {root}", file=sys.stderr)
        return 1
    sessions = sorted(
        (d for d in root.iterdir() if d.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[: args.last]
    if not sessions:
        print(f"no sessions in {root}.")
        return 0
    print(f"{len(sessions)} most-recent session(s) under {root}:")
    for s in sessions:
        png_count = len(list(s.glob("*.png")))
        total_kb = sum(p.stat().st_size for p in s.iterdir() if p.is_file()) // 1024
        print(f"  {s.name}   {png_count} png  {total_kb} KB total")
    return 0


def cmd_describe(args) -> int:
    """Print one tool's full descriptor as JSON."""
    from .container import build_runtime

    _, dispatcher = build_runtime()
    desc = next(
        (d for d in dispatcher.descriptors if d.name == args.tool), None
    )
    if desc is None:
        print(f"unknown tool: {args.tool}", file=sys.stderr)
        return 1
    out = {
        "name": desc.name,
        "description": desc.description,
        "input_schema": desc.input_schema,
    }
    if desc.output_schema is not None:
        out["output_schema"] = desc.output_schema
    annotations = {}
    if desc.read_only is not None:
        annotations["readOnlyHint"] = desc.read_only
    if desc.destructive is not None:
        annotations["destructiveHint"] = desc.destructive
    if desc.idempotent is not None:
        annotations["idempotentHint"] = desc.idempotent
    if desc.open_world is not None:
        annotations["openWorldHint"] = desc.open_world
    if annotations:
        out["annotations"] = annotations
    print(json.dumps(out, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phone-controll",
        description="Operations CLI for mcp-phone-controll. See `phone-controll <cmd> --help`.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="Show version, tools, backends, cap")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("locks", help="List or release device locks")
    p.add_argument(
        "--release", metavar="SERIAL", help="Force-release the lock on SERIAL"
    )
    p.set_defaults(func=cmd_locks)

    p = sub.add_parser("audit", help="Check/recap artifact dimensions + size")
    p.add_argument(
        "--root", type=Path,
        default=Path.home() / ".mcp_phone_controll" / "sessions",
    )
    p.add_argument("--cap", action="store_true", help="Actually rewrite oversized PNGs")
    p.add_argument("--max-dim", type=int, default=1600)
    p.add_argument("--max-bytes-kb", type=int, default=250)
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("tools", help="List registered tools (filter by tier)")
    p.add_argument(
        "--tier", choices=["basic", "intermediate", "all"], default="all"
    )
    p.set_defaults(func=cmd_tools)

    p = sub.add_parser("sessions", help="List recent session directories")
    p.add_argument("--last", type=int, default=10)
    p.set_defaults(func=cmd_sessions)

    p = sub.add_parser("describe", help="Print one tool's full descriptor")
    p.add_argument("tool", help="Tool name")
    p.set_defaults(func=cmd_describe)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
