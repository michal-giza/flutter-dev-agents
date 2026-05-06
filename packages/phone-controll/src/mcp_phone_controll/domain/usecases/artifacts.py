"""Artifact session use cases."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ..entities import Session
from ..failures import FilesystemFailure
from ..repositories import ArtifactRepository
from ..result import Err, Result, err, ok
from .base import BaseUseCase, NoParams


@dataclass(frozen=True, slots=True)
class NewSessionParams:
    label: str | None = None


class NewSession(BaseUseCase[NewSessionParams, Session]):
    def __init__(self, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def execute(self, params: NewSessionParams) -> Result[Session]:
        return await self._artifacts.new_session(params.label)


class GetArtifactsDir(BaseUseCase[NoParams, Path]):
    def __init__(self, artifacts: ArtifactRepository) -> None:
        self._artifacts = artifacts

    async def execute(self, params: NoParams) -> Result[Path]:
        session_res = await self._artifacts.current_session()
        if isinstance(session_res, Err):
            return session_res
        return ok(session_res.value.root)


# Suffixes that should always come back as metadata-only (binary data is not
# useful in a chat envelope; the agent already has the path).
_BINARY_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".webm", ".bin"}
)


@dataclass(frozen=True, slots=True)
class FetchArtifactParams:
    path: Path
    max_bytes: int = 64_000   # ~16k tokens at avg 4 bytes/token; safe for 4B
    encoding: str = "utf-8"


@dataclass(frozen=True, slots=True)
class FetchArtifactResult:
    path: Path
    size_bytes: int
    sha256: str
    is_binary: bool
    truncated: bool
    content: str | None     # text content if not binary and within max_bytes


class FetchArtifact(BaseUseCase[FetchArtifactParams, FetchArtifactResult]):
    """Read a previously emitted artifact from disk by path.

    The dispatcher truncates large outputs and adds
    `next_action: "fetch_full_artifact_if_needed"` — `fetch_artifact` is the
    follow-up the agent uses to grab the full text content (logs, JUnit XML,
    UI dumps) when truncation matters. Binary artifacts (PNG, MP4) come back
    as metadata only — those are not useful inline.
    """

    async def execute(
        self, params: FetchArtifactParams
    ) -> Result[FetchArtifactResult]:
        path = Path(params.path).expanduser()
        if not path.exists():
            return err(
                FilesystemFailure(
                    message=f"artifact not found: {path}",
                    next_action="check_path",
                    details={"path": str(path)},
                )
            )
        if not path.is_file():
            return err(
                FilesystemFailure(
                    message=f"artifact is not a regular file: {path}",
                    next_action="check_path",
                )
            )
        size = path.stat().st_size
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        is_binary = path.suffix.lower() in _BINARY_SUFFIXES
        if is_binary:
            return ok(
                FetchArtifactResult(
                    path=path,
                    size_bytes=size,
                    sha256=digest.hexdigest(),
                    is_binary=True,
                    truncated=False,
                    content=None,
                )
            )
        try:
            with path.open("rb") as fh:
                raw = fh.read(params.max_bytes + 1)
            truncated = len(raw) > params.max_bytes
            data = raw[: params.max_bytes].decode(
                params.encoding, errors="replace"
            )
        except OSError as exc:
            return err(
                FilesystemFailure(
                    message=f"failed to read artifact: {exc}",
                    next_action="check_permissions",
                )
            )
        return ok(
            FetchArtifactResult(
                path=path,
                size_bytes=size,
                sha256=digest.hexdigest(),
                is_binary=False,
                truncated=truncated,
                content=data,
            )
        )
