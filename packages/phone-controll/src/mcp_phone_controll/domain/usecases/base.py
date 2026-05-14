"""BaseUseCase: every use case takes typed Params and returns Result[T]."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from ..failures import UnexpectedFailure
from ..result import Err, Result

P = TypeVar("P")
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class NoParams:
    pass


class BaseUseCase(ABC, Generic[P, T]):
    @abstractmethod
    async def execute(self, params: P) -> Result[T]: ...

    async def __call__(self, params: P) -> Result[T]:
        try:
            return await self.execute(params)
        except Exception as e:
            return Err(UnexpectedFailure(message=f"{type(e).__name__}: {e}"))
