"""Replay agent transcripts through the dispatcher and assert envelope invariants.

Each JSON file under `transcripts/` is a list whose first item is metadata
(`name`, `rationale`) and remaining items are steps:

    {"tool": "...", "args": {...}, "expect": {...}}

A step's `expect` block uses the keys understood by
`assert_envelope_invariants` in `conftest.py`. We dispatch through a fully-fake
dispatcher so the tests are hermetic and fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.agent.conftest import (
    assert_envelope_invariants,
    load_transcript,
)


def _transcript_files() -> list[Path]:
    here = Path(__file__).parent / "transcripts"
    return sorted(p for p in here.glob("*.json"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "transcript_path",
    _transcript_files(),
    ids=lambda p: p.stem,
)
async def test_replay_transcript(
    transcript_path: Path, fake_dispatcher_factory
) -> None:
    steps = load_transcript(transcript_path)
    assert steps, f"empty transcript: {transcript_path}"

    # First entry is metadata; the rest are real steps.
    metadata = steps[0]
    assert "name" in metadata, (
        f"first entry must be metadata with `name`: {transcript_path}"
    )

    dispatcher = fake_dispatcher_factory()

    for index, step in enumerate(steps[1:], start=1):
        tool = step["tool"]
        args = step.get("args", {})
        expected = step.get("expect", {})
        envelope = await dispatcher.dispatch(tool, args)
        try:
            assert_envelope_invariants(envelope, expected)
        except AssertionError as exc:
            raise AssertionError(
                f"transcript {transcript_path.name} step {index} ({tool}) "
                f"failed: {exc}"
            ) from exc
