"""Tests for work_timer.timer.timer_test."""
from datetime import datetime
import unittest

from flaky import flaky

from work_timer.config import get_test_config
from work_timer.timelog import Period
from work_timer.timer import Timer
from work_timer.utils.testing import FakeClock


class TestLoggingToTimeLog(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.addCleanup(self.clock.stop)
        self.config = get_test_config()
        self.task = list(self.config.task_db.get_all().values())[0]

    @flaky
    def test_it_logs_at_the_period_end(self):
        start_dt = datetime.fromtimestamp(self.clock.time())
        timer = Timer(self.config, clock=self.clock)

        timer.start(self.task.id)
        self.clock.advance(self.config.work_period_duration)

        assert self.config.time_log.get_periods() == [
                Period(task_id=self.task.id,
                        start=start_dt,
                        duration=self.config.work_period_duration)
        ]

    def test_it_does_not_log_while_the_period_is_still_going(self):
        timer = Timer(self.config, clock=self.clock)

        timer.start(self.task.id)
        self.clock.advance(self.config.work_period_duration / 2)

        assert self.config.time_log.get_periods() == []

    def test_it_logs_on_pause(self):
        start_dt = datetime.fromtimestamp(self.clock.time())
        timer = Timer(self.config, clock=self.clock)

        timer.start(self.task.id)
        self.clock.advance(self.config.work_period_duration / 2)
        timer.pause()

        assert self.config.time_log.get_periods() == [
                Period(task_id=self.task.id,
                        start=start_dt,
                        duration=self.config.work_period_duration / 2)
        ]


    def test_it_logs_two_periods_on_pause_and_resume(self):
        start_dt = datetime.fromtimestamp(self.clock.time())
        timer = Timer(self.config, clock=self.clock)

        half_duration = self.config.work_period_duration / 2

        timer.start(self.task.id)
        self.clock.advance(half_duration)
        timer.pause()
        timer.resume()
        self.clock.advance(self.config.work_period_duration)

        assert self.config.time_log.get_periods() == [
                Period(task_id=self.task.id,
                        start=start_dt,
                        duration=half_duration),
                Period(task_id=self.task.id,
                        start=start_dt + half_duration,
                        duration=half_duration)
        ]
