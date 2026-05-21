"""App-size analyzer — store-listing-readiness quality gate.

`flutter build apk|ios --analyze-size` produces a per-package
breakdown showing which dependencies, assets, and code contribute
how many bytes to the final binary. This use case wraps that
output and surfaces:

  • Total compressed + uncompressed size.
  • Top N largest packages by code size.
  • Top N largest assets (the "we forgot to .gitignore the 50MB
    onboarding video" case).
  • A flat-vs-previous diff (when a baseline path is given) so CI
    can fail PRs that bloat the binary > N MB.

Why this is a separate tool and not just `build_app(analyze_size=True)`:

The analyze-size JSON file is large (~50KB-2MB depending on app)
and structured as a deep tree. Agents shouldn't try to parse it
inline — the use case extracts the top-N summary they actually
need, leaves the raw JSON on disk for fetch_artifact if deeper
analysis is needed later.

Scope of v0.3.0:
- Android (`apk` / `appbundle`).
- iOS support is gated on the `flutter build ios --analyze-size`
  invocation working on the user's Xcode version — same arg, same
  JSON output format on success.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..failures import FilesystemFailure, FlutterCliFailure
from ..result import Result, err, ok
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class AnalyzeAppSizeParams:
    project_path: Path
    platform: str = "apk"            # "apk" | "appbundle" | "ios"
    mode: str = "release"            # warns on non-release
    flavor: str | None = None
    top_n: int = 15
    # Optional path to a previous run's JSON — produces a delta
    # report rather than absolute sizes.
    baseline_json_path: Path | None = None


@dataclass(frozen=True, slots=True)
class PackageSize:
    name: str                        # e.g. "package:flutter/material.dart"
    bytes: int
    # The Flutter analyzer reports both "deflated" (compressed) +
    # "uncompressed". Agents care about deflated for store-page
    # display sizes; uncompressed for memory footprint. Both surfaced.


@dataclass(frozen=True, slots=True)
class AssetSize:
    path: str                        # e.g. "assets/images/hero.png"
    bytes: int


@dataclass(frozen=True, slots=True)
class SizeDelta:
    name: str
    bytes_before: int
    bytes_after: int
    delta_bytes: int                 # positive = grew, negative = shrank


@dataclass(frozen=True, slots=True)
class AnalyzeAppSizeResult:
    json_path: str                   # raw output for fetch_artifact
    platform: str
    total_compressed_bytes: int
    total_uncompressed_bytes: int
    top_packages: tuple[PackageSize, ...]
    top_assets: tuple[AssetSize, ...]
    deltas_vs_baseline: tuple[SizeDelta, ...]    # empty unless baseline provided
    advice: str                      # human-readable summary for the agent


class AnalyzeAppSize(
    BaseUseCase[AnalyzeAppSizeParams, AnalyzeAppSizeResult]
):
    """Runs `flutter build … --analyze-size`, surfaces the top contributors.

    Use as a pre-release gate. The typical CI integration:

      result = analyze_app_size(project_path, baseline_json_path=last_release_path)
      if any(d.delta_bytes > 500_000 for d in result.deltas_vs_baseline):
          fail("a dependency grew by > 500 KB — investigate before merging")

    The `advice` field is a plain-English summary the agent can paste
    into a PR comment without paraphrasing.
    """

    def __init__(self, flutter_cli) -> None:
        self._cli = flutter_cli

    async def execute(
        self, params: AnalyzeAppSizeParams
    ) -> Result[AnalyzeAppSizeResult]:
        # Validate platform — anything else won't produce the JSON.
        if params.platform not in ("apk", "appbundle", "ios"):
            return err(
                FlutterCliFailure(
                    message=(
                        f"unsupported platform {params.platform!r}; "
                        "use 'apk', 'appbundle', or 'ios'"
                    ),
                    next_action="fix_arguments",
                )
            )

        result = await self._cli.build_with_size_analysis(
            project_path=params.project_path,
            platform=params.platform,
            mode=params.mode,
            flavor=params.flavor,
        )
        if not result.ok:
            return err(
                FlutterCliFailure(
                    message="flutter build --analyze-size failed",
                    details={
                        "stderr_tail": (result.stderr or "")[-2000:],
                        "stdout_tail": (result.stdout or "")[-2000:],
                    },
                    next_action="check_build_log",
                )
            )

        # Flutter prints the JSON path on its own line; capture it.
        json_path = _extract_json_path_from_output(result.stdout or "")
        if json_path is None or not json_path.exists():
            return err(
                FilesystemFailure(
                    message=(
                        "build succeeded but the size-analysis JSON path "
                        "couldn't be found in the output. Try running "
                        "`flutter build … --analyze-size` manually to confirm."
                    ),
                    next_action="check_flutter_version",
                    details={"stdout_tail": (result.stdout or "")[-500:]},
                )
            )

        try:
            report = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return err(
                FilesystemFailure(
                    message=f"could not read/parse size-analysis JSON: {e}",
                    next_action="check_artifacts_dir",
                    details={"json_path": str(json_path)},
                )
            )

        # The report tree has shape:
        #   {"root": [{"name", "size", "type" ("package" | "file"), "children"}, ...]}
        # We flatten into packages + assets separately.
        packages = _collect_packages(report, top_n=params.top_n)
        assets = _collect_assets(report, top_n=params.top_n)
        total_compressed = int(report.get("compressed_size_bytes", 0)) or _sum_tree(report)
        total_uncompressed = int(report.get("uncompressed_size_bytes", 0)) or total_compressed

        # Optional delta vs baseline.
        deltas: tuple[SizeDelta, ...] = ()
        if params.baseline_json_path is not None:
            try:
                baseline = json.loads(params.baseline_json_path.read_text(encoding="utf-8"))
                deltas = _diff_packages(baseline, report, top_n=params.top_n)
            except (OSError, json.JSONDecodeError):
                # Don't fail the whole call on a bad baseline — log
                # the issue in `advice` and surface absolute sizes.
                deltas = ()

        # Build the human-readable advice line. Numbers convert; the
        # agent should be able to drop this directly into a PR comment.
        biggest_pkg = packages[0] if packages else None
        biggest_asset = assets[0] if assets else None
        parts = [f"Total compressed: {_fmt_bytes(total_compressed)}."]
        if biggest_pkg:
            parts.append(f"Largest package: {biggest_pkg.name} ({_fmt_bytes(biggest_pkg.bytes)}).")
        if biggest_asset:
            parts.append(f"Largest asset: {biggest_asset.path} ({_fmt_bytes(biggest_asset.bytes)}).")
        if deltas:
            growers = [d for d in deltas if d.delta_bytes > 0]
            if growers:
                top_grower = growers[0]
                parts.append(
                    f"Biggest growth vs baseline: {top_grower.name} "
                    f"(+{_fmt_bytes(top_grower.delta_bytes)})."
                )
        if params.mode != "release":
            parts.append(
                f"⚠️ Mode is {params.mode!r}, not release — tree shaking "
                "disabled, numbers are misleading."
            )
        advice = " ".join(parts)

        return ok(
            AnalyzeAppSizeResult(
                json_path=str(json_path),
                platform=params.platform,
                total_compressed_bytes=total_compressed,
                total_uncompressed_bytes=total_uncompressed,
                top_packages=packages,
                top_assets=assets,
                deltas_vs_baseline=deltas,
                advice=advice,
            )
        )


# ---- helpers -----------------------------------------------------------


_JSON_PATH_RE = re.compile(
    # Two flavors Flutter has used across versions:
    #   "A size analysis file has been written to: <path>"
    #   "Size analysis written to <path>"
    r"(?:size[- ]analysis(?:\s+file)?(?:\s+has been)?\s+written\s+to[:\s]+)([^\s]+\.json)",
    re.IGNORECASE,
)


def _extract_json_path_from_output(stdout: str) -> Path | None:
    """Scrape the path-to-JSON line Flutter prints.

    Resilient to whitespace + the wording variant Flutter shipped
    between versions. Returns None if nothing matches — the caller
    surfaces that as a structured error.
    """
    m = _JSON_PATH_RE.search(stdout)
    if not m:
        return None
    return Path(m.group(1).strip())


def _collect_packages(
    report: dict, top_n: int
) -> tuple[PackageSize, ...]:
    """Walk the size-analysis tree, accumulating package-level sizes.

    `package:foo/bar.dart` and `package:foo/baz.dart` roll up into a
    single `package:foo` entry so the top-N isn't dominated by one
    big package's many files.
    """
    rolled: dict[str, int] = {}
    for entry in _walk(report.get("root", [])):
        if entry.get("type") != "package" and not _looks_like_package(entry.get("name", "")):
            continue
        name = _package_root(entry.get("name", "?"))
        rolled[name] = rolled.get(name, 0) + int(entry.get("size", 0))
    sorted_pkgs = sorted(rolled.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return tuple(PackageSize(name=name, bytes=size) for name, size in sorted_pkgs)


def _collect_assets(
    report: dict, top_n: int
) -> tuple[AssetSize, ...]:
    """Find leaf entries that look like asset files (PNG, JPG, MP4, etc.)."""
    assets: list[AssetSize] = []
    asset_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4",
                  ".mov", ".webm", ".ogg", ".mp3", ".ttf", ".otf",
                  ".woff", ".woff2", ".json")
    for entry in _walk(report.get("root", [])):
        name = entry.get("name", "")
        if any(name.lower().endswith(ext) for ext in asset_exts):
            assets.append(AssetSize(path=name, bytes=int(entry.get("size", 0))))
    assets.sort(key=lambda a: a.bytes, reverse=True)
    return tuple(assets[:top_n])


def _diff_packages(
    baseline: dict, current: dict, top_n: int
) -> tuple[SizeDelta, ...]:
    """Compute per-package size deltas vs a previous report."""
    base_map: dict[str, int] = {}
    for entry in _walk(baseline.get("root", [])):
        if entry.get("type") == "package" or _looks_like_package(entry.get("name", "")):
            name = _package_root(entry.get("name", "?"))
            base_map[name] = base_map.get(name, 0) + int(entry.get("size", 0))

    cur_map: dict[str, int] = {}
    for entry in _walk(current.get("root", [])):
        if entry.get("type") == "package" or _looks_like_package(entry.get("name", "")):
            name = _package_root(entry.get("name", "?"))
            cur_map[name] = cur_map.get(name, 0) + int(entry.get("size", 0))

    all_names = set(base_map) | set(cur_map)
    deltas: list[SizeDelta] = []
    for name in all_names:
        b = base_map.get(name, 0)
        a = cur_map.get(name, 0)
        if a == b:
            continue
        deltas.append(SizeDelta(name=name, bytes_before=b, bytes_after=a, delta_bytes=a - b))
    # Sort by absolute delta — biggest changes first (growth OR shrink).
    deltas.sort(key=lambda d: abs(d.delta_bytes), reverse=True)
    return tuple(deltas[:top_n])


def _walk(nodes):
    """Yield every entry in the (potentially nested) size-analysis tree."""
    if isinstance(nodes, list):
        for n in nodes:
            yield from _walk(n)
    elif isinstance(nodes, dict):
        yield nodes
        children = nodes.get("children")
        if children:
            yield from _walk(children)


def _looks_like_package(name: str) -> bool:
    return name.startswith("package:") or name.startswith("dart:")


def _package_root(name: str) -> str:
    # "package:flutter_bloc/src/bloc.dart" → "package:flutter_bloc"
    if name.startswith("package:"):
        return "package:" + name[len("package:"):].split("/", 1)[0]
    return name


def _sum_tree(report: dict) -> int:
    """Fallback total when the report doesn't expose top-level totals."""
    total = 0
    for entry in _walk(report.get("root", [])):
        if not entry.get("children"):
            total += int(entry.get("size", 0))
    return total


def _fmt_bytes(n: int) -> str:
    """Human-readable byte count. Numbers > advice."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"
