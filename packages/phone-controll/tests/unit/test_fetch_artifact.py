"""Unit tests for fetch_artifact."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.usecases.artifacts import (
    FetchArtifact,
    FetchArtifactParams,
)


@pytest.mark.asyncio
async def test_reads_text_file(tmp_path: Path):
    f = tmp_path / "log.txt"
    f.write_text("hello world")
    res = await FetchArtifact().execute(FetchArtifactParams(path=f))
    assert res.is_ok
    assert res.value.content == "hello world"
    assert res.value.is_binary is False
    assert res.value.size_bytes == 11
    assert len(res.value.sha256) == 64


@pytest.mark.asyncio
async def test_truncates_when_exceeds_max_bytes(tmp_path: Path):
    f = tmp_path / "log.txt"
    f.write_text("x" * 1000)
    res = await FetchArtifact().execute(
        FetchArtifactParams(path=f, max_bytes=100)
    )
    assert res.is_ok
    assert res.value.truncated is True
    assert len(res.value.content) == 100
    assert res.value.size_bytes == 1000


@pytest.mark.asyncio
async def test_binary_file_returns_metadata_only(tmp_path: Path):
    f = tmp_path / "shot.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
    res = await FetchArtifact().execute(FetchArtifactParams(path=f))
    assert res.is_ok
    assert res.value.is_binary is True
    assert res.value.content is None


@pytest.mark.asyncio
async def test_missing_file_errors(tmp_path: Path):
    res = await FetchArtifact().execute(
        FetchArtifactParams(path=tmp_path / "nope.txt")
    )
    assert not res.is_ok
    assert res.failure.next_action == "check_path"
