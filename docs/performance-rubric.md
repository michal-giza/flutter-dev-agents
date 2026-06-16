# Performance Rubric — `audit_performance`

> Static jank audit for Flutter. The gap no first-party MCP fills:
> Google's `dart mcp-server` does analyze/fix/inspector but **no
> performance/animation judgment**; Maestro and the browser MCPs don't
> do Flutter static analysis. Pure compute over `lib/` — no device, no
> VM, model-agnostic. (v0.9.0)

It scans the three things that actually drop frames in Flutter —
**animations**, **scroll/virtualization**, and **rebuild cost** — at the
precision a regex can credibly hit without an AST. For *runtime* jank
(actual frame timings), use `ingest_frame_timeline` (mobile VM Timeline
/ web Chrome trace); this is the static, pre-run complement.

## The 10 rules

### HIGH — drops frames

| Rule | Category | What |
|---|---|---|
| `non_lazy_list` | scroll | `ListView(children:)` / `GridView(children:)` default ctor builds every child up front — janks on long/dynamic lists. Use `.builder`. |
| `setstate_in_animation` | animation | `setState()` inside an animation listener rebuilds the whole subtree every frame. Use `AnimatedBuilder`. |
| `controller_not_disposed` | animation | `AnimationController` created but the file has no `dispose()` — ticker leak + jank. |
| `opacity_animated` | animation | `Opacity(opacity: <animation>)` repaints the subtree each frame. Use `FadeTransition` / `AnimatedOpacity`. |

### MEDIUM — likely jank

| Rule | Category | What |
|---|---|---|
| `shrinkwrap_list` | scroll | `shrinkWrap: true` lays out all children at once — defeats virtualization. |
| `nested_scroll_column` | scroll | `SingleChildScrollView` + `Column` rendering a dynamic list (`...`/`.map`) — not lazy. |
| `image_no_cache_size` | rebuild | `Image.network/asset/file` without `cacheWidth`/`cacheHeight` decodes at full resolution. |
| `heavy_work_in_build` | rebuild | `.sort()/.where()/.map()/.reduce()` inside `build()` re-runs every rebuild. |

### LOW — polish

| Rule | Category | What |
|---|---|---|
| `missing_repaint_boundary` | animation | File animates (`AnimationController`/`AnimatedBuilder`/`CustomPaint`) but has no `RepaintBoundary` to isolate repaints. |
| `implicit_anim_zero` | animation | Implicit animation with `Duration.zero` animates nothing — likely a bug. |

## Grade

```
>= 5 HIGH  OR  score >= 12   → severe
>= 1 HIGH  OR  score >= 4    → janky
score >= 1                   → acceptable
otherwise                    → smooth
no dart files                → smooth
```

`score` = weighted findings per KLOC (HIGH=6, MEDIUM=2, LOW=1). Same
weighted-per-KLOC shape as `audit_security`, so density — not raw count —
drives the grade.

## Composite

`audit_release_readiness` includes a **performance** domain (default-on,
`include_performance=True`, `weight_performance=1.5`). Grade → score:
`smooth=100 / acceptable=80 / janky=45 / severe=15`.

## What this is NOT

- **Not a profiler.** It can't measure real frame times — that's
  `ingest_frame_timeline` (runtime). This flags patterns *before* you run.
- **Not the linter.** We skip `const`/style nits `flutter analyze` owns.
- **Not an AST.** Regex over text; false negatives on indirection
  (a list built in a helper, an opacity driven through a getter).
- **`non_lazy_list` is a heuristic.** A short *fixed* list as
  `ListView(children:)` is fine; we can't measure length statically, so
  treat HIGH here as "confirm this list is bounded," not "always wrong."

## Field calibration (bike_news_room/frontend)

111 files / ~21k LOC → grade `janky` (score 2.0), 17 findings:
3 `non_lazy_list`, 5 `nested_scroll_column`, 3 `heavy_work_in_build`,
2 `image_no_cache_size`, 4 `missing_repaint_boundary`. Reasonable signal
density (≈0.8 findings/KLOC) — surfaces real scroll/rebuild work without
drowning the report.
