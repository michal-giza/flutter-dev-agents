# ADR-0005: Hybrid dense + lexical retrieval for `recall`

**Status:** accepted
**Date:** 2026-05-14

## Context

The MCP's `recall(query, scope, k)` retrieves chunks from the
indexed SKILL + docs + project source. Pure dense retrieval
(BAAI/bge-small-en-v1.5 via FastEmbed) is strong on conceptual
queries ("UMP gate preconditions") but smooths away exact-token
signal. Querying for code identifiers like `tap_text` or
`TestExecutionFailure` would frequently miss because the embedding
treats them like prose.

Karpukhin et al., 2020 (DPR,
[arXiv:2004.04906](https://arxiv.org/abs/2004.04906)) established
dense is necessary; later hybrid-retrieval literature established
that adding a lexical channel beats pure dense for mixed query
distributions.

## Decision

Three pieces:

1. **Over-fetch from dense**: ask Qdrant for `k * 4` (min 12) candidates.
2. **Re-rank with lexical overlap**: in-process token-level Jaccard
   with IDF-ish weighting (see `data/hybrid_rerank.py`). Splits
   CamelCase identifiers into component tokens so `TapTextRefused`
   matches a query for `tap text refused`.
3. **Fuse via Reciprocal Rank Fusion** (Cormack et al., 2009): the
   final top-k is the RRF combination of dense rank + lexical rank.

Pure Python, no new model dependency. Forward-compatible with adding
true BM25 via FastEmbed's `SparseTextEmbedding` when we have evidence
the lexical proxy is insufficient.

## Consequences

**Easier.** Code-identifier queries surface the right chunk. SKILL
queries continue to work as before. RRF is a known-stable fusion;
unlikely to need tuning.

**Harder.** Slight CPU overhead per recall (a few ms) from the
re-rank step. Negligible at user scale.

**Accepted.** Lexical-proxy quality vs true BM25 is a measured
question we haven't run. The cap-ed dimension is the agent's
context budget, not retrieval recall, so quality slack is fine
until proven otherwise.

## Alternatives considered

- **Dense only** — fails on code-identifier queries.
- **BM25 only** — fails on conceptual queries.
- **Qdrant native sparse vectors** (BM25-indexed at upload time) —
  cleaner long-term, but doubles index size and requires a new
  embedding model. Defer until we have a measurement gap.

## References

- `src/mcp_phone_controll/data/hybrid_rerank.py`
- `src/mcp_phone_controll/data/repositories/qdrant_rag_repository.py`
- `tests/unit/test_hybrid_rerank.py`
- Cormack et al., 2009, RRF — "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods" (SIGIR)
- Karpukhin et al., 2020, DPR — [arXiv:2004.04906](https://arxiv.org/abs/2004.04906)
