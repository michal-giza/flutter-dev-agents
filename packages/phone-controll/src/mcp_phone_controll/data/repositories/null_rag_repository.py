"""Null RAG repository — returns informative failures when RAG is off.

Used when the optional `[rag]` extras aren't installed or Qdrant isn't
reachable. Every method returns a `RagUnavailableFailure` whose
`next_action` tells the agent what to fix.
"""

from __future__ import annotations

from ...domain.entities import IndexStats, RecallChunk
from ...domain.failures import RagUnavailableFailure
from ...domain.result import Result, err


class NullRagRepository:
    """No-op RAG repo. All operations fail open with a precise next_action."""

    def __init__(self, reason: str = "rag extras not installed") -> None:
        self._reason = reason

    async def recall(
        self, query: str, k: int = 3, scope: str = "all"
    ) -> Result[list[RecallChunk]]:
        return err(self._fail(action="install_rag_extra"))

    async def index_collection(
        self, collection: str, items: list[tuple[str, str, dict]]
    ) -> Result[IndexStats]:
        return err(self._fail(action="install_rag_extra"))

    async def is_available(self) -> Result[str]:
        return err(self._fail(action="install_rag_extra"))

    def _fail(self, action: str) -> RagUnavailableFailure:
        return RagUnavailableFailure(
            message=f"RAG backend unavailable: {self._reason}",
            next_action=action,
            details={
                "reason": self._reason,
                "fix": (
                    "Install: cd packages/phone-controll && uv pip install "
                    "-e '.[rag]'. Then run: docker run -p 6333:6333 "
                    "qdrant/qdrant"
                ),
                "docs": "docs/composition.md",
            },
        )
