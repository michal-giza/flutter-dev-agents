"""YAML loader for v1 TestPlan documents.

Schema (v1):
    apiVersion: phone-controll/v1
    kind: TestPlan
    metadata: { name: <str> }
    spec:
      device:    { platform: android|ios|null, pool: <str> }
      project:   { path: <str> }
      phases:    [ <PlanPhase>, ... ]
      report:    { format: junit|json|null }
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..domain.entities import PhaseDriver, PlanPhase, TestPlan
from ..domain.failures import InvalidArgumentFailure
from ..domain.result import Result, err, ok


_API = "phone-controll/v1"
_KIND = "TestPlan"


class YamlPlanLoader:
    def load_path(self, path: Path) -> Result[TestPlan]:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as e:
            return err(
                InvalidArgumentFailure(
                    message=f"cannot read plan file: {e}",
                    next_action="fix_arguments",
                )
            )
        return self.load_str(text)

    def load_str(self, source: str) -> Result[TestPlan]:
        try:
            doc = yaml.safe_load(source)
        except yaml.YAMLError as e:
            return err(
                InvalidArgumentFailure(
                    message=f"YAML parse error: {e}", next_action="fix_arguments"
                )
            )
        if not isinstance(doc, dict):
            return err(
                InvalidArgumentFailure(
                    message="plan must be a mapping", next_action="fix_arguments"
                )
            )
        if doc.get("apiVersion") != _API:
            return err(
                InvalidArgumentFailure(
                    message=f"unsupported apiVersion (expect {_API!r})",
                    next_action="fix_arguments",
                )
            )
        if doc.get("kind") != _KIND:
            return err(
                InvalidArgumentFailure(
                    message=f"unsupported kind (expect {_KIND!r})",
                    next_action="fix_arguments",
                )
            )
        meta = doc.get("metadata", {}) or {}
        spec = doc.get("spec", {}) or {}
        if not isinstance(meta, dict) or not isinstance(spec, dict):
            return err(
                InvalidArgumentFailure(
                    message="metadata and spec must be mappings",
                    next_action="fix_arguments",
                )
            )
        name = meta.get("name")
        if not isinstance(name, str) or not name:
            return err(
                InvalidArgumentFailure(
                    message="metadata.name is required",
                    next_action="fix_arguments",
                )
            )

        device = spec.get("device") or {}
        project = spec.get("project") or {}
        phases_raw = spec.get("phases") or []
        report = spec.get("report") or {}

        if not isinstance(phases_raw, list) or not phases_raw:
            return err(
                InvalidArgumentFailure(
                    message="spec.phases must be a non-empty list",
                    next_action="fix_arguments",
                )
            )

        phases: list[PlanPhase] = []
        for idx, raw in enumerate(phases_raw):
            if not isinstance(raw, dict):
                return err(
                    InvalidArgumentFailure(
                        message=f"phase[{idx}] must be a mapping",
                        next_action="fix_arguments",
                    )
                )
            phase_name = raw.get("phase")
            if not isinstance(phase_name, str) or not phase_name:
                return err(
                    InvalidArgumentFailure(
                        message=f"phase[{idx}].phase is required",
                        next_action="fix_arguments",
                    )
                )
            driver_raw = raw.get("driver")
            driver = None
            if isinstance(driver_raw, dict):
                kind = driver_raw.get("kind")
                if not isinstance(kind, str):
                    return err(
                        InvalidArgumentFailure(
                            message=f"phase[{idx}].driver.kind is required",
                            next_action="fix_arguments",
                        )
                    )
                driver = PhaseDriver(
                    kind=kind,
                    target=driver_raw.get("target"),
                    args={k: v for k, v in driver_raw.items() if k not in ("kind", "target")},
                )
            capture = raw.get("capture") or ()
            if isinstance(capture, str):
                capture = (capture,)
            else:
                capture = tuple(capture)
            known_keys = {
                "phase", "driver", "planned_outcome", "package_id", "project_path",
                "wait_for_key", "wait_for_text", "timeout_s", "capture", "notes",
            }
            extras = {k: v for k, v in raw.items() if k not in known_keys}
            phases.append(
                PlanPhase(
                    phase=phase_name,
                    driver=driver,
                    planned_outcome=raw.get("planned_outcome"),
                    package_id=raw.get("package_id"),
                    project_path=raw.get("project_path"),
                    wait_for_key=raw.get("wait_for_key"),
                    wait_for_text=raw.get("wait_for_text"),
                    timeout_s=raw.get("timeout_s"),
                    capture=capture,
                    notes=raw.get("notes"),
                    extras=extras,
                )
            )

        proj_path_raw = project.get("path") if isinstance(project, dict) else None
        return ok(
            TestPlan(
                api_version=_API,
                kind=_KIND,
                name=name,
                device_platform=(device.get("platform") if isinstance(device, dict) else None),
                device_pool=(device.get("pool") if isinstance(device, dict) else None),
                project_path=Path(proj_path_raw) if proj_path_raw else None,
                phases=tuple(phases),
                report_format=(report.get("format") if isinstance(report, dict) else None),
            )
        )
