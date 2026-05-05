"""SetupWebDriverAgent — one-time per-device WDA build.

Codifies the manual recipe the user discovered for tap-driven iOS testing:

    git clone https://github.com/appium/WebDriverAgent.git
    xcodebuild build-for-testing -project WebDriverAgent.xcodeproj \\
      -scheme WebDriverAgentRunner \\
      -destination "platform=iOS,id=<UDID>"

This use case is long-running (minutes) — `xcodebuild build-for-testing`
compiles the runner and signs it for the target device. The agent should
expect to wait, not poll prematurely.
"""

from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class WdaBuildResult:
    udid: str
    wda_dir: Path
    cloned: bool
    xcodebuild_stdout: str
    xcodebuild_stderr: str


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

        build_res = await self._cli.build_for_testing(
            wda_dir=wda_dir, udid=params.udid, scheme=params.scheme
        )
        if not build_res.ok:
            return err(
                FlutterCliFailure(
                    message="xcodebuild build-for-testing failed",
                    details={
                        "stderr_tail": build_res.stderr[-2000:] if build_res.stderr else "",
                        "stdout_tail": build_res.stdout[-2000:] if build_res.stdout else "",
                        "udid": params.udid,
                        "wda_dir": str(wda_dir),
                    },
                    next_action="check_xcode_signing",
                )
            )
        return ok(
            WdaBuildResult(
                udid=params.udid,
                wda_dir=wda_dir,
                cloned=cloned,
                xcodebuild_stdout=build_res.stdout[-2000:] if build_res.stdout else "",
                xcodebuild_stderr=build_res.stderr[-2000:] if build_res.stderr else "",
            )
        )
