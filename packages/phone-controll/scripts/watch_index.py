"""Watch a project tree and re-index changed files into Qdrant.

Reuses `index_project`'s chunker + repo, but on a debounced watcher
loop driven by `watchdog`. Run alongside the MCP server while you edit;
recall queries stay current.

Usage:

    pip install watchdog                                  # one-time
    python -m scripts.watch_index /path/to/flutter/project
    python -m scripts.watch_index /path/to/proj --collection my-app

Stop with Ctrl-C. Skips re-indexing during the same debounce window if
multiple files change in quick succession (e.g. saving a Flutter
project triggers .dart_tool churn).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path


_DEFAULT_DEBOUNCE_S = 1.5
_INDEXABLE_SUFFIXES = {".md", ".dart", ".py", ".yaml", ".yml"}


def _watchdog_available() -> bool:
    try:
        import watchdog  # noqa: F401
        return True
    except ImportError:
        return False


async def _index_once(project: Path, collection: str) -> None:
    """Run one full `index_project` pass through the same use case the
    MCP exposes. Reuses every guard the in-tree pipeline ships with."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from mcp_phone_controll.container import build_runtime
    from mcp_phone_controll.domain.usecases.recall import IndexProjectParams

    use_cases, _ = build_runtime()
    res = await use_cases.index_project.execute(
        IndexProjectParams(project_path=project, collection=collection)
    )
    if res.is_ok:
        s = res.value
        print(
            f"[watch_index] indexed {s.chunks_indexed} chunks across "
            f"{s.files_indexed} files into {s.collection}"
        )
    else:
        f = res.failure
        print(
            f"[watch_index] index failed: {f.code}: {f.message} "
            f"(next: {f.next_action})",
            file=sys.stderr,
        )


def _run(project: Path, collection: str, debounce_s: float) -> int:
    if not _watchdog_available():
        print(
            "watchdog not installed. Run: uv pip install watchdog",
            file=sys.stderr,
        )
        return 2
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    pending = {"at": 0.0}
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory:
                return
            path = Path(event.src_path)
            if path.suffix.lower() not in _INDEXABLE_SUFFIXES:
                return
            pending["at"] = time.monotonic() + debounce_s

    handler = _Handler()
    observer = Observer()
    observer.schedule(handler, str(project), recursive=True)
    observer.start()
    print(f"[watch_index] watching {project} → collection={collection!r}")
    print("[watch_index] indexing once at startup, then on every save…")

    try:
        loop.run_until_complete(_index_once(project, collection))
        while True:
            time.sleep(0.4)
            now = time.monotonic()
            if pending["at"] and now >= pending["at"]:
                pending["at"] = 0.0
                loop.run_until_complete(_index_once(project, collection))
    except KeyboardInterrupt:
        print("\n[watch_index] stopped.")
    finally:
        observer.stop()
        observer.join()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path, help="Project root to watch.")
    ap.add_argument(
        "--collection",
        default="phone-controll-default",
        help="Qdrant collection name.",
    )
    ap.add_argument(
        "--debounce-s",
        type=float,
        default=_DEFAULT_DEBOUNCE_S,
        help="Seconds to wait after the last file event before re-indexing.",
    )
    args = ap.parse_args()
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"not a directory: {project}", file=sys.stderr)
        return 2
    return _run(project, args.collection, args.debounce_s)


if __name__ == "__main__":
    sys.exit(main())
