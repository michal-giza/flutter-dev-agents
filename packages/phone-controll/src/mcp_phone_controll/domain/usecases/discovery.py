"""Capability discovery + session reflection — autonomy primitives."""

from __future__ import annotations

from dataclasses import dataclass

from ..entities import CapabilityReport, SessionTrace
from ..repositories import CapabilitiesProvider, SessionTraceRepository
from ..result import Result
from .base import BaseUseCase, NoParams


class DescribeCapabilities(BaseUseCase[NoParams, CapabilityReport]):
    def __init__(self, provider: CapabilitiesProvider) -> None:
        self._provider = provider

    async def execute(self, params: NoParams) -> Result[CapabilityReport]:
        return await self._provider.describe()


@dataclass(frozen=True, slots=True)
class SessionSummaryParams:
    session_id: str | None = None


class SessionSummary(BaseUseCase[SessionSummaryParams, SessionTrace]):
    def __init__(self, traces: SessionTraceRepository) -> None:
        self._traces = traces

    async def execute(self, params: SessionSummaryParams) -> Result[SessionTrace]:
        return await self._traces.summary(params.session_id)
