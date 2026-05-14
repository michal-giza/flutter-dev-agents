"""Corrective RAG (CRAG) — self-grade and re-query on low confidence.

Yan et al., 2024 ("Corrective Retrieval Augmented Generation",
arXiv:2401.15884) showed that adding a relevance-grading step on top of
retrieval markedly improves end-to-end task success: a retriever that
sometimes returns garbage stops poisoning the agent's context.

This use case wraps `Recall`. After retrieval, every chunk gets a
relevance score against the query. If the average is above
`confidence_threshold`, return as-is. If below, re-query with a wider
scope (or a fallback strategy) and re-grade.

The grader is deliberately cheap — it's the same lexical overlap +
length-normalised score the hybrid reranker uses. We don't ship an
LLM-based grader; that's a Tier J research bet, not a v1 default.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...domain.usecases.base import BaseUseCase
from ..entities import RecallChunk
from ..failures import RagIndexingFailure
from ..result import Err, Result, err, ok

_FALLBACK_ORDER = ("skill", "docs", "code", "trace", "all")


@dataclass(frozen=True, slots=True)
class CorrectiveRecallParams:
    query: str
    k: int = 3
    scope: str = "all"
    confidence_threshold: float = 0.15
    max_retries: int = 1


@dataclass(frozen=True, slots=True)
class CorrectiveRecallResult:
    chunks: tuple[RecallChunk, ...]
    confidence: float
    used_scope: str
    retries: int
    diagnosis: str


def _grade(query: str, chunks: list[RecallChunk]) -> float:
    """Mean lexical-overlap score across retrieved chunks. Cheap proxy
    for relevance — same family as the hybrid reranker's lex_score."""
    from ...data.hybrid_rerank import lexical_score, tokenize

    if not chunks:
        return 0.0
    q_tokens = tokenize(query)
    if not q_tokens:
        return 0.0
    scores = [lexical_score(q_tokens, c.text) for c in chunks]
    return sum(scores) / len(scores)


class CorrectiveRecall(BaseUseCase[CorrectiveRecallParams, CorrectiveRecallResult]):
    """Recall + relevance grading + scoped re-query on low confidence."""

    def __init__(self, recall_uc) -> None:
        # `recall_uc` must implement async execute(RecallParams) -> Result.
        self._recall = recall_uc

    async def execute(
        self, params: CorrectiveRecallParams
    ) -> Result[CorrectiveRecallResult]:
        if params.confidence_threshold < 0 or params.confidence_threshold > 1:
            return err(
                RagIndexingFailure(
                    message="confidence_threshold must be in [0, 1]",
                    next_action="fix_arguments",
                )
            )
        from .recall import RecallParams

        scopes_to_try: list[str] = [params.scope]
        if params.scope != "all":
            for fallback in _FALLBACK_ORDER:
                if fallback not in scopes_to_try:
                    scopes_to_try.append(fallback)
                if len(scopes_to_try) > params.max_retries + 1:
                    break
        else:
            scopes_to_try = ["all"]
        retries = 0
        last_chunks: list[RecallChunk] = []
        last_score = 0.0
        last_scope = params.scope
        for attempt, scope in enumerate(scopes_to_try):
            res = await self._recall.execute(
                RecallParams(query=params.query, k=params.k, scope=scope)
            )
            if isinstance(res, Err):
                # Propagate underlying RAG failure (e.g. install_rag_extra)
                # — CRAG can't repair an unavailable backend.
                return res
            chunks = list(res.value)
            score = _grade(params.query, chunks)
            last_chunks, last_score, last_scope = chunks, score, scope
            if score >= params.confidence_threshold:
                return ok(
                    CorrectiveRecallResult(
                        chunks=tuple(chunks),
                        confidence=round(score, 4),
                        used_scope=scope,
                        retries=attempt,
                        diagnosis=(
                            f"confidence {score:.3f} ≥ {params.confidence_threshold}"
                            f" on scope={scope}"
                        ),
                    )
                )
            retries = attempt + 1
        # Fell through every scope; return the best we got with a clear
        # next_action so the agent knows the answer might be weak.
        return ok(
            CorrectiveRecallResult(
                chunks=tuple(last_chunks),
                confidence=round(last_score, 4),
                used_scope=last_scope,
                retries=retries,
                diagnosis=(
                    "all scopes returned low-confidence chunks; agent should "
                    "treat this as a hint, not an authoritative answer"
                ),
            )
        )
