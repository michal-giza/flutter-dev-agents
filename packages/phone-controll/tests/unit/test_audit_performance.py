"""Tests for audit_performance — Flutter jank/animation/scroll audit."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_phone_controll.domain.result import Err, Ok
from mcp_phone_controll.domain.usecases.audit_performance import (
    AuditPerformance,
    AuditPerformanceParams,
)


def _project(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


async def _run(tmp_path: Path, files: dict[str, str], **kw):
    proj = _project(tmp_path, files)
    res = await AuditPerformance()(AuditPerformanceParams(project_path=proj, **kw))
    assert isinstance(res, Ok), res
    return res.value


def _rules(result) -> set[str]:
    return {f.rule for f in result.findings}


# ---- HIGH rules ---------------------------------------------------------


@pytest.mark.asyncio
async def test_non_lazy_list_flagged(tmp_path):
    r = await _run(tmp_path, {"lib/feed.dart": """
class Feed extends StatelessWidget {
  Widget build(BuildContext context) {
    return ListView(children: items.map((i) => Tile(i)).toList());
  }
}
"""})
    assert "non_lazy_list" in _rules(r)


@pytest.mark.asyncio
async def test_lazy_list_builder_not_flagged(tmp_path):
    r = await _run(tmp_path, {"lib/feed.dart": """
Widget build(BuildContext context) =>
    ListView.builder(itemCount: n, itemBuilder: (c, i) => Tile(i));
"""})
    assert "non_lazy_list" not in _rules(r)


@pytest.mark.asyncio
async def test_setstate_in_animation_listener(tmp_path):
    r = await _run(tmp_path, {"lib/anim.dart": """
class _S extends State<X> {
  late AnimationController c;
  void initState() {
    c = AnimationController(vsync: this);
    c.addListener(() { setState(() {}); });
  }
  void dispose() { c.dispose(); super.dispose(); }
}
"""})
    assert "setstate_in_animation" in _rules(r)


@pytest.mark.asyncio
async def test_controller_not_disposed(tmp_path):
    r = await _run(tmp_path, {"lib/anim.dart": """
class _S extends State<X> {
  final c = AnimationController(vsync: this);
  Widget build(BuildContext context) => Container();
}
"""})
    assert "controller_not_disposed" in _rules(r)


@pytest.mark.asyncio
async def test_controller_disposed_not_flagged(tmp_path):
    r = await _run(tmp_path, {"lib/anim.dart": """
class _S extends State<X> {
  late AnimationController c = AnimationController(vsync: this);
  void dispose() { c.dispose(); super.dispose(); }
}
"""})
    assert "controller_not_disposed" not in _rules(r)


@pytest.mark.asyncio
async def test_opacity_animated(tmp_path):
    r = await _run(tmp_path, {"lib/fade.dart": """
Widget build(BuildContext context) =>
    Opacity(opacity: _animation.value, child: child);
"""})
    assert "opacity_animated" in _rules(r)


# ---- MEDIUM rules -------------------------------------------------------


@pytest.mark.asyncio
async def test_shrinkwrap_flagged(tmp_path):
    r = await _run(tmp_path, {"lib/x.dart": """
Widget build(BuildContext context) =>
    ListView.builder(shrinkWrap: true, itemBuilder: (c, i) => Tile(i));
"""})
    assert "shrinkwrap_list" in _rules(r)


@pytest.mark.asyncio
async def test_image_without_cache_size(tmp_path):
    r = await _run(tmp_path, {"lib/x.dart": """
Widget build(BuildContext context) => Image.network('https://x/y.png');
"""})
    assert "image_no_cache_size" in _rules(r)


@pytest.mark.asyncio
async def test_image_with_cache_size_not_flagged(tmp_path):
    r = await _run(tmp_path, {"lib/x.dart": """
Widget build(BuildContext context) =>
    Image.network('https://x/y.png', cacheWidth: 200);
