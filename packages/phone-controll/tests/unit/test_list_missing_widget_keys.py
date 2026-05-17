"""list_missing_widget_keys — Flutter selector-hygiene diagnostic.

Per the research (Drizz May 2026), 30-50% of Flutter QA time goes
to selector maintenance. This tool surfaces the highest-leverage
fix: tap-target widgets without Keys. Tests verify:
  - widgets with `key:` are not flagged
  - widgets without `key:` ARE flagged
  - widgets matched even in trailing-comma / multi-line style
  - rationale string reflects findings vs all-green
  - custom target_widgets honored
  - missing lib/ → check_path failure
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.usecases.productivity import (
    ListMissingWidgetKeys,
    ListMissingWidgetKeysParams,
)


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a minimal `<tmp>/proj/lib/` with the given dart files."""
    proj = tmp_path / "proj"
    lib = proj / "lib"
    lib.mkdir(parents=True)
    for name, content in files.items():
        target = lib / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return proj


@pytest.mark.asyncio
async def test_flags_button_without_key(tmp_path: Path):
    proj = _make_project(tmp_path, {
        "page.dart": (
            "class P extends StatelessWidget {\n"
            "  Widget build(BuildContext c) =>\n"
            "    ElevatedButton(\n"
            "      onPressed: () {},\n"
            "      child: Text('Go'),\n"
            "    );\n"
            "}\n"
        ),
    })
    res = await ListMissingWidgetKeys().execute(
        ListMissingWidgetKeysParams(project_path=proj)
    )
    assert res.is_ok
    out = res.value
    assert len(out.findings) == 1
    assert out.findings[0].widget == "ElevatedButton"
    assert out.findings[0].path == "lib/page.dart"
    assert "Drizz" in out.rationale  # cites the research that motivated this


@pytest.mark.asyncio
async def test_does_not_flag_button_with_key(tmp_path: Path):
    proj = _make_project(tmp_path, {
        "page.dart": (
            "class P extends StatelessWidget {\n"
            "  Widget build(BuildContext c) =>\n"
            "    ElevatedButton(\n"
            "      key: const Key('go-btn'),\n"
            "      onPressed: () {},\n"
            "      child: Text('Go'),\n"
            "    );\n"
            "}\n"
        ),
    })
    res = await ListMissingWidgetKeys().execute(
        ListMissingWidgetKeysParams(project_path=proj)
    )
    assert res.is_ok
    assert len(res.value.findings) == 0
    assert "stable" in res.value.rationale


@pytest.mark.asyncio
async def test_handles_single_line_construction(tmp_path: Path):
    """Inline `Button(onPressed: …, child: …)` with no key on a single
    line — the rolling 6-line peek must still match."""
    proj = _make_project(tmp_path, {
        "page.dart": (
            "Widget _row() => Row(children: [\n"
            "  IconButton(icon: Icon(Icons.add), onPressed: () {}),\n"
            "  IconButton(key: Key('subtract'), icon: Icon(Icons.remove), onPressed: () {}),\n"
            "]);\n"
        ),
    })
    res = await ListMissingWidgetKeys().execute(
        ListMissingWidgetKeysParams(project_path=proj)
    )
    assert res.is_ok
    out = res.value
    # First IconButton has no key → flagged; second has key: → not.
    assert len(out.findings) == 1
    assert out.findings[0].widget == "IconButton"
    assert "add" in out.findings[0].snippet.lower() or "icons.add" in out.findings[0].snippet.lower()


@pytest.mark.asyncio
async def test_custom_target_widgets_filter(tmp_path: Path):
    """Override the default widget set — only scan for `TextField`."""
    proj = _make_project(tmp_path, {
        "page.dart": (
            "Widget _build() => Column(children: [\n"
            "  ElevatedButton(onPressed: () {}, child: Text('A')),\n"
            "  TextField(decoration: InputDecoration(labelText: 'Name')),\n"
            "]);\n"
        ),
    })
    res = await ListMissingWidgetKeys().execute(
        ListMissingWidgetKeysParams(
            project_path=proj, target_widgets=("TextField",)
        )
    )
    assert res.is_ok
    out = res.value
    # ElevatedButton ignored — we asked for TextField only.
    assert all(f.widget == "TextField" for f in out.findings)
    assert len(out.findings) == 1


@pytest.mark.asyncio
async def test_rejects_missing_lib_dir(tmp_path: Path):
    proj = tmp_path / "no_lib"
    proj.mkdir()
    res = await ListMissingWidgetKeys().execute(
        ListMissingWidgetKeysParams(project_path=proj)
    )
    assert not res.is_ok
    assert res.failure.next_action == "check_path"


@pytest.mark.asyncio
async def test_respects_max_results(tmp_path: Path):
    """Generate 5 unkeyed buttons but cap at 2."""
    body = "Widget _w() => Column(children: [\n"
    for i in range(5):
        body += f"  ElevatedButton(onPressed: () {{}}, child: Text('{i}')),\n"
    body += "]);\n"
    proj = _make_project(tmp_path, {"page.dart": body})
    res = await ListMissingWidgetKeys().execute(
        ListMissingWidgetKeysParams(project_path=proj, max_results=2)
    )
    assert res.is_ok
    out = res.value
    assert len(out.findings) == 2
    assert out.truncated is True
