"""Tests for work_timer.timer.timer_test."""
from datetime import datetime
import unittest
from unittest import mock

from flaky import flaky

from work_timer import config
from work_timer.taskdb import BREAK_TASK_ID
from work_timer.timelog import Period
from work_timer.timer import Timer
from work_timer.utils.testing import FakeClock
from work_timer.utils.time import td


@flaky
class TestLoggingToTimeLog(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.addCleanup(self.clock.stop)
        self.config = config.get_test_config()
        self.task = list(self.config.task_db.get_all().values())[0]

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

    def test_it_logs_at_a_break_end(self):
        start_dt = datetime.fromtimestamp(self.clock.time())
        timer = Timer(self.config, clock=self.clock)

        timer.start(BREAK_TASK_ID)
        self.clock.advance(self.config.work_period_duration)

        assert self.config.time_log.get_periods() == [
                Period(task_id=BREAK_TASK_ID,
                       start=start_dt,
                       duration=self.config.work_period_duration)
        ]

    def test_logging_with_user_supplied_period_length(self):
        start_dt = datetime.fromtimestamp(self.clock.time())
        timer = Timer(self.config, clock=self.clock)
        period_length = td('42m')
        assert period_length > self.config.work_period_duration

        timer.start(self.task.id, period_length=period_length)
        self.clock.advance(period_length)

        assert self.config.time_log.get_periods() == [
                Period(task_id=self.task.id,
                       start=start_dt,
                       duration=period_length)
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


@flaky
class TestNotifications(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.addCleanup(self.clock.stop)
        self.config = config.get_test_config()
        self.notifier = self.config.notifier = mock.Mock(spec=config.DesktopNotifier)
        self.task = list(self.config.task_db.get_all().values())[0]

    def test_notifications_at_the_end_of_a_work_period(self):
        timer = Timer(self.config, clock=self.clock)

        timer.start(self.task.id)
        self.clock.advance(self.config.work_period_duration)

        assert self.notifier.send.call_count == 1
        assert self.notifier.send.call_args.kwargs['title'] == 'Work period ended'

    def test_notifications_at_the_end_of_a_break(self):
        timer = Timer(self.config, clock=self.clock)

        timer.start(BREAK_TASK_ID)
        self.clock.advance(self.config.work_period_duration)

        assert self.notifier.send.call_count == 1
        assert self.notifier.send.call_args.kwargs['title'] == 'Break ended'


@flaky
class TestCalendar(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.addCleanup(self.clock.stop)
        self.config = config.get_test_config()
        self.calendar = self.config.calendar = mock.Mock(spec=config.GoogleCalendar)
        self.task = list(self.config.task_db.get_all().values())[0]

    def test_an_event_is_added_at_the_end_of_a_work_period(self):
        timer = Timer(self.config, clock=self.clock)

        timer.start(self.task.id)
        self.clock.advance(self.config.work_period_duration)

        assert self.calendar.add_event.call_count == 1

    def test_an_event_is_not_added_at_the_end_of_a_break(self):
        timer = Timer(self.config, clock=self.clock)

        timer.start(BREAK_TASK_ID)
        self.clock.advance(self.config.work_period_duration)

        # No events.
        assert self.calendar.add_event.call_count == 0
        # ...while the break still ended.
        assert len(self.config.time_log.get_periods()) == 1
