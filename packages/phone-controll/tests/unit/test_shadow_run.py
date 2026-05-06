"""Smoke test for the shadow-run harness — must produce zero invariant
violations against the Tier-G suite. This is the CI-side gate that the
article enhancement #7 promises."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_shadow_run_tier_g_zero_invariant_violations():
    # Import paths the script uses; mirror its logic without spawning a process.
    import sys
    import importlib.util

    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts" / "shadow_run.py"
    )
    spec = importlib.util.spec_from_file_location("shadow_run", script_path)
    assert spec and spec.loader
    sr = importlib.util.module_from_spec(spec)
    sys.modules["shadow_run"] = sr
    spec.loader.exec_module(sr)

    from tests.integration.test_tool_dispatcher import _build_fake_dispatcher

    dispatcher = _build_fake_dispatcher(Path("/tmp"))
    failures = 0
    for tool in sr._TIER_G_TOOLS:
        res = await sr._drive(dispatcher, tool, iterations=20, strategy="fuzz")
        assert res["envelope_invariants_violated"] == 0, (
            f"{tool} produced malformed envelopes: {res}"
        )
        failures += res["envelope_invariants_violated"]
    assert failures == 0
