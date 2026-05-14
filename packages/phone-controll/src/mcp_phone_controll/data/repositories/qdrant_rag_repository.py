"""Qdrant + FastEmbed-backed RagRepository.

Optional dependency: install with `uv pip install -e '.[rag]'`. The module
is import-safe even without the deps — construction is what fails.

Why these choices:

  - **Qdrant**: same backend the rag-search course teaches; runs as a
    single Docker container; supports filtered hybrid search out of the
    box (Reimers, 2019, sentence-BERT background; Karpukhin et al.,
    2020, arXiv 2004.04906 dense passage retrieval).
  - **FastEmbed**: ONNX-served embeddings, no torch dependency, ~50 MB
    base. Default model BAAI/bge-small-en-v1.5 (384 dims) — strong
    quality-per-byte. Switch with `MCP_RAG_EMBED_MODEL`.
  - **Hybrid not built in v1**. Pure dense retrieval covers the agent's
    "find me the SKILL section about UMP" use case. BM25 sparse can
    layer on later (one method, no schema change).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
import uuid
from importlib.util import find_spec
from typing import Any

from ...domain.entities import IndexStats, RecallChunk
from ...domain.failures import RagIndexingFailure, RagUnavailableFailure
from ...domain.result import Result, err, ok

_DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
_DEFAULT_QDRANT_URL = "http://localhost:6333"
_DEFAULT_VECTOR_DIM = 384


def rag_extras_available() -> bool:
    """True iff `qdrant_client` and `fastembed` are both importable."""
    return all(find_spec(m) is not None for m in ("qdrant_client", "fastembed"))


class QdrantRagRepository:
    """Async-friendly Qdrant + FastEmbed adapter.

    Construction is lazy: the Qdrant client + embedding model are loaded
    on first call. That keeps `build_runtime()` cheap when RAG is opted
    out and avoids loading the embedder for users who never call
    `recall`/`index_project`.
    """

    def __init__(
        self,
        url: str | None = None,
        embed_model: str | None = None,
        vector_dim: int = _DEFAULT_VECTOR_DIM,
    ) -> None:
        self._url = url or os.environ.get("MCP_QDRANT_URL", _DEFAULT_QDRANT_URL)
        self._embed_model = (
            embed_model
            or os.environ.get("MCP_RAG_EMBED_MODEL", _DEFAULT_EMBED_MODEL)
        )
        self._vector_dim = vector_dim
        self._client: Any | None = None
        self._embedder: Any | None = None
        self._init_lock = asyncio.Lock()
        self._init_error: RagUnavailableFailure | None = None

    async def _ensure_ready(self) -> RagUnavailableFailure | None:
        if self._client is not None and self._embedder is not None:
            return None
        if self._init_error is not None:
            return self._init_error
        async with self._init_lock:
            if self._client is not None and self._embedder is not None:
                return None
            try:
                from fastembed import TextEmbedding
                from qdrant_client import QdrantClient
            except ImportError as exc:
                self._init_error = RagUnavailableFailure(
                    message=f"missing optional dep: {exc}",
                    next_action="install_rag_extra",
                    details={
                        "missing": str(exc),
                        "fix": "uv pip install -e '.[rag]'",
                    },
                )
                return self._init_error
            try:
                # Run blocking init in a thread; fastembed's first call
                # downloads the model.
                self._client = await asyncio.to_thread(
                    QdrantClient, url=self._url
                )
                self._embedder = await asyncio.to_thread(
                    TextEmbedding, model_name=self._embed_model
                )
            except Exception as exc:
                self._init_error = RagUnavailableFailure(
                    message=f"failed to initialise RAG backend: {exc}",
                    next_action="start_qdrant",
                    details={
                        "url": self._url,
                        "fix": "docker run -p 6333:6333 qdrant/qdrant",
                    },
                )
                return self._init_error
            return None

    async def is_available(self) -> Result[str]:
        fail = await self._ensure_ready()
        if fail is not None:
            return err(fail)
        try:
            await asyncio.to_thread(self._client.get_collections)
        except Exception as exc:
            return err(
                RagUnavailableFailure(
                    message=f"qdrant unreachable: {exc}",
                    next_action="start_qdrant",
                    details={"url": self._url},
                )
            )
        return ok(f"qdrant @ {self._url}; embed={self._embed_model}")

    async def index_collection(
        self,
        collection: str,
        items: list[tuple[str, str, dict]],
    ) -> Result[IndexStats]:
        fail = await self._ensure_ready()
        if fail is not None:
            return err(fail)
        if not items:
            return err(
                RagIndexingFailure(
                    message="empty items list",
                    next_action="check_globs",
                )
            )
        started = time.monotonic()
        try:
            from qdrant_client.http import models as qm

            await asyncio.to_thread(
                self._ensure_collection, collection, self._vector_dim
            )
            texts = [t for t, _src, _md in items]
            vectors = await asyncio.to_thread(
                lambda: list(self._embedder.embed(texts))
            )
            points = []
            sources_seen: set[str] = set()
            for (text, source, metadata), vector in zip(items, vectors, strict=True):
                sources_seen.add(source)
                point_id = _stable_point_id(collection, source, metadata, text)
                payload = {
                    "text": text,
                    "source": source,
                    **metadata,
                }
                points.append(
                    qm.PointStruct(
                        id=point_id, vector=list(vector), payload=payload
                    )
                )
            await asyncio.to_thread(
                self._client.upsert, collection_name=collection, points=points
            )
        except Exception as exc:
            return err(
                RagIndexingFailure(
                    message=f"indexing failed: {exc}",
                    next_action="retry_with_backoff",
                )
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        return ok(
            IndexStats(
                collection=collection,
                files_indexed=len(sources_seen),
                chunks_indexed=len(items),
                skipped=(),
                duration_ms=duration_ms,
            )
        )

    async def recall(
        self, query: str, k: int = 3, scope: str = "all"
    ) -> Result[list[RecallChunk]]:
        fail = await self._ensure_ready()
        if fail is not None:
            return err(fail)
        # Over-fetch dense, then re-rank with lexical fusion (RRF). Keeps
        # us competitive on exact-token queries (`tap_text`, error codes)
        # without requiring Qdrant sparse-vector config.
        over_fetch = max(k * 4, 12)
        try:
            from qdrant_client.http import models as qm

            from ..hybrid_rerank import hybrid_rerank

            vector = (
                await asyncio.to_thread(
                    lambda: list(self._embedder.embed([query]))
                )
            )[0]
            collections_res = await asyncio.to_thread(
                self._client.get_collections
            )
            collection_names = [c.name for c in collections_res.collections]
            if not collection_names:
                return ok([])
            scope_filter = None
            if scope != "all":
                scope_filter = qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="scope", match=qm.MatchValue(value=scope)
                        )
                    ]
                )
            all_hits: list[tuple[str, str, float, RecallChunk]] = []
            for name in collection_names:
                hits = await asyncio.to_thread(
                    self._client.search,
                    collection_name=name,
                    query_vector=list(vector),
                    limit=over_fetch,
                    query_filter=scope_filter,
                )
                for hit in hits:
                    payload = hit.payload or {}
                    chunk_id = str(hit.id)
                    text = str(payload.get("text", ""))
                    chunk = RecallChunk(
                        text=text,
                        source=str(payload.get("source", name)),
                        score=float(hit.score),
                        metadata={
                            "collection": name,
                            **{
                                k: v
                                for k, v in payload.items()
                                if k not in {"text", "source"}
                            },
                        },
                    )
                    all_hits.append((chunk_id, text, float(hit.score), chunk))
        except Exception as exc:
            return err(
                RagUnavailableFailure(
                    message=f"recall failed: {exc}",
                    next_action="retry_with_backoff",
                )
            )
        if not all_hits:
            return ok([])
        # Hybrid rerank — combine dense ranks with lexical ranks via RRF.
        dense_triples = [(cid, text, score) for cid, text, score, _ in all_hits]
        top_ids = hybrid_rerank(query, dense_triples, k)
        by_id = {cid: chunk for cid, _, _, chunk in all_hits}
        return ok([by_id[cid] for cid in top_ids if cid in by_id])

    # ---- internals ------------------------------------------------------

    def _ensure_collection(self, name: str, dim: int) -> None:
        from qdrant_client.http import models as qm

        existing = {c.name for c in self._client.get_collections().collections}
        if name in existing:
            return
        self._client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(
                size=dim, distance=qm.Distance.COSINE
            ),
        )


def _stable_point_id(
    collection: str, source: str, metadata: dict, text: str
) -> str:
    """Deterministic UUID5 from (collection, source, char_start, hash(text)).

    Re-indexing the same chunk replaces it instead of duplicating; safe
    against minor whitespace edits to the same logical chunk.
    """
    text_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    key = (
        f"{collection}|{source}|{metadata.get('char_start', 0)}|{text_hash}"
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
