"""Artifact retention — disk_usage breakdown + prune_originals safety."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pytest

from mcp_phone_controll.domain.entities import Session
from mcp_phone_controll.domain.result import ok
from mcp_phone_controll.domain.usecases.artifact_retention import (
    DiskUsage,
    PruneOriginals,
    PruneOriginalsParams,
    _bucket_for,
)
from mcp_phone_controll.domain.usecases.base import NoParams


class _FakeArtifacts:
    def __init__(self, sessions_root: Path) -> None:
        self._session = Session(
            id="s1", started_at=datetime(2026, 1, 1),
            root=sessions_root / "s1",
        )
        self._session.root.mkdir(parents=True, exist_ok=True)

    async def new_session(self, _label=None): return ok(self._session)
    async def current_session(self): return ok(self._session)
    async def allocate_path(self, *_a, **_k): return ok(self._session.root / "x.png")
    async def register(self, _artifact): return ok(None)


def _touch(path: Path, contents: bytes = b"", mtime_offset_days: float = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    if mtime_offset_days:
        ts = time.time() - mtime_offset_days * 86400
        os_module_path = str(path)
        import os as _os

        _os.utime(os_module_path, (ts, ts))


# ---- _bucket_for classifier ---------------------------------------------


def test_bucket_classification():
    cases = [
        (Path("sessions/a/screenshot.png"), "screenshots"),
        (Path("sessions/a/screenshot.orig.png"), "originals"),
        (Path("sessions/a/release/01-home.png"), "release"),
        (Path("project/tests/fixtures/golden/home.png"), "goldens"),
        (Path("sessions/a/run.log"), "logs"),
        (Path("sessions/a/rec.mp4"), "recordings"),
        (Path("sessions/a/unknown.bin"), "other"),
    ]
    for path, expected in cases:
        assert _bucket_for(path) == expected, f"{path} → {expected}"


# ---- DiskUsage ----------------------------------------------------------


@pytest.mark.asyncio
async def test_disk_usage_buckets_files_correctly(tmp_path: Path):
    sessions = tmp_path / "sessions"
    repo = _FakeArtifacts(sessions)
    _touch(sessions / "s1" / "shot.png", b"x" * 100)
    _touch(sessions / "s1" / "shot.orig.png", b"x" * 500)
    _touch(sessions / "s1" / "run.log", b"x" * 50)
    _touch(sessions / "s1" / "rec.mp4", b"x" * 1000)
    _touch(sessions / "s2" / "release" / "01.png", b"x" * 200)

    res = await DiskUsage(repo).execute(NoParams())
    assert res.is_ok
    rep = res.value
    bucket_names = {b.name for b in rep.buckets}
    assert bucket_names >= {"screenshots", "originals", "logs", "recordings", "release"}
    total = sum(b.bytes for b in rep.buckets)
    assert total == rep.total_bytes
    assert rep.total_files == 5


# ---- PruneOriginals -----------------------------------------------------


@pytest.mark.asyncio
async def test_prune_originals_dry_run_does_not_delete(tmp_path: Path):
    sessions = tmp_path / "sessions"
    repo = _FakeArtifacts(sessions)
    old = sessions / "s1" / "shot.orig.png"
    _touch(old, b"x" * 1000, mtime_offset_days=30)
    res = await PruneOriginals(repo).execute(
        PruneOriginalsParams(older_than_days=14, dry_run=True)
    )
    assert res.is_ok
    assert res.value.candidates_found == 1
    assert res.value.deleted == 0
    assert res.value.bytes_freed == 1000
    assert old.exists()  # NOT deleted


@pytest.mark.asyncio
async def test_prune_originals_deletes_when_not_dry_run(tmp_path: Path):
    sessions = tmp_path / "sessions"
    repo = _FakeArtifacts(sessions)
    old = sessions / "s1" / "shot.orig.png"
    _touch(old, b"x" * 1000, mtime_offset_days=30)
    res = await PruneOriginals(repo).execute(
        PruneOriginalsParams(older_than_days=14, dry_run=False)
    )
    assert res.is_ok
    assert res.value.deleted == 1
    assert res.value.bytes_freed == 1000
    assert not old.exists()


@pytest.mark.asyncio
async def test_prune_originals_respects_age_threshold(tmp_path: Path):
    sessions = tmp_path / "sessions"
    repo = _FakeArtifacts(sessions)
    fresh = sessions / "s1" / "fresh.orig.png"
    old = sessions / "s1" / "old.orig.png"
    _touch(fresh, b"x", mtime_offset_days=1)
    _touch(old, b"y" * 500, mtime_offset_days=30)
    res = await PruneOriginals(repo).execute(
        PruneOriginalsParams(older_than_days=14, dry_run=False)
    )
    assert res.is_ok
    assert res.value.deleted == 1
    assert fresh.exists()
    assert not old.exists()


@pytest.mark.asyncio
async def test_prune_originals_only_touches_orig_pngs(tmp_path: Path):
    sessions = tmp_path / "sessions"
    repo = _FakeArtifacts(sessions)
    # A regular old screenshot and a golden — neither should ever be touched.
    capped = sessions / "s1" / "shot.png"
    golden = sessions / "s1" / "golden" / "home.png"
    _touch(capped, b"x", mtime_offset_days=30)
    _touch(golden, b"y", mtime_offset_days=30)
    res = await PruneOriginals(repo).execute(
        PruneOriginalsParams(older_than_days=14, dry_run=False)
    )
    assert res.is_ok
    assert res.value.deleted == 0
    assert capped.exists()
    assert golden.exists()
