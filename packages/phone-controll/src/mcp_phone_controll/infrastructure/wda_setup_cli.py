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
