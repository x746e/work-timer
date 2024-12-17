"""Tests for work_timer.timer.timer_test."""
from datetime import datetime
import unittest

from flaky import flaky

from work_timer import timer
from work_timer.taskdb import TaskID
from work_timer.timelog import TimeLog, Period
from work_timer.utils.testing import FakeClock, td


class TestLoggingToTimeLog(unittest.TestCase):

    def setUp(self):
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    @flaky
    def test_it(self):
        log = TimeLog()
        start_dt = datetime.fromtimestamp(self._clock.time())
        _ = timer.Timer(task_id=TaskID(42), period_length=td('5m'),
                        clock=self._clock, time_log=log)

        self._clock.advance('5m')

        self.assertEqual(
                log.get_periods(),
                [Period(task_id=TaskID(42), start=start_dt, duration=td('5m'))])
