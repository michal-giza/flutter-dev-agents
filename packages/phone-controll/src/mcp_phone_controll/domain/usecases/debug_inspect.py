"""DAP-lite use cases — inspect Dart VM state via the VM service WebSocket.

For agents producing quality code: when something goes wrong, evaluate state
at the breakpoint or top-of-stack to decide the fix. Connects to the VM
service URI exposed by start_debug_session — no separate boot required.

`websockets` is an optional dependency (the [debug] extra). If missing, every
tool here returns a typed failure with next_action: install_debug_extras.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..failures import DebugSessionFailure
from ..repositories import DebugSessionRepository
from ..result import Err, Result, err, ok
from .base import BaseUseCase


@dataclass(frozen=True, slots=True)
class VmListIsolatesParams:
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class IsolateInfo:
    id: str
    name: str
    runnable: bool


class VmListIsolates(BaseUseCase[VmListIsolatesParams, list[IsolateInfo]]):
    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(
        self, params: VmListIsolatesParams
    ) -> Result[list[IsolateInfo]]:
        sessions_res = await self._repo.list_sessions()
        if isinstance(sessions_res, Err):
            return sessions_res
        sessions = sessions_res.value
        target = None
        if params.session_id:
            for s in sessions:
                if s.id == params.session_id:
                    target = s
                    break
        elif sessions:
            target = sessions[-1]
        if target is None or not target.vm_service_uri:
            return err(
                DebugSessionFailure(
                    message="no active debug session with a vm_service_uri",
                    next_action="start_debug_session",
                )
            )
        return await _with_vm(target.vm_service_uri, _list_isolates)


@dataclass(frozen=True, slots=True)
class VmEvaluateParams:
    expression: str
    isolate_id: str | None = None
    frame_index: int = 0
    session_id: str | None = None


class VmEvaluate(BaseUseCase[VmEvaluateParams, dict]):
    """Evaluate a Dart expression at frame_index of the given isolate.

    If isolate_id is omitted, picks the first runnable isolate.
    """

    def __init__(self, repo: DebugSessionRepository) -> None:
        self._repo = repo

    async def execute(self, params: VmEvaluateParams) -> Result[dict]:
        sessions_res = await self._repo.list_sessions()
        if isinstance(sessions_res, Err):
            return sessions_res
        sessions = sessions_res.value
        target = None
        if params.session_id:
            for s in sessions:
                if s.id == params.session_id:
                    target = s
                    break
        elif sessions:
            target = sessions[-1]
        if target is None or not target.vm_service_uri:
            return err(
                DebugSessionFailure(
                    message="no active debug session with a vm_service_uri",
                    next_action="start_debug_session",
                )
            )
        return await _with_vm(
            target.vm_service_uri,
            _evaluate,
            isolate_id=params.isolate_id,
            frame_index=params.frame_index,
            expression=params.expression,
        )


# ---- internal helpers --------------------------------------------------


async def _with_vm(uri: str, op, **kwargs) -> Result[dict]:
    from ...infrastructure.vm_service_client import VmServiceClient

    try:
        client = VmServiceClient(uri)
        await client.connect()
    except ImportError as e:
        return err(
            DebugSessionFailure(
                message=str(e),
                next_action="install_debug_extras",
                details={"hint": "uv pip install -e \".[debug]\""},
            )
        )
    except Exception as e:  # noqa: BLE001
        return err(
            DebugSessionFailure(
                message=f"failed to connect to VM service: {e}",
                next_action="check_debug_session",
            )
        )
    try:
        return await op(client, **kwargs)
    finally:
        await client.close()


async def _list_isolates(client) -> Result[list[IsolateInfo]]:
    response = await client.get_vm()
    if "error" in response:
        return err(
            DebugSessionFailure(
                message=str(response["error"]),
                details={"response": response},
            )
        )
    result = response.get("result") or {}
    out: list[IsolateInfo] = []
    for iso in result.get("isolates") or []:
        out.append(
            IsolateInfo(
                id=str(iso.get("id", "")),
                name=str(iso.get("name", "")),
                runnable=bool(iso.get("runnable", False)),
            )
        )
    return ok(out)


async def _evaluate(
    client,
    isolate_id: str | None,
    frame_index: int,
    expression: str,
) -> Result[dict]:
    if isolate_id is None:
        vm = await client.get_vm()
        isolates = (vm.get("result") or {}).get("isolates") or []
        runnable = next((i for i in isolates if i.get("runnable")), None)
        if not runnable:
            return err(
                DebugSessionFailure(
                    message="no runnable isolate",
                    next_action="check_debug_session",
                )
            )
        isolate_id = str(runnable["id"])
    response = await client.evaluate_in_frame(isolate_id, frame_index, expression)
    if "error" in response:
        return err(
            DebugSessionFailure(
                message=str(response["error"]),
                details={"response": response, "expression": expression},
            )
        )
    return ok(
        {
            "isolate_id": isolate_id,
            "expression": expression,
            "result": response.get("result"),
        }
    )
