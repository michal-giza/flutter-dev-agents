"""Contract test: `tools/list` shape snapshot.

The MCP `tools/list` response is the agent-facing contract. Tool count,
naming, schemas, annotations — all of it visible to every host that
connects. A silent drift here breaks agents in production.

This test snapshots the live surface to `docs/tools-contract.json` and
fails CI if the live surface diverges. To update the snapshot
intentionally (after adding/renaming/annotating a tool), run:

    UPDATE_CONTRACT=1 pytest tests/unit/test_tools_list_contract.py

The diff is then visible in the PR — reviewers see exactly what the
host-facing contract changed.

Pattern recommended by Kai Gritun (kaigritun.com/mcp/testing-mcp-servers)
and Block's MCP playbook (engineering.block.xyz/blog/blocks-playbook-for-designing-mcp-servers).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mcp_phone_controll.container import build_runtime
from mcp_phone_controll.presentation.descriptors._shared import (
    default_annotations,
)

# tests/unit/test_tools_list_contract.py → repo-root via parents[4]:
#   parents[0] = tests/unit
#   parents[1] = tests
#   parents[2] = packages/phone-controll
#   parents[3] = packages
#   parents[4] = REPO ROOT
SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[4] / "docs" / "tools-contract.json"
)


def _live_surface() -> list[dict]:
    """Produce the surface in stable shape: sorted by name, with
    schemas + annotations rendered the same way the stdio adapter
    would. Stable across runs so the snapshot diff is meaningful."""
    _, dispatcher = build_runtime()
    out: list[dict] = []
    for d in sorted(dispatcher.descriptors, key=lambda x: x.name):
        annotations = dict(default_annotations(d.name))
        # Per-tool overrides win — same as mcp_server.py
        if d.read_only is not None:
            annotations["readOnlyHint"] = d.read_only
        if d.destructive is not None:
            annotations["destructiveHint"] = d.destructive
        if d.idempotent is not None:
            annotations["idempotentHint"] = d.idempotent
        if d.open_world is not None:
            annotations["openWorldHint"] = d.open_world
        entry: dict = {
            "name": d.name,
            "description": d.description,
            "inputSchema": d.input_schema,
            "annotations": annotations,
        }
        # Only include outputSchema in the snapshot when a tool has
        # actually declared one — otherwise every untouched tool's
        # snapshot would show `outputSchema: null` and the diff would
        # be huge on no-op runs.
        if d.output_schema is not None:
            entry["outputSchema"] = d.output_schema
        out.append(entry)
    return out


def _write_snapshot(surface: list[dict]) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(surface, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_tools_list_matches_snapshot():
    """Compare the live surface to the committed snapshot. On
    intentional contract changes, re-run with UPDATE_CONTRACT=1 to
    refresh `docs/tools-contract.json`."""
    live = _live_surface()

    if os.environ.get("UPDATE_CONTRACT") == "1" or not SNAPSHOT_PATH.exists():
        _write_snapshot(live)
        if not SNAPSHOT_PATH.exists():
            pytest.fail(
                "snapshot did not exist — written. Re-run the test to confirm."
            )
        return

    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    # Compare tool-by-tool for a useful diff message rather than dumping
    # the whole list when one tool changes.
    live_names = {t["name"] for t in live}
    expected_names = {t["name"] for t in expected}
    added = sorted(live_names - expected_names)
    removed = sorted(expected_names - live_names)

    assert not added, (
        f"new tools added that aren't in the snapshot: {added}. "
        "Run `UPDATE_CONTRACT=1 pytest tests/unit/test_tools_list_contract.py`"
    )
    assert not removed, (
        f"tools removed that ARE in the snapshot: {removed}. "
        "Run `UPDATE_CONTRACT=1 pytest tests/unit/test_tools_list_contract.py`"
    )

    # Per-tool deep equality. List the first 3 differing tools to keep
    # the failure message readable.
    differing = []
    by_name_expected = {t["name"]: t for t in expected}
    for live_tool in live:
        if live_tool != by_name_expected.get(live_tool["name"]):
            differing.append(live_tool["name"])
    assert not differing[:3], (
        f"contract drift in: {differing}. "
        "Run `UPDATE_CONTRACT=1 pytest tests/unit/test_tools_list_contract.py`"
    )
