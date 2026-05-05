"""SessionStateRepository — in-memory holder of the selected device serial."""

from __future__ import annotations

from ...domain.repositories import SessionStateRepository
from ...domain.result import Result, ok


class InMemorySessionStateRepository(SessionStateRepository):
    def __init__(self) -> None:
        self._serial: str | None = None

    async def set_selected_serial(self, serial: str | None) -> Result[None]:
        self._serial = serial
        return ok(None)

    async def get_selected_serial(self) -> Result[str | None]:
        return ok(self._serial)
