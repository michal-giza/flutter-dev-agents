"""Single async-subprocess chokepoint. Every shell-out goes through here."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class ProcessRunner(Protocol):
    async def run(
        self,
        argv: list[str],
        cwd: Path | None = None,
        timeout_s: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessResult: ...

    async def run_to_file(
        self,
        argv: list[str],
        output_path: Path,
        cwd: Path | None = None,
        timeout_s: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessResult: ...

    async def stream(
        self,
        argv: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> "asyncio.subprocess.Process": ...


class AsyncProcessRunner:
    """Concrete asyncio-based runner. Decouples repos from the asyncio API."""

    async def run(
        self,
        argv: list[str],
        cwd: Path | None = None,
        timeout_s: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd) if cwd else None,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            return ProcessResult(
                returncode=-127,
                stdout="",
                stderr=f"binary not found on PATH: {argv[0]} ({e})",
            )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        return ProcessResult(
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
        )

    async def run_to_file(
        self,
        argv: list[str],
        output_path: Path,
        cwd: Path | None = None,
        timeout_s: float | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessResult:
        """Stream binary stdout straight to `output_path` — never decoded.

        Required for any command whose stdout is a binary blob (screencap PNG,
        screenrecord MP4, file pulls). Returns the same ProcessResult as `run`
        except `stdout` is empty (the bytes went to disk).
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("wb") as out_fh:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    cwd=str(cwd) if cwd else None,
                    env=env,
                    stdout=out_fh,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    _, stderr_b = await asyncio.wait_for(
                        proc.communicate(), timeout=timeout_s
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    raise
        except FileNotFoundError as e:
            return ProcessResult(
                returncode=-127,
                stdout="",
                stderr=f"binary not found on PATH: {argv[0]} ({e})",
            )
        return ProcessResult(
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout="",
            stderr=stderr_b.decode("utf-8", errors="replace"),
        )

    async def stream(
        self,
        argv: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd) if cwd else None,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
