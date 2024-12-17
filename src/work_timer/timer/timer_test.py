"""Tests for work_timer.timer.timer_test."""
from datetime import datetime
import unittest

from flaky import flaky

from work_timer.config import get_test_config
from work_timer.taskdb import TaskID
from work_timer.timelog import Period
from work_timer.timer import Timer
from work_timer.utils.testing import FakeClock


class TestLoggingToTimeLog(unittest.TestCase):

    def setUp(self):
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    @flaky
    def test_it(self):
        config = get_test_config()
        start_dt = datetime.fromtimestamp(self._clock.time())
        timer = Timer(config, clock=self._clock)

        timer.start(TaskID(42))
        self._clock.advance(config.work_period_duration)

        self.assertEqual(
                config.time_log.get_periods(),
                [Period(task_id=TaskID(42), start=start_dt, duration=config.work_period_duration)])
