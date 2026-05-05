"""Result type — every use case returns Ok or Err. No exceptions cross layer boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeAlias, TypeVar

from .failures import Failure

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T

    @property
    def is_ok(self) -> bool:
        return True

    @property
    def is_err(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Err:
    failure: Failure

    @property
    def is_ok(self) -> bool:
        return False

    @property
    def is_err(self) -> bool:
        return True


Result: TypeAlias = Ok[T] | Err


def ok(value: T) -> Ok[T]:
    return Ok(value)


def err(failure: Failure) -> Err:
    return Err(failure)
