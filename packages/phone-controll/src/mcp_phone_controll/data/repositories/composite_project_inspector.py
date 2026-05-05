"""Composite ProjectInspector — tries each registered inspector in order.

Adding support for a new stack (RN, native iOS, web) is just appending another
inspector to the list passed in.
"""

from __future__ import annotations

from pathlib import Path

from ...domain.entities import ProjectInfo, ProjectType
from ...domain.repositories import ProjectInspector
from ...domain.result import Err, Result, ok


class CompositeProjectInspector(ProjectInspector):
    def __init__(self, inspectors: list[ProjectInspector]) -> None:
        self._inspectors = inspectors

    async def inspect(self, project_path: Path) -> Result[ProjectInfo]:
        last_error: Result[ProjectInfo] | None = None
        for inspector in self._inspectors:
            res = await inspector.inspect(project_path)
            if isinstance(res, Err):
                last_error = res
                continue
            if res.value.type is not ProjectType.UNKNOWN:
                return res
            last_error = res
        return last_error or ok(
            ProjectInfo(path=project_path, type=ProjectType.UNKNOWN, test_frameworks=())
        )
