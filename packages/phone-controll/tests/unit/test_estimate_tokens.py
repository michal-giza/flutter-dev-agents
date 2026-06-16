"""Tests for estimate_tokens — token counter / budget predictor / validator."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.estimate_tokens import (
    EstimateTokens,
    EstimateTokensParams,
)


async def _run(**kw):
    res = await EstimateTokens()(EstimateTokensParams(**kw))
    assert isinstance(res, Ok), res
    return res.value


# ---- counting -----------------------------------------------------------


@pytest.mark.asyncio
async def test_counts_text():
    r = await _run(text="hello world " * 100)
    assert r.chars == 1200
    assert r.words == 200
    assert r.estimated_tokens > 0
    # heuristic band brackets the estimate
    assert r.low_tokens <= r.estimated_tokens <= r.high_tokens
    assert r.source == "text"
    assert r.method in ("heuristic", "tiktoken")


@pytest.mark.asyncio
async def test_tiktoken_band_collapses_to_point():
    """When tiktoken is the method, the band is the exact count."""
    r = await _run(text="The quick brown fox jumps over the lazy dog. " * 40)
    if r.method == "tiktoken":
        assert r.low_tokens == r.estimated_tokens == r.high_tokens
    else:
        assert r.low_tokens <= r.estimated_tokens <= r.high_tokens


@pytest.mark.asyncio
async def test_empty_text_is_zero_tokens():
    r = await _run(text="")
    assert r.chars == 0
    assert r.estimated_tokens == 0
    assert r.size_class == "small"


# ---- size classes -------------------------------------------------------


@pytest.mark.asyncio
async def test_size_class_small():
    r = await _run(text="word " * 50)
    assert r.size_class == "small"


@pytest.mark.asyncio
async def test_size_class_scales_up():
    # ~50k chars / 4 ≈ 12k tokens → large
    r = await _run(text="x " * 25_000, chars_per_token=4.0)
    assert r.size_class in ("large", "huge")


# ---- budget validation --------------------------------------------------


@pytest.mark.asyncio
async def test_budget_fits_comfortably():
    r = await _run(text="hello world " * 100, budget_tokens=10_000)
    assert r.fits is True
    assert r.headroom_tokens is not None and r.headroom_tokens > 0
    assert r.recommendation == "proceed"
    assert "fits" in r.advice


@pytest.mark.asyncio
async def test_budget_overflow_recommends_flush():
    r = await _run(text="x " * 5000, budget_tokens=100)
    assert r.fits is False
    assert r.headroom_tokens is not None and r.headroom_tokens < 0
    assert r.recommendation == "flush_context"
    assert "OVERFLOWS" in r.advice


@pytest.mark.asyncio
async def test_budget_tight_recommends_caution():
    # estimate just under budget, <20% headroom
    r = await _run(text="word " * 300)
    est = r.estimated_tokens
    budget = int(est * 1.05)  # 5% headroom → caution band
    r2 = await _run(text="word " * 300, budget_tokens=budget)
    assert r2.fits is True
    assert r2.recommendation == "proceed_with_caution"


@pytest.mark.asyncio
async def test_no_budget_means_no_verdict():
    r = await _run(text="hello")
    assert r.budget_tokens is None
    assert r.fits is None
    assert r.headroom_tokens is None
    assert r.recommendation is None


# ---- files --------------------------------------------------------------


@pytest.mark.asyncio
async def test_counts_file(tmp_path: Path):
    p = tmp_path / "payload.json"
    p.write_text("hello world " * 500, encoding="utf-8")
    r = await _run(path=p)
    assert r.chars == 6000
    assert r.source == "file:payload.json"
    assert r.estimated_tokens > 0


@pytest.mark.asyncio
async def test_missing_file_errors():
    res = await EstimateTokens()(
        EstimateTokensParams(path=Path("/nonexistent/nope.json"))
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_neither_text_nor_path_errors():
    res = await EstimateTokens()(EstimateTokensParams())
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


# ---- heuristic knobs ----------------------------------------------------


@pytest.mark.asyncio
async def test_denser_chars_per_token_yields_more_tokens():
    """Code/JSON (cpt ~3.3) should estimate more tokens than prose (cpt 4)
    for the same text — when the heuristic is in use."""
    text = "x" * 4000  # no spaces → no tiktoken-vs-heuristic ambiguity on words
    prose = await _run(text=text, chars_per_token=4.0)
    code = await _run(text=text, chars_per_token=3.3)
    if prose.method == "heuristic":
        assert code.estimated_tokens > prose.estimated_tokens


@pytest.mark.asyncio
async def test_nonpositive_chars_per_token_falls_back_to_default():
    r = await _run(text="hello world " * 100, chars_per_token=0)
    assert r.estimated_tokens > 0  # didn't divide by zero


@pytest.mark.asyncio
async def test_band_brackets_estimate_for_code_dense_input():
    """Regression: code/JSON has few whitespace 'words' but many tokens.
    An earlier words×1.33 blend pushed the central estimate BELOW the
    char-based low bound. The band must always bracket the estimate."""
    code = ('{"key": "value", "n": 12345, "nested": [1,2,3]} ' * 500)
    r = await _run(text=code, chars_per_token=3.3)
    if r.method == "heuristic":  # tiktoken collapses the band to a point
        assert r.low_tokens <= r.estimated_tokens <= r.high_tokens
