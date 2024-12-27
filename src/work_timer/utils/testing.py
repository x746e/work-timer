"""Misc testing helpers."""
from collections import defaultdict
from datetime import timedelta
import functools
import time
import threading
from typing import Protocol, Callable
import sys
import traceback

from work_timer.utils import clock
from work_timer.utils.time import td


class UnittestTestCaseMixin(Protocol):
    # pylint: disable=invalid-name
    def setUp(self) -> None: ...

    def addCleanup(self, function: Callable, /, *args, **kwargs) -> None: ...


class FakeClock(clock.Clock):
    """A fake implementation of timer.Clock iface.

    Allows to test the code that calls `time.sleep` and `time.time`, without
    actually waiting for time to pass.

    The class tries to be smart about the way it moves the time forward.  If
    there are three threads sleeping, say, for 4, 10, and 52,
    FakeClock.advance(52) will try to first set time to 4, wait for the first
    sleeping thread to wake up and signal back it woke up, then it will move
    the time forward to 10, and then to 52, each time waiting for the awoken
    thread to signal back.
    """

    # I don't have too much confidence in the correctness of this, but seems to
    # work.  And this is test-only code, so it's OK if it's not :).
    #
    # One possible way to try if it works funky: lock when returning
    # self._time, use the same lock in the Condition.

    def __init__(self) -> None:
        self._time = 0.
        self._stopped = False
        self._future_is_now = threading.Condition()
        self._wake_lock = threading.Lock()
        self._wake_at = defaultdict(list)
        self._scheduler = None

    def set_scheduler(self, scheduler) -> None:
        self._scheduler = scheduler

    def advance(self, delta: timedelta | str) -> None:
        """Move the fake time by `delta`.

        `delta` can either be a `timedelta` object, or a string like '5s' or
        '3h2m5s'.
        """

        def let_callbacks_run():
            if self._scheduler:
                self._scheduler._wait()  # pylint: disable=protected-access

        advance_to = self._time + td(delta).total_seconds()

        # Don't move directly to `advance_to`: step through the times this
        # class was asked to `.sleep` until, and, if `self._scheduler` is set,
        # also step through the times callbacks was scheduled to run.  These
        # two sets should be the same most of the time, if not always.

        def get_next_wake_time() -> float | None:
            with self._wake_lock:
                wake_times = set(self._wake_at)
            if self._scheduler:
                wake_times |= set(self._scheduler._get_future_wake_times())  # pylint: disable=protected-access
            wake_times = sorted(wake_times)
            if not wake_times:
                return None
            return wake_times[0]

        while True:
            t = get_next_wake_time()
            if t is None:
                break
            if t > advance_to:
                break
            assert t >= self._time

            # Notify all the sleeping threads.
            with self._future_is_now:
                self._time = t
                self._future_is_now.notify_all()

            # And wait for them to signal us back they woke up.
            with self._wake_lock:
                if t in self._wake_at:
                    evts = self._wake_at.pop(t)
                    for sleeper_awoken in evts:
                        sleeper_awoken.wait()

            let_callbacks_run()

        self._time = advance_to
        time.sleep(0.01)

        let_callbacks_run()

    def time(self) -> float:
        return self._time

    def sleep(self, seconds: float, /) -> None:

        until = self._time + seconds

        with self._wake_lock:
            wake_evt = threading.Event()
            self._wake_at[until].append(wake_evt)

        with self._future_is_now:
            while self._time < until:
                self._future_is_now.wait()

        # Notify the thread running .advance that we woke up, and it's OK to
        # continue moving the time forward.
        wake_evt.set()

    def stop(self) -> None:
        # Move forward for a bit, to allow callbacks to fire.
        self._stopped = True
        self.advance('356d')


def bts(label=''):
    """Print stacktraces from all running threads."""
    p = functools.partial(print, file=sys.stderr)
    p('')
    p('>>> ' + label + ' ' + '>>>' * 20)
    for fr in sys._current_frames().values():  # pylint: disable=protected-access
        traceback.print_stack(fr)
        p('---' * 20)
    p('<<<' * 20)
    p()
