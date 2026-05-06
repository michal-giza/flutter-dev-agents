"""Capability discovery + session reflection — autonomy primitives."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..entities import CapabilityReport, SessionTrace
from ..failures import InvalidArgumentFailure
from ..repositories import CapabilitiesProvider, SessionTraceRepository
from ..result import Err, Result, err, ok
from ..tool_levels import tools_for_level
from .base import BaseUseCase, NoParams


@dataclass(frozen=True, slots=True)
class DescribeCapabilitiesParams:
    level: str = "expert"


class DescribeCapabilities(
    BaseUseCase[DescribeCapabilitiesParams, CapabilityReport]
):
    """Returns capabilities + the tool subset for the requested level.

    The tool subset is computed from the dispatcher's full list of tool names,
    injected as `all_tool_names_provider` (a no-arg callable). Keeps the level
    filter consistent with whatever's actually registered.
    """

    def __init__(
        self,
        provider: CapabilitiesProvider,
        all_tool_names_provider=None,
    ) -> None:
        self._provider = provider
        self._all_tool_names_provider = all_tool_names_provider

    async def execute(
        self, params: DescribeCapabilitiesParams
    ) -> Result[CapabilityReport]:
        report_res = await self._provider.describe()
        if isinstance(report_res, Err):
            return report_res
        all_names: tuple[str, ...] = ()
        if self._all_tool_names_provider is not None:
            try:
                all_names = tuple(self._all_tool_names_provider())
            except Exception:  # noqa: BLE001
                all_names = ()
        subset = tools_for_level(params.level, all_names)
        return ok(
            replace(
                report_res.value,
                tool_subset=subset,
                level=params.level,
            )
        )


@dataclass(frozen=True, slots=True)
class SessionSummaryParams:
    session_id: str | None = None


class SessionSummary(BaseUseCase[SessionSummaryParams, SessionTrace]):
    def __init__(self, traces: SessionTraceRepository) -> None:
        self._traces = traces

    async def execute(self, params: SessionSummaryParams) -> Result[SessionTrace]:
        return await self._traces.summary(params.session_id)


@dataclass(frozen=True, slots=True)
class DescribeToolParams:
    name: str


@dataclass(frozen=True, slots=True)
class ToolDetail:
    name: str
    description: str
    input_schema: dict
    example: dict


@dataclass(frozen=True, slots=True)
class ToolUsageRow:
    name: str
    calls: int
    errors: int
    error_rate: float


@dataclass(frozen=True, slots=True)
class ToolUsageReport:
    total_calls: int
    by_tool: tuple[ToolUsageRow, ...]
    dead_tools: tuple[str, ...]
    top_errors: tuple[ToolUsageRow, ...]


@dataclass(frozen=True, slots=True)
class ToolUsageReportParams:
    session_id: str | None = None
    top_n: int = 10


class ToolUsageReportUseCase(BaseUseCase[ToolUsageReportParams, ToolUsageReport]):
    """Aggregate the session trace into a per-tool usage report.

    Surfaces:
      - dead tools (registered but never called this session) — candidates
        for trimming or for description rewrites,
      - per-tool error rate — early signal of agent confusion or schema drift,
      - top-N called tools — concentration check.
    """

    def __init__(
        self,
        traces: SessionTraceRepository,
        all_tool_names_provider=None,
    ) -> None:
        self._traces = traces
        self._all_tool_names_provider = all_tool_names_provider

    async def execute(
        self, params: ToolUsageReportParams
    ) -> Result[ToolUsageReport]:
        summary_res = await self._traces.summary(params.session_id)
        if isinstance(summary_res, Err):
            return summary_res
        entries = summary_res.value.entries
        counts: dict[str, int] = {}
        errors: dict[str, int] = {}
        for entry in entries:
            counts[entry.tool_name] = counts.get(entry.tool_name, 0) + 1
            if not entry.ok:
                errors[entry.tool_name] = errors.get(entry.tool_name, 0) + 1
        rows = tuple(
            ToolUsageRow(
                name=name,
                calls=calls,
                errors=errors.get(name, 0),
                error_rate=(errors.get(name, 0) / calls) if calls else 0.0,
            )
            for name, calls in sorted(
                counts.items(), key=lambda p: p[1], reverse=True
            )
        )
        dead: tuple[str, ...] = ()
        if self._all_tool_names_provider is not None:
            try:
                all_names = set(self._all_tool_names_provider())
            except Exception:  # noqa: BLE001
                all_names = set()
            seen = set(counts.keys())
            dead = tuple(sorted(all_names - seen))
        top_errors = tuple(
            sorted(
                (r for r in rows if r.errors > 0),
                key=lambda r: (r.errors, r.error_rate),
                reverse=True,
            )[: params.top_n]
        )
        return ok(
            ToolUsageReport(
                total_calls=len(entries),
                by_tool=rows[: params.top_n],
                dead_tools=dead,
                top_errors=top_errors,
            )
        )


class DescribeTool(BaseUseCase[DescribeToolParams, ToolDetail]):
    """Full description + JSONSchema + corrected example for one tool.

    Lets small LLMs fetch verbose docs only for the tool they're about to
    call, instead of carrying every tool's prose in context.
    """

    def __init__(self, descriptor_lookup) -> None:
        # descriptor_lookup: callable name -> {name, description, input_schema}
        self._lookup = descriptor_lookup

    async def execute(self, params: DescribeToolParams) -> Result[ToolDetail]:
        descriptor = self._lookup(params.name)
        if descriptor is None:
            return err(
                InvalidArgumentFailure(
                    message=f"unknown tool: {params.name!r}",
                    next_action="describe_capabilities",
                )
            )
        # Local import to avoid circular dependency between domain and presentation.
        from ...presentation.argument_coercion import corrected_example

        return ok(
            ToolDetail(
                name=descriptor["name"],
                description=descriptor["description"],
                input_schema=descriptor["input_schema"],
                example=corrected_example(descriptor["input_schema"] or {}),
            )
        )
