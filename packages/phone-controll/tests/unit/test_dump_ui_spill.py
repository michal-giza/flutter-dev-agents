"""dump_ui spills full XML to an artifact when large (v0.14.0 #5).

Field bug: dump_ui truncated at ~56 KB with a `fetch_full_artifact`
hint, but no artifact was ever written — a dead end. Now the full XML
is written to disk and the path is returned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Ok, ok
from mcp_phone_controll.domain.usecases.ui_query import DumpUi, DumpUiParams
from tests.fakes.fake_repositories import (
    FakeArtifactRepository,
    FakeSessionStateRepository,
)


class _XmlUi:
    def __init__(self, xml: str) -> None:
        self._xml = xml

    async def dump_ui(self, serial):
        return ok(self._xml)


def _dump(xml: str, tmp_path: Path, artifacts=True):
    arts = FakeArtifactRepository(root=tmp_path / "sessions") if artifacts else None
    uc = DumpUi(_XmlUi(xml), FakeSessionStateRepository(serial="dev"), arts)
    return uc


@pytest.mark.asyncio
async def test_small_tree_is_inline_no_artifact(tmp_path):
    uc = _dump("<hierarchy><node text='Hi'/></hierarchy>", tmp_path)
    res = await uc(DumpUiParams())
    assert isinstance(res, Ok)
    d = res.value
    assert d.artifact_path is None
    assert d.node_count == 1
    assert "inline" in d.advice
    assert d.xml.startswith("<hierarchy")


@pytest.mark.asyncio
async def test_large_tree_spills_to_artifact(tmp_path):
    big = "<hierarchy>" + ("<node text='x'/>" * 2000) + "</hierarchy>"
    assert len(big.encode()) > 8000
    uc = _dump(big, tmp_path)
    res = await uc(DumpUiParams())
    assert isinstance(res, Ok)
    d = res.value
    assert d.artifact_path is not None
    # the full XML is actually on disk (not just promised)
    written = Path(d.artifact_path).read_text(encoding="utf-8")
    assert written == big
    assert d.byte_size == len(big.encode())
    assert "find_element" in d.advice  # points at the full-tree searchers


@pytest.mark.asyncio
async def test_large_tree_without_artifacts_still_advises(tmp_path):
    """No artifact session wired → degrade gracefully, point at find_element."""
    big = "<hierarchy>" + ("<node text='x'/>" * 2000) + "</hierarchy>"
    uc = _dump(big, tmp_path, artifacts=False)
    res = await uc(DumpUiParams())
    assert isinstance(res, Ok)
    assert res.value.artifact_path is None
    assert "find_element" in res.value.advice


@pytest.mark.asyncio
async def test_node_count_counts_xcui_too(tmp_path):
    xml = "<AppiumAUT><XCUIElementTypeButton/><XCUIElementTypeStaticText/></AppiumAUT>"
    uc = _dump(xml, tmp_path)
    res = await uc(DumpUiParams())
    assert res.value.node_count == 2
