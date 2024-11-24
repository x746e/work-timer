"""Time related helpers."""

from typing import Protocol


class Clock(Protocol):
    def time(self) -> float:
        ...

    def sleep(self, seconds: float, /):
        ...
