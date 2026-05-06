"""Hybrid retrieval reranker — pure unit tests, no Qdrant."""

from __future__ import annotations

from mcp_phone_controll.data.hybrid_rerank import (
    hybrid_rerank,
    lexical_score,
    rrf_fuse,
    tokenize,
)


def test_tokenize_splits_camel_case():
    assert tokenize("TapTextRefused") == ["tap", "text", "refused"]


def test_tokenize_handles_underscores():
    assert tokenize("tap_text_method") == ["tap", "text", "method"]


def test_lexical_score_rewards_overlap():
    q = tokenize("tap_text refused")
    text_match = "TapTextRefused: tap_text refused while patrol active"
    text_miss = "Generic device-listing log entry without overlap."
    assert lexical_score(q, text_match) > lexical_score(q, text_miss)


def test_lexical_score_zero_when_no_overlap():
    q = tokenize("ump gate")
    assert lexical_score(q, "Completely unrelated content here.") == 0.0


def test_rrf_fuse_prefers_chunks_high_in_both_rankings():
    dense = ["a", "b", "c", "d"]
    lex = ["c", "a", "b", "d"]
    fused = rrf_fuse([dense, lex])
    # 'a' is rank 1 dense + rank 2 lex; 'c' is rank 3 dense + rank 1 lex.
    # Both should outrank 'd' (rank 4 in both).
    ordered = sorted(fused.items(), key=lambda p: p[1], reverse=True)
    assert ordered[-1][0] == "d"


def test_hybrid_rerank_promotes_lexical_match_for_code_query():
    # The dense ranking gets the lexical match wrong (returns it last);
    # hybrid should pull it forward.
    query = "tap_text refused"
    dense_hits = [
        ("h1", "general guidance about Patrol sessions and discipline.", 0.91),
        ("h2", "device locking strategy and lifecycle.", 0.90),
        ("h3", "TapTextRefused — tap_text is refused while a Patrol session is active.", 0.40),
    ]
    top = hybrid_rerank(query, dense_hits, k=2)
    assert "h3" in top  # the exact-identifier match must surface


def test_hybrid_rerank_handles_empty_input():
    assert hybrid_rerank("anything", [], k=3) == []
