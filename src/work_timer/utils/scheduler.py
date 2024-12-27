"""A variation of stdlib's sched.scheduler.

...only with the features I need, and integrated with utils.testing.FakeClock.
"""
from collections import defaultdict
from datetime import timedelta
import itertools
import threading
import time

from typing import NewType

from work_timer.utils.clock import Clock
from work_timer.utils.time import humanize_td
from work_timer.utils.testing import bts


EvtID = NewType('EvtID', int)


class Scheduler:
    """Schedules execution on callables in the feature."""

    def __init__(self, clock: Clock = time) -> None:
        self._lock = threading.Lock()
        self._sequence_generator = itertools.count(1)
        self._clock = clock
        self._scheduled = defaultdict(list)
        self._cancelled: set[EvtID] = set()

    def schedule(self, action, after: timedelta) -> EvtID:
        """Schedule calling `action` after `after` time passes."""
        with self._lock:
            evt_id = next(self._sequence_generator)
        at = self._clock.time() + after.total_seconds()

        started = threading.Event()

        def target():
            started.set()
            self._clock.sleep(after.total_seconds())
            with self._lock:
                if evt_id in self._cancelled:
                    return
            action()

        thread = threading.Thread(target=target,
                                  name=f'Running {action.__name__} at {humanize_td(at)}',
                                  daemon=True)
        with self._lock:
            self._scheduled[at].append(thread)
        thread.start()

        started.wait()

        return EvtID(evt_id)

    def cancel(self, evt: EvtID) -> None:
        with self._lock:
            self._cancelled.add(evt)

    def _wait(self) -> None:
        """Wait for all threads scheduled to run before `self._clock.time()` to finish.

        Intended for use in tests, especially the ones manipulating time.
        """
        def should_be_awoken() -> list[threading.Thread]:
            ret = []
            with self._lock:
                wake_times = sorted(ts for ts in self._scheduled if ts <= self._clock.time())
                for ts in wake_times:
                    ret.extend(self._scheduled.pop(ts))
            return ret

        for thread in should_be_awoken():
            thread.join(timeout=5)
            if thread.is_alive():
                bts()
                assert False

        # This code assumes no new threads will be scheduled while we are doing this.
        # In case there are, this method should probably be extended.
        assert not should_be_awoken()

    def _get_future_wake_times(self) -> list[float]:
        with self._lock:
            return sorted(ts for ts in self._scheduled if ts >= self._clock.time())
