"""Recall + IndexProject use cases — fake RAG repo, no Qdrant required."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.data.chunker import LanguageAwareChunker
from mcp_phone_controll.data.repositories.null_rag_repository import (
    NullRagRepository,
)
from mcp_phone_controll.domain.entities import IndexStats, RecallChunk
from mcp_phone_controll.domain.result import Err, ok
from mcp_phone_controll.domain.usecases.recall import (
    IndexProject,
    IndexProjectParams,
    Recall,
    RecallParams,
)


class _FakeRag:
    """Captures index_collection calls; returns canned recall results."""

    def __init__(self, recall_results=None):
        self._recall = recall_results or []
        self.indexed: list[tuple[str, list[tuple[str, str, dict]]]] = []
        self.available_value = ok("fake")

    async def is_available(self):
        return self.available_value

    async def recall(self, query, k=3, scope="all"):
        return ok(list(self._recall[:k]))

    async def index_collection(self, collection, items):
        self.indexed.append((collection, items))
        return ok(
            IndexStats(
                collection=collection,
                files_indexed=len({src for _t, src, _md in items}),
                chunks_indexed=len(items),
                duration_ms=1,
            )
        )


# ---- Recall --------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_returns_chunks():
    rag = _FakeRag(
        recall_results=[
            RecallChunk(text="abc", source="SKILL.md", score=0.9),
            RecallChunk(text="def", source="SKILL.md", score=0.7),
        ]
    )
    res = await Recall(rag).execute(RecallParams(query="ump gate", k=2))
    assert res.is_ok
    assert len(res.value) == 2


@pytest.mark.asyncio
async def test_recall_rejects_empty_query():
    res = await Recall(_FakeRag()).execute(RecallParams(query="   "))
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"


@pytest.mark.asyncio
async def test_recall_rejects_invalid_scope():
    res = await Recall(_FakeRag()).execute(
        RecallParams(query="x", scope="weird")
    )
    assert isinstance(res, Err)
    assert "valid_scopes" in res.failure.details


@pytest.mark.asyncio
async def test_recall_rejects_out_of_range_k():
    res = await Recall(_FakeRag()).execute(RecallParams(query="x", k=99))
    assert isinstance(res, Err)


@pytest.mark.asyncio
async def test_recall_propagates_null_rag_failure():
    res = await Recall(NullRagRepository()).execute(RecallParams(query="x"))
    assert isinstance(res, Err)
    assert res.failure.next_action == "install_rag_extra"


# ---- IndexProject --------------------------------------------------------


@pytest.mark.asyncio
async def test_index_project_chunks_and_uploads(tmp_path: Path):
    proj = tmp_path / "p"
    (proj / "lib").mkdir(parents=True)
    (proj / "docs").mkdir(parents=True)
    (proj / "lib" / "main.dart").write_text(
        "class App extends StatelessWidget {\n"
        "  const App({super.key});\n"
        "  Widget build(BuildContext c) => const Scaffold(body: Text('hi'));\n"
        "}\n" * 3
    )
    (proj / "docs" / "guide.md").write_text(
        "# Guide\n\nA generous body that exceeds the minimum chunk size for testing.\n"
        "More content to keep the chunker happy and produce a chunk we can assert on.\n\n"
        "# Subsection\n\nAnother body with enough text to pass the floor filter.\n"
        "Even more padding to be safe across chunker tweaks.\n"
    )
    rag = _FakeRag()
    uc = IndexProject(rag, LanguageAwareChunker())
    res = await uc.execute(IndexProjectParams(project_path=proj))
    assert res.is_ok
    stats = res.value
    assert stats.chunks_indexed >= 2
    assert stats.files_indexed >= 2
    # The metadata should include scope tags.
    items = rag.indexed[0][1]
    scopes = {md["scope"] for _t, _s, md in items}
    assert "code" in scopes or "docs" in scopes


@pytest.mark.asyncio
async def test_index_project_rejects_missing_directory(tmp_path: Path):
    res = await IndexProject(_FakeRag(), LanguageAwareChunker()).execute(
        IndexProjectParams(project_path=tmp_path / "no")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "check_path"


@pytest.mark.asyncio
async def test_index_project_returns_unavailable_on_null_rag(tmp_path: Path):
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "README.md").write_text("# x\n" * 50)
    res = await IndexProject(NullRagRepository(), LanguageAwareChunker()).execute(
        IndexProjectParams(project_path=proj)
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "install_rag_extra"
