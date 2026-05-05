"""ArtifactRepository implementation writing under ~/.mcp_phone_controll/sessions/."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime
from pathlib import Path

from ...domain.entities import Artifact, Session
from ...domain.failures import FilesystemFailure
from ...domain.repositories import ArtifactRepository
from ...domain.result import Result, err, ok


def _slugify(label: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", label).strip("-").lower() or "untitled"


class FilesystemArtifactRepository(ArtifactRepository):
    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = asyncio.Lock()
        self._current: Session | None = None
        self._registered: list[Artifact] = []

    async def new_session(self, label: str | None = None) -> Result[Session]:
        async with self._lock:
            now = datetime.now()
            session_id = now.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
            session_dir = self._root / session_id
            try:
                session_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                return err(FilesystemFailure(message=f"failed to create session dir: {e}"))
            session = Session(id=session_id, root=session_dir, started_at=now, label=label)
            self._current = session
            self._registered = []
            return ok(session)

    async def current_session(self) -> Result[Session]:
        if self._current is None:
            res = await self.new_session(label=None)
            if res.is_err:
                return res  # type: ignore[return-value]
            return ok(res.value)  # type: ignore[union-attr]
        return ok(self._current)

    async def allocate_path(
        self, kind: str, suffix: str, label: str | None = None
    ) -> Result[Path]:
        session_res = await self.current_session()
        if session_res.is_err:
            return session_res  # type: ignore[return-value]
        timestamp = datetime.now().strftime("%H%M%S-%f")[:-3]
        slug = _slugify(label) if label else kind
        filename = f"{timestamp}-{slug}{suffix}"
        return ok(session_res.value.root / filename)  # type: ignore[union-attr]

    async def register(self, artifact: Artifact) -> Result[None]:
        self._registered.append(artifact)
        return ok(None)
