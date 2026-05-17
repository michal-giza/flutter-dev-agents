"""SystemEnvironmentRepository._check_image_cap_pipeline — doctor self-test.

This probe was added after a recurring incident where users had stale
MCP subprocesses running an old cap value. The doctor row makes it
answerable in one call whether the cap pipeline actually works. The
probe writes a synthetic 3000x2000 PNG and asserts the result is
within the 1900 hard ceiling.

These tests pin the probe's contract — it must:
  - report ok=True when at least one backend (PIL/cv2/sips) is
    available AND successfully caps a 3000x2000 input
  - report ok=False with a clear `fix=` string when no backends are
    available
  - never raise (a crashing probe is worse than a failing probe)
"""

from __future__ import annotations

import pytest

from mcp_phone_controll.data.repositories.system_environment_repository import (
    SystemEnvironmentRepository,
)


def _have_pil() -> bool:
    try:
        import PIL  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    not _have_pil(), reason="Pillow needed to write the 3000x2000 probe input"
)


# We bypass __init__ — the probe doesn't use any of the injected
# clients, so a bare instance is fine and avoids dragging in adb /
# flutter / pmd3 wiring just for this unit test.
def _bare_repo() -> SystemEnvironmentRepository:
    return SystemEnvironmentRepository.__new__(SystemEnvironmentRepository)


@pytest.mark.asyncio
async def test_probe_reports_ok_when_backends_present():
    repo = _bare_repo()
    res = await repo._check_image_cap_pipeline()
    assert res.name == "image_cap_pipeline"
    assert res.ok is True, res.detail
    # Detail must mention the backends list AND the active cap so
    # operators can diagnose "wrong cap value" vs "no backends" in one
    # glance.
    assert "active cap=" in res.detail
    # At least one of the three backend names must appear.
    assert any(b in res.detail for b in ("PIL", "cv2", "sips")), res.detail


@pytest.mark.asyncio
async def test_probe_reports_red_when_no_backends(monkeypatch):
    """With no cv2, no PIL, no sips, the probe must surface the
    structured `pipx install pillow` style fix without raising."""
    # Force `available_backends()` to return empty by hiding all three.
    import shutil

    from mcp_phone_controll.data import image_capping

    monkeypatch.setattr(image_capping, "find_spec", lambda name: None)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    repo = _bare_repo()
    res = await repo._check_image_cap_pipeline()

    assert res.name == "image_cap_pipeline"
    assert res.ok is False
    # The fix message must point at the install command, not at a
    # generic "see docs" line. Concrete fix > pointer-to-fix.
    assert res.fix is not None
    assert "pillow" in res.fix.lower() or "pip install" in res.fix.lower()


@pytest.mark.asyncio
async def test_probe_never_raises_on_pil_failure(monkeypatch):
    """If PIL is installed but raises during Image.new or .save (e.g.
    a broken libpng install), the probe must catch it and report red
    instead of bubbling the exception. A crashing doctor probe blocks
    every other check downstream.

    We simulate the broken-PIL case by patching `Image.new` to raise.
    `find_spec("PIL")` still returns truthy (so the probe enters the
    PIL path), but the call inside blows up — exactly what a corrupted
    libpng would do.
    """
    from PIL import Image

    def _boom(*a, **k):
        raise RuntimeError("simulated broken libpng")

    monkeypatch.setattr(Image, "new", _boom)

    repo = _bare_repo()
    res = await repo._check_image_cap_pipeline()

    # Must not have raised. Must be red with a usable fix string.
    assert res.ok is False
    assert "probe raised" in res.detail.lower()
