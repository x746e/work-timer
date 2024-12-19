"""Misc testing helpers."""
from collections import defaultdict
from datetime import timedelta
import time
import threading
from typing import Protocol, Callable
import sys
import traceback

from work_timer.utils import clock
from work_timer.utils.time import td


class UnittestTestCaseMixin(Protocol):

    def addCleanup(self, function: Callable) -> None: ...  # pylint: disable=invalid-name


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

    def advance(self, delta: timedelta | str) -> None:
        """Move the fake time by `delta`.

        `delta` can either be a `timedelta` object, or a string like '5s' or
        '3h2m5s'.
        """
        advance_to = self._time + td(delta).total_seconds()

        bts('BEFORE WAKE UP')

        for t in sorted(self._wake_at):
            if t > advance_to:
                break

            # Notify all the sleeping threads.
            with self._future_is_now:
                self._time = t
                self._future_is_now.notify_all()

            # And wait for them to signal us back they woke up.
            with self._wake_lock:
                evts = self._wake_at.pop(t)
            for sleeper_awoken in evts:
                sleeper_awoken.wait()

        self._time = advance_to
        time.sleep(0)

        # The idea here is to look at what are all the threads doing, and maybe
        # wait for our code to get executed, if not already.
        #
        # To implement that I started by just list all the threads with the
        # `bts` function.  It appears that doing that takes just enough time
        # for other threads to call all the required callbacks!
        #
        # I'm going to leave this as is for now, and if a see tests getting
        # flaky again, to continue with that the hacky idea above.
        #
        # And if that doesn't work, I probably should add some synchronization
        # mechanism to the SingleTaskTimer itself: a threading.Event that is set
        # after its callbacks fire, for instance.
        bts('AFTER WAKE UP')

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
    print('')
    print('>>> ' + label + ' ' + '>>>' * 20)
    for fr in sys._current_frames().values():  # pylint: disable=protected-access
        traceback.print_stack(fr)
        print('---' * 20)
    print('<<<' * 20)
    print()
