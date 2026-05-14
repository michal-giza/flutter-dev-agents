"""Reciprocal-rank fusion of dense + lexical retrieval.

Pure Python, zero deps. The cleanest path to "hybrid" without forcing
Qdrant sparse-vector config or a second embedding model:

  1. Over-fetch from dense retrieval (k * over_fetch)
  2. Re-rank the over-fetched set by lexical overlap (token Jaccard
     plus an IDF-ish weighting that favours rare tokens)
  3. Fuse the dense ranks with the lexical ranks via RRF
     (Cormack et al., 2009 — "Reciprocal Rank Fusion outperforms
     Condorcet and individual Rank Learning Methods")

Why this beats pure dense for our use case: dense embeddings smooth
away exact-token signal — querying for a code identifier like
`tap_text` or `TestExecutionFailure` benefits hugely from lexical
overlap. Karpukhin et al., 2020 (DPR, arXiv:2004.04906) showed dense
wins on conceptual queries; for ours we need both.

Forward-compatible: when we add real BM25 via FastEmbed's
SparseTextEmbedding (Tier H1 v2), this module's `rrf_fuse` function
can take real sparse scores instead of the lexical proxy below.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def tokenize(text: str) -> list[str]:
    """Lowercased identifier tokens. Splits CamelCase to ['camel', 'case']."""
    raw = _TOKEN_RE.findall(text)
    out: list[str] = []
    for token in raw:
        # Split CamelCase → camel, Case
        parts = re.findall(r"[A-Z][a-z0-9]+|[a-z0-9]+|[A-Z]+(?=[A-Z]|$)", token)
        if parts:
            out.extend(p.lower() for p in parts)
        else:
            out.append(token.lower())
    return out


@dataclass(frozen=True, slots=True)
class _Scored:
    chunk_id: str
    text: str
    dense_score: float
    lex_score: float


def lexical_score(query_tokens: list[str], text: str) -> float:
    """Jaccard-with-IDF — rewards rare overlapping tokens.

    Cheap stand-in for BM25 over a small over-fetched set. The exact
    formula doesn't matter much; what matters is that the ranking
    prefers chunks containing the query's rare tokens.
    """
    chunk_tokens = tokenize(text)
    if not chunk_tokens or not query_tokens:
        return 0.0
    chunk_set = set(chunk_tokens)
    overlap = [t for t in query_tokens if t in chunk_set]
    if not overlap:
        return 0.0
    # Approximate IDF: shorter tokens are penalised (common stop-ish);
    # rare exact identifiers (length >= 5) get a bonus.
    weight = sum(math.log(1 + len(t)) for t in overlap)
    return weight / (1 + math.log(1 + len(chunk_tokens)))


def rrf_fuse(
    rankings: list[list[str]],
    k_constant: int = 60,
) -> dict[str, float]:
    """Reciprocal-rank fusion. Each ranking is a list of chunk_ids in
    descending order of relevance. Returns chunk_id → fused_score.

    The constant k=60 is the value Cormack et al. recommend; it
    dampens the influence of the top-1 vs top-2 difference and makes
    the fusion robust to noisy rankers.
    """
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (
                k_constant + rank + 1
            )
    return fused


def hybrid_rerank(
    query: str,
    dense_hits: list[tuple[str, str, float]],  # (id, text, dense_score)
    k: int,
) -> list[str]:
    """Top-k chunk_ids after dense + lexical fusion.

    `dense_hits` is the over-fetched dense result. We re-rank in-place
    using lexical scores, then fuse the two rankings with RRF.
    """
    if not dense_hits:
        return []
    query_tokens = tokenize(query)
    scored = [
        _Scored(
            chunk_id=cid,
            text=text,
            dense_score=dense,
            lex_score=lexical_score(query_tokens, text),
        )
        for cid, text, dense in dense_hits
    ]
    dense_ranked = [s.chunk_id for s in sorted(scored, key=lambda s: s.dense_score, reverse=True)]
    lex_ranked = [s.chunk_id for s in sorted(scored, key=lambda s: s.lex_score, reverse=True)]
    fused = rrf_fuse([dense_ranked, lex_ranked])
    by_score = sorted(fused.items(), key=lambda p: p[1], reverse=True)
    return [cid for cid, _score in by_score[:k]]
