"""CorrectiveRecall — relevance grading + scope-fallback retry."""

from __future__ import annotations

import pytest

from mcp_phone_controll.domain.entities import RecallChunk
from mcp_phone_controll.domain.result import Err, ok
from mcp_phone_controll.domain.usecases.crag import (
    CorrectiveRecall,
    CorrectiveRecallParams,
)


class _RecallStub:
    """Fake Recall use case with scope-conditional canned responses."""

    def __init__(self, by_scope: dict[str, list[RecallChunk]]):
        self._by_scope = by_scope
        self.calls: list[tuple[str, str, int]] = []

    async def execute(self, params):
        self.calls.append((params.query, params.scope, params.k))
        return ok(self._by_scope.get(params.scope, []))


@pytest.mark.asyncio
async def test_returns_first_attempt_when_confidence_clears_threshold():
    chunks = [
        RecallChunk(
            text="ump_gate decline preconditions and how to capture diagnostics",
            source="SKILL.md",
            score=0.9,
        )
    ]
    stub = _RecallStub({"skill": chunks})
    res = await CorrectiveRecall(stub).execute(
        CorrectiveRecallParams(
            query="ump_gate decline preconditions",
            scope="skill",
            confidence_threshold=0.05,
        )
    )
    assert res.is_ok
    assert res.value.used_scope == "skill"
    assert res.value.retries == 0
    assert len(stub.calls) == 1


@pytest.mark.asyncio
async def test_falls_back_to_next_scope_on_low_confidence():
    weak = [RecallChunk(text="unrelated content", source="A", score=0.4)]
    strong = [
        RecallChunk(
            text="reflexion retry pattern referenced by ump_gate decline path",
            source="SKILL.md",
            score=0.9,
        )
    ]
    stub = _RecallStub({"trace": weak, "skill": strong, "all": strong})
    res = await CorrectiveRecall(stub).execute(
        CorrectiveRecallParams(
            query="reflexion retry ump_gate",
            scope="trace",
            confidence_threshold=0.10,
            max_retries=3,
        )
    )
    assert res.is_ok
    # Stub returns strong content for `skill` (and `all`); fallback should
    # have iterated past `trace` and landed on a stronger scope.
    assert res.value.used_scope != "trace"
    assert res.value.retries >= 1


@pytest.mark.asyncio
async def test_returns_best_effort_when_all_scopes_low():
    weak = [RecallChunk(text="generic irrelevant log", source="x", score=0.1)]
    stub = _RecallStub({s: weak for s in ("skill", "docs", "code", "trace", "all")})
    res = await CorrectiveRecall(stub).execute(
        CorrectiveRecallParams(
            query="ump_gate",
            scope="skill",
            confidence_threshold=0.99,
            max_retries=4,
        )
    )
    assert res.is_ok
    assert "low-confidence" in res.value.diagnosis


@pytest.mark.asyncio
async def test_propagates_underlying_recall_failure():
    from mcp_phone_controll.domain.failures import RagUnavailableFailure

    class _FailingRecall:
        async def execute(self, _p):
            return Err(
                RagUnavailableFailure(
                    message="rag off",
                    next_action="install_rag_extra",
                )
            )

    res = await CorrectiveRecall(_FailingRecall()).execute(
        CorrectiveRecallParams(query="x")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "install_rag_extra"
