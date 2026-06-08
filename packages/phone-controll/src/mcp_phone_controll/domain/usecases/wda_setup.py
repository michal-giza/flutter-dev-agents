"""SetupWebDriverAgent — one-time per-device WDA build.

Codifies the manual recipe the user discovered for tap-driven iOS testing:

    git clone https://github.com/appium/WebDriverAgent.git
    xcodebuild build-for-testing -project WebDriverAgent.xcodeproj \\
      -scheme WebDriverAgentRunner \\
      -destination "platform=iOS,id=<UDID>"

This use case is long-running (minutes) — `xcodebuild build-for-testing`
compiles the runner and signs it for the target device. The agent should
expect to wait, not poll prematurely.

Sibling use case `StartWdaOnSimulator` (below) handles the SIMULATOR
side: kicks off `xcodebuild test-without-building` against a sim
destination, polls the WDA port for reachability, returns when WDA
is up. Closes the loop opened by K1: K1 detects WDA-not-running with
`WdaUnreachable(next_action="start_wda_on_simulator")`; this tool is
what the agent calls to satisfy that next_action.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..failures import (
    FlutterCliFailure,
    InvalidArgumentFailure,
)
from ..result import Result, err, ok
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class SetupWebDriverAgentParams:
    udid: str
    wda_dir: Path | None = None        # Existing checkout. If None, clone first.
    repo_url: str = "https://github.com/appium/WebDriverAgent.git"
    scheme: str = "WebDriverAgentRunner"
    skip_if_built: bool = True         # Honor a previous successful build's marker file.
    # Apple Developer Team ID (10-char alphanumeric, e.g. "ABCDE12345").
    # Required for physical-device builds — without it xcodebuild fails
    # with "Signing for 'WebDriverAgentRunner' requires a development
    # team". Fetch via `xcrun altool --list-providers` or from Xcode
    # → Account → Manage Certificates. Falls back to env var
    # MCP_WDA_TEAM_ID if not provided here. Ignored for simulators.
    team_id: str | None = None
    # Whether the target udid is an iOS Simulator. None → auto-detect via
    # `xcrun simctl list devices`. Simulators build with the simulator
    # destination + signing disabled (no team needed).
    is_simulator: bool | None = None


@dataclass(frozen=True, slots=True)
class WdaBuildResult:
    udid: str
    wda_dir: Path
    cloned: bool
    xcodebuild_stdout: str
    xcodebuild_stderr: str
    skipped_existing: bool = False


# Marker file written next to a successful build so we can short-circuit
# subsequent calls. Includes the udid so multi-device setups don't collide.
_BUILD_MARKER = ".mcp-phone-controll-built"


class SetupWebDriverAgent(BaseUseCase[SetupWebDriverAgentParams, WdaBuildResult]):
    """Clones (if needed) and builds WebDriverAgent for one iOS device."""

    def __init__(self, wda_setup_cli) -> None:
        self._cli = wda_setup_cli

    async def execute(
        self, params: SetupWebDriverAgentParams
    ) -> Result[WdaBuildResult]:
        if not params.udid:
            return err(
                InvalidArgumentFailure(
                    message="udid is required",
                    next_action="fix_arguments",
                )
            )

        wda_dir = params.wda_dir
        cloned = False
        if wda_dir is None:
            wda_dir = (
                Path.home() / ".mcp_phone_controll" / "WebDriverAgent"
            )
            if not wda_dir.exists():
                clone_res = await self._cli.clone(wda_dir, repo_url=params.repo_url)
                if not clone_res.ok:
                    return err(
                        FlutterCliFailure(
                            message="git clone WebDriverAgent failed",
                            details={"stderr": clone_res.stderr},
                            next_action="check_network_or_git",
                        )
                    )
                cloned = True
        elif not wda_dir.exists():
            return err(
                InvalidArgumentFailure(
                    message=f"wda_dir does not exist: {wda_dir}",
                    next_action="fix_arguments",
                )
            )

        # Short-circuit if a successful build for this UDID is already on disk.
        marker = wda_dir / _BUILD_MARKER
        if params.skip_if_built and marker.exists():
            try:
                if params.udid in marker.read_text(encoding="utf-8").splitlines():
                    return ok(
                        WdaBuildResult(
                            udid=params.udid,
                            wda_dir=wda_dir,
                            cloned=cloned,
                            xcodebuild_stdout="",
                            xcodebuild_stderr="",
                            skipped_existing=True,
                        )
                    )
            except OSError:
                pass

        # Resolve device-class: simulators build with the simulator
        # destination + no signing; devices need a team. Auto-detect when
        # the caller didn't say (so "it just works" like Android/adb).
        is_simulator = params.is_simulator
        if is_simulator is None:
            is_simulator = False
            with contextlib.suppress(Exception):
                is_simulator = bool(
                    await self._cli.detect_is_simulator(params.udid)
                )

        # team_id resolution (device only): explicit param wins, env
        # fallback for ops who'd rather set MCP_WDA_TEAM_ID once. For
        # simulators we never sign, so team_id stays None.
        import os as _os
        team_id = None
        if not is_simulator:
            team_id = params.team_id or _os.environ.get(
                "MCP_WDA_TEAM_ID", ""
            ).strip() or None

        build_res = await self._cli.build_for_testing(
            wda_dir=wda_dir,
            udid=params.udid,
            scheme=params.scheme,
            team_id=team_id,
            is_simulator=is_simulator,
        )
        if not build_res.ok:
            stderr_tail = build_res.stderr[-2000:] if build_res.stderr else ""
            # Detect the most common failure mode and surface the
            # actionable next step instead of a generic "check_xcode_signing".
            signing_hint = not is_simulator and (
                "requires a development team" in stderr_tail
                or "DEVELOPMENT_TEAM" in stderr_tail
                or "Code signing is required" in stderr_tail
            )
            return err(
                FlutterCliFailure(
                    message=(
                        "xcodebuild build-for-testing failed: signing requires "
                        "DEVELOPMENT_TEAM — pass team_id (10-char Apple Team "
                        "ID, e.g. 'ABCDE12345') or set MCP_WDA_TEAM_ID env var"
                        if signing_hint
                        else "xcodebuild build-for-testing failed"
                    ),
                    details={
                        "stderr_tail": stderr_tail,
                        "stdout_tail": build_res.stdout[-2000:] if build_res.stdout else "",
                        "udid": params.udid,
                        "wda_dir": str(wda_dir),
                        "team_id_passed": bool(team_id),
                    },
                    next_action=(
                        "provide_team_id" if signing_hint else "check_xcode_signing"
                    ),
                )
            )
        # Record success so subsequent calls can short-circuit.
        try:
            existing = (
                marker.read_text(encoding="utf-8") if marker.exists() else ""
            )
            udids = set(existing.splitlines()) | {params.udid}
            marker.write_text("\n".join(sorted(u for u in udids if u)) + "\n", encoding="utf-8")
        except OSError:
            pass

        return ok(
            WdaBuildResult(
                udid=params.udid,
                wda_dir=wda_dir,
                cloned=cloned,
                xcodebuild_stdout=build_res.stdout[-2000:] if build_res.stdout else "",
                xcodebuild_stderr=build_res.stderr[-2000:] if build_res.stderr else "",
            )
        )


# ---- start_wda_on_simulator -------------------------------------------


@dataclass(frozen=True, slots=True)
class StartWdaOnSimulatorParams:
    udid: str
    port: int = 8100
    wda_dir: Path | None = None  # defaults to ~/.mcp_phone_controll/WebDriverAgent
    scheme: str = "WebDriverAgentRunner"
    ready_timeout_s: float = 60.0  # how long to wait for the WDA port


@dataclass(frozen=True, slots=True)
class StartWdaOnSimulatorResult:
    udid: str
    port: int
    pid: int
    ready: bool
    elapsed_s: float
    wda_dir: str


class StartWdaOnSimulator(BaseUseCase[
    StartWdaOnSimulatorParams, StartWdaOnSimulatorResult
]):
    """Spawn `xcodebuild test-without-building` against a sim, wait for
    WDA to listen on `port`, return.

    The xcodebuild process is detached: it keeps running after this use
    case returns. Killing it cleanly is left to the agent / lifecycle
    layer — typically `pkill -f "test-without-building.*UDID"` or just
    quitting the simulator.

    On success: WDA is reachable on `127.0.0.1:port`, the K1 WDA factory
    will route to it, every subsequent tap/swipe just works.

    On timeout: kills the spawned xcodebuild, returns a structured
    failure with `next_action="setup_webdriveragent"` if the build
    isn't on disk yet.
    """

    def __init__(self, wda_setup_cli) -> None:
        # We don't actually use the CLI wrapper here — we spawn directly
        # so we can detach — but accepting it keeps wiring symmetric
        # with `SetupWebDriverAgent` for testability + DI.
        self._cli = wda_setup_cli

    async def execute(
        self, params: StartWdaOnSimulatorParams
    ) -> Result[StartWdaOnSimulatorResult]:
        if not params.udid:
            return err(
                InvalidArgumentFailure(
                    message="udid is required",
                    next_action="fix_arguments",
                )
            )

        wda_dir = params.wda_dir or (
            Path.home() / ".mcp_phone_controll" / "WebDriverAgent"
        )
        if not wda_dir.exists():
            return err(
                FlutterCliFailure(
                    message=(
                        f"WebDriverAgent not found at {wda_dir} — run "
                        "setup_webdriveragent first to clone + build it."
                    ),
                    next_action="setup_webdriveragent",
                    details={"udid": params.udid, "wda_dir": str(wda_dir)},
                )
            )
        proj = wda_dir / "WebDriverAgent.xcodeproj"
        if not proj.exists():
            return err(
                FlutterCliFailure(
                    message=f"missing {proj} — wda_dir doesn't look like a WDA checkout",
                    next_action="setup_webdriveragent",
                    details={"wda_dir": str(wda_dir)},
                )
            )

        # Fast path: WDA already listening (e.g. user started it
        # manually in another terminal). Return success without
        # spawning anything.
        if _port_open("127.0.0.1", params.port):
            return ok(
                StartWdaOnSimulatorResult(
                    udid=params.udid,
                    port=params.port,
                    pid=0,
                    ready=True,
                    elapsed_s=0.0,
                    wda_dir=str(wda_dir),
                )
            )

        # Spawn xcodebuild detached. We don't await — the process should
        # outlive this use case. stdout/stderr → DEVNULL so it doesn't
        # fill our pipe buffers and block.
        loop = asyncio.get_event_loop()
        started = loop.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                "xcodebuild",
                "test-without-building",
                "-project",
                "WebDriverAgent.xcodeproj",
                "-scheme",
                params.scheme,
                "-destination",
                f"platform=iOS Simulator,id={params.udid}",
                f"USE_PORT={params.port}",
                cwd=str(wda_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # detach from our process group
            )
        except FileNotFoundError:
            return err(
                FlutterCliFailure(
                    message="xcodebuild not found on PATH",
                    next_action="install_xcode_command_line_tools",
                    details={"hint": "xcode-select --install"},
                )
            )

        # Poll the port until ready or timeout.
        deadline = started + params.ready_timeout_s
        ready = False
        while loop.time() < deadline:
            if _port_open("127.0.0.1", params.port):
                ready = True
                break
            await asyncio.sleep(0.5)
            # If xcodebuild itself died (e.g. build error), bail early
            # with whatever it told us.
            if proc.returncode is not None:
                return err(
                    FlutterCliFailure(
                        message=(
                            "xcodebuild test-without-building exited before "
                            f"WDA came up (returncode={proc.returncode}). Most "
                            "likely the simulator hasn't been built yet — run "
                            "setup_webdriveragent first (it now builds for the "
                            "simulator destination, no signing needed)."
                        ),
                        next_action="setup_webdriveragent",
                        details={
                            "udid": params.udid,
                            "wda_dir": str(wda_dir),
                            "hint": (
                                "build once: `xcodebuild build-for-testing "
                                "-project WebDriverAgent.xcodeproj -scheme "
                                f"{params.scheme} -destination 'platform=iOS "
                                f"Simulator,id={params.udid}' "
                                "CODE_SIGNING_ALLOWED=NO`, then re-run "
                                "start_wda_on_simulator"
                            ),
                        },
                    )
                )

        elapsed = loop.time() - started

        if not ready:
            # Timeout — try to kill the xcodebuild we spawned.
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
            return err(
                FlutterCliFailure(
                    message=(
                        f"WDA didn't come up on 127.0.0.1:{params.port} within "
                        f"{params.ready_timeout_s:.0f}s"
                    ),
                    next_action="check_xcode_signing",
                    details={
                        "udid": params.udid,
                        "wda_dir": str(wda_dir),
                        "elapsed_s": round(elapsed, 1),
                    },
                )
            )

        return ok(
            StartWdaOnSimulatorResult(
                udid=params.udid,
                port=params.port,
                pid=proc.pid,
                ready=True,
                elapsed_s=round(elapsed, 2),
                wda_dir=str(wda_dir),
            )
        )


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
