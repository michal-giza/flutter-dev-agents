"""One-time WebDriverAgent build helper.

Wraps `xcodebuild build-for-testing` on the Appium WebDriverAgent project.
Required once per device for iOS UI driving; codifies what the user discovered
manually:

    git clone https://github.com/appium/WebDriverAgent.git
    cd WebDriverAgent
    xcodebuild build-for-testing -project WebDriverAgent.xcodeproj \\
      -scheme WebDriverAgentRunner \\
      -destination "platform=iOS,id=<UDID>"

This module is purely subprocess plumbing; the use case + tool layer above
decides when to invoke it and surfaces progress/failure to agents.
"""

from __future__ import annotations

from pathlib import Path

from .process_runner import ProcessResult, ProcessRunner


class WdaSetupCli:
    def __init__(self, runner: ProcessRunner) -> None:
        self._runner = runner

    async def clone(
        self,
        target_dir: Path,
        repo_url: str = "https://github.com/appium/WebDriverAgent.git",
        timeout_s: float = 300.0,
    ) -> ProcessResult:
        return await self._runner.run(
            ["git", "clone", repo_url, str(target_dir)],
            timeout_s=timeout_s,
        )

    async def build_for_testing(
        self,
        wda_dir: Path,
        udid: str,
        scheme: str = "WebDriverAgentRunner",
        timeout_s: float = 1800.0,
    ) -> ProcessResult:
        return await self._runner.run(
            [
                "xcodebuild",
                "build-for-testing",
                "-project",
                "WebDriverAgent.xcodeproj",
                "-scheme",
                scheme,
                "-destination",
                f"platform=iOS,id={udid}",
            ],
            cwd=wda_dir,
            timeout_s=timeout_s,
        )

    async def test_without_building_for_sim(
        self,
        wda_dir: Path,
        udid: str,
        port: int = 8100,
        scheme: str = "WebDriverAgentRunner",
        timeout_s: float = 60.0,
    ) -> ProcessResult:
        """Launch the WDA test runner against an iOS simulator.

        This is the simulator equivalent of `build_for_testing`: it
        spawns `xcodebuild test-without-building` against a sim
        destination, which keeps WDA serving HTTP on `USE_PORT` for
        the lifetime of the xcodebuild process. The caller is expected
        to leave it running in the background — the timeout here
        bounds how long we wait for WDA to come up, NOT the full test
        runner. A reachability poll on the port is the right way to
        confirm WDA is ready.

        Reported in the field May 2026: agents that detected
        `WdaUnreachable` on the iPhone 17 sim had no way to actually
        START WDA from inside the MCP — they'd surface the
        `xcodebuild …` recipe but the user had to run it manually in
        a separate terminal. This tool closes that loop.
        """
        return await self._runner.run(
            [
                "xcodebuild",
                "test-without-building",
                "-project",
                "WebDriverAgent.xcodeproj",
                "-scheme",
                scheme,
                "-destination",
                f"platform=iOS Simulator,id={udid}",
                f"USE_PORT={port}",
            ],
            cwd=wda_dir,
            timeout_s=timeout_s,
        )
