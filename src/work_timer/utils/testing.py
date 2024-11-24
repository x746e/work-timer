import datetime
import time

from work_timer.utils import clock


class FakeClock(clock.Clock):
    """A fake implementation of timer.Clock iface.

    Allows to test the code that calls `time.sleep` and `time.time`, without
    actually waiting for time to pass.
    """

    def __init__(self):
        self._time = 0.
        self._stopped = False

    def advance(self, delta: datetime.timedelta | str, ticks=30):
        inc = td(delta).seconds / ticks
        for _ in range(ticks):
            self._time += inc
            time.sleep(0)
        time.sleep(0.001)

    def time(self) -> float:
        return self._time

    def sleep(self, seconds: float, /):
        until = self._time + seconds
        while self._time < until and not self._stopped:
            pass

    def stop(self):
        # Move forward for a bit, to allow callbacks to fire.
        self._stopped = True
        self.advance('1h')
        self._time = 2**32


def td(s: str | datetime.timedelta) -> datetime.timedelta:
    if isinstance(s, datetime.timedelta):
        return s
    if s[-1] == 's':
        return datetime.timedelta(seconds=int(s[:-1]))
    if s[-1] == 'm':
        return datetime.timedelta(minutes=int(s[:-1]))
    if s[-1] == 'h':
        return datetime.timedelta(hours=int(s[:-1]))
    raise ValueError(s)
