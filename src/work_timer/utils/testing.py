"""Misc testing helpers."""
from datetime import timedelta
import time
from threading import Condition
from typing import Protocol, Callable

from work_timer.utils import clock
from work_timer.utils.time import td


class UnittestTestCaseMixin(Protocol):

    def addCleanup(self, function: Callable) -> None: ...  # pylint: disable=invalid-name


class FakeClock(clock.Clock):
    """A fake implementation of timer.Clock iface.

    Allows to test the code that calls `time.sleep` and `time.time`, without
    actually waiting for time to pass.
    """

    def __init__(self) -> None:
        self._time = 0.
        self._stopped = False
        self._future_is_now = Condition()

    def advance(self, delta: timedelta | str, ticks=30) -> None:
        """Move the fake time by `delta`."""

        def time_travel(to: float) -> None:
            with self._future_is_now:
                self._time = to
                self._future_is_now.notify_all()

        delta_sec = td(delta).total_seconds()
        # `(float_num / ticks) * ticks` isn't necessarily equals `float_num`,
        # so let's calculate what the time should be at the end, so set this
        # explicitly.
        advance_to = self._time + delta_sec
        inc = delta_sec / ticks
        for _ in range(ticks):
            time_travel(to=self._time + inc)
            time.sleep(0)

        if self._time < advance_to:
            time_travel(advance_to)

        time.sleep(0.001)

    def time(self) -> float:
        return self._time

    def sleep(self, seconds: float, /) -> None:
        until = self._time + seconds
        with self._future_is_now:
            while self._time < until and not self._stopped:
                self._future_is_now.wait()

    def stop(self) -> None:
        # Move forward for a bit, to allow callbacks to fire.
        self._stopped = True
        self.advance('1h')
        self._time = 2**32
        with self._future_is_now:
            self._future_is_now.notify_all()
