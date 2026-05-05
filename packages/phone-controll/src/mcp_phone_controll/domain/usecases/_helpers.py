"""Shared use-case helpers — kept tiny, only the things genuinely repeated."""

from __future__ import annotations

from ..failures import NoDeviceSelectedFailure
from ..repositories import SessionStateRepository
from ..result import Err, Result, err, ok


async def resolve_serial(
    explicit: str | None, state: SessionStateRepository
) -> Result[str]:
    if explicit is not None:
        return ok(explicit)
    selected = await state.get_selected_serial()
    if isinstance(selected, Err):
        return selected
    if selected.value is None:
        return err(
            NoDeviceSelectedFailure(
                message="No device selected. Call select_device or pass serial explicitly."
            )
        )
    return ok(selected.value)