"""})
    assert "image_no_cache_size" not in _rules(r)


@pytest.mark.asyncio
async def test_nested_scroll_column(tmp_path):
    r = await _run(tmp_path, {"lib/x.dart": """
Widget build(BuildContext context) => SingleChildScrollView(
  child: Column(children: [...items.map((i) => Tile(i))]),
);
"""})
    assert "nested_scroll_column" in _rules(r)


@pytest.mark.asyncio
async def test_heavy_work_in_build(tmp_path):
    r = await _run(tmp_path, {"lib/x.dart": """
Widget build(BuildContext context) {
  final sorted = items.sort((a, b) => a.compareTo(b));
  return Text(sorted.toString());
}
"""})
    assert "heavy_work_in_build" in _rules(r)


# ---- LOW rules ----------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_repaint_boundary(tmp_path):
    r = await _run(tmp_path, {"lib/p.dart": """
Widget build(BuildContext context) =>
    AnimatedBuilder(animation: a, builder: (c, _) => CustomPaint(painter: P()));
"""})
    assert "missing_repaint_boundary" in _rules(r)


@pytest.mark.asyncio
async def test_repaint_boundary_present_not_flagged(tmp_path):
    r = await _run(tmp_path, {"lib/p.dart": """
Widget build(BuildContext context) => RepaintBoundary(
  child: AnimatedBuilder(animation: a, builder: (c, _) => CustomPaint()),
);
"""})
    assert "missing_repaint_boundary" not in _rules(r)


@pytest.mark.asyncio
async def test_implicit_anim_zero(tmp_path):
    r = await _run(tmp_path, {"lib/x.dart": """
Widget build(BuildContext context) =>
    AnimatedContainer(duration: Duration.zero, color: c);
"""})
    assert "implicit_anim_zero" in _rules(r)


# ---- grade + plumbing ---------------------------------------------------


@pytest.mark.asyncio
async def test_clean_project_grades_smooth(tmp_path):
    r = await _run(tmp_path, {"lib/x.dart": """
Widget build(BuildContext context) =>
    ListView.builder(itemCount: n, itemBuilder: (c, i) => const Tile());
"""})
    assert r.grade == "smooth"
    assert r.findings == ()


@pytest.mark.asyncio
async def test_janky_project_grades_down(tmp_path):
    r = await _run(tmp_path, {"lib/x.dart": """
Widget build(BuildContext context) {
  return ListView(children: [
    Opacity(opacity: _animation.value, child: Image.network('x')),
  ]);
}
"""})
    assert r.grade in ("janky", "severe")
    assert r.findings_by_category.get("scroll", 0) >= 1
    assert r.findings_by_category.get("animation", 0) >= 1


@pytest.mark.asyncio
async def test_generated_and_test_files_skipped(tmp_path):
    r = await _run(tmp_path, {
        "lib/x.g.dart": "ListView(children: [Tile()]);",
        "test/x_test.dart": "ListView(children: [Tile()]);",
    })
    assert r.findings == ()
    assert r.files_scanned == 0


@pytest.mark.asyncio
async def test_min_severity_filter(tmp_path):
    files = {"lib/p.dart": """
Widget build(BuildContext context) =>
    AnimatedBuilder(animation: a, builder: (c, _) => CustomPaint());
"""}
    # LOW finding present at default
    r_low = await _run(tmp_path, files)
    assert "missing_repaint_boundary" in _rules(r_low)
    # filtered out at min_severity=high
    r_high = await _run(tmp_path, files, min_severity="high")
    assert "missing_repaint_boundary" not in _rules(r_high)


@pytest.mark.asyncio
async def test_missing_project_path_errors(tmp_path):
    res = await AuditPerformance()(
        AuditPerformanceParams(project_path=tmp_path / "nope")
    )
    assert isinstance(res, Err)
    assert res.failure.next_action == "fix_arguments"
