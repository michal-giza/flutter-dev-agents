"""DebugSessionStore — durable JSON registry of debug sessions (v0.16.0)."""

from __future__ import annotations

from mcp_phone_controll.infrastructure.debug_session_store import DebugSessionStore


def test_missing_file_loads_empty(tmp_path):
    store = DebugSessionStore(tmp_path / "nope.json")
    assert store.load() == []


def test_upsert_and_load_round_trip(tmp_path):
    store = DebugSessionStore(tmp_path / "ds.json")
    store.upsert({"id": "a", "vm_service_uri": "ws://x/ws"})
    store.upsert({"id": "b", "vm_service_uri": "ws://y/ws"})
    ids = {r["id"] for r in store.load()}
    assert ids == {"a", "b"}


def test_upsert_replaces_same_id(tmp_path):
    store = DebugSessionStore(tmp_path / "ds.json")
    store.upsert({"id": "a", "vm_service_uri": "ws://old/ws"})
    store.upsert({"id": "a", "vm_service_uri": "ws://new/ws"})
    recs = store.load()
    assert len(recs) == 1
    assert recs[0]["vm_service_uri"] == "ws://new/ws"


def test_remove(tmp_path):
    store = DebugSessionStore(tmp_path / "ds.json")
    store.upsert({"id": "a"})
    store.upsert({"id": "b"})
    store.remove("a")
    assert {r["id"] for r in store.load()} == {"b"}


def test_persists_across_instances(tmp_path):
    """A NEW store instance (== an MCP restart) sees prior records."""
    path = tmp_path / "ds.json"
    DebugSessionStore(path).upsert({"id": "a", "vm_service_uri": "ws://x/ws"})
    revived = DebugSessionStore(path).load()
    assert [r["id"] for r in revived] == ["a"]


def test_corrupt_file_loads_empty(tmp_path):
    path = tmp_path / "ds.json"
    path.write_text("{ not json", encoding="utf-8")
    assert DebugSessionStore(path).load() == []


def test_records_without_id_are_dropped(tmp_path):
    path = tmp_path / "ds.json"
    path.write_text('[{"vm_service_uri": "ws://x"}, {"id": "keep"}]', encoding="utf-8")
    assert [r["id"] for r in DebugSessionStore(path).load()] == ["keep"]
