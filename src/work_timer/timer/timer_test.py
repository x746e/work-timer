"""Tests for work_timer.timer.timer_test."""
from datetime import datetime
import functools
import unittest
from unittest import mock

from typing import no_type_check

from work_timer import config
from work_timer.taskdb import BREAK_TASK_ID
from work_timer.timelog import Period
from work_timer.timer import Timer, TimerInfo, NoActiveTimer
from work_timer.utils.scheduler import Scheduler
from work_timer.utils.testing import FakeClock, UnittestTestCaseMixin
from work_timer.utils.time import td


def rt_type(val, typ):
    assert isinstance(val, typ)
    return val


class TimerMixin:
    """Makes it easier to create Timer instances.

    ...with linked FakeClock and Scheduler.
    """

    @no_type_check
    def setUp(self):  # pylint: disable=invalid-name
        self.config = config.get_test_config()
        self.task = list(self.config.task_db.get_all().values())[-1]

        self.clock = FakeClock()
        self.addCleanup(self.clock.stop)
        self.scheduler = Scheduler(self.clock)
        self.clock.set_scheduler(self.scheduler)
        self.Timer = functools.partial(Timer,  # pylint: disable=invalid-name
                                       clock=self.clock, scheduler=self.scheduler)


class TestBreaks(TimerMixin, unittest.TestCase):

    def test_it_starts_a_break_after_a_working_period(self):
        timer = self.Timer(self.config)

        timer.start(self.task.id)
        self.clock.advance(self.config.work_period_duration)

        ti = timer.get_info()
        assert rt_type(ti, TimerInfo).task_id == BREAK_TASK_ID

    def test_there_is_no_active_timer_after_a_break_ends(self):
        timer = self.Timer(self.config)

        timer.start(BREAK_TASK_ID)
        self.clock.advance(self.config.work_period_duration)

        assert isinstance(timer.get_info(), NoActiveTimer)

    # TODO
    def test_it_do_not_start_a_break_when_stopped_before_the_period_end(self):
        pass

    def test_long_breaks(self):
        # Set the long_break_after to be after two periods.
        self.config.long_break_after = self.config.work_period_duration * 2
        timer = self.Timer(self.config)

        # Start these two periods.
        timer.start(self.task.id)
        assert rt_type(timer.get_info(), TimerInfo).task_id == self.task.id
        self.clock.advance(self.config.work_period_duration)
        assert rt_type(timer.get_info(), TimerInfo).task_id == BREAK_TASK_ID
        assert rt_type(timer.get_info(), TimerInfo).period_length == self.config.break_duration
        self.clock.advance(self.config.break_duration)
        assert isinstance(timer.get_info(), NoActiveTimer)
        timer.start(self.task.id)
        self.clock.advance(self.config.work_period_duration)

        # The long period should be started by now.
        ti = rt_type(timer.get_info(), TimerInfo)
        assert ti.task_id == BREAK_TASK_ID
        assert ti.period_length == self.config.long_break_duration


class TestLoggingToTimeLog(TimerMixin, unittest.TestCase):

    def test_it_logs_at_the_period_end(self):
        start_dt = datetime.fromtimestamp(self.clock.time())
        timer = self.Timer(self.config)

        timer.start(self.task.id)
        self.clock.advance(self.config.work_period_duration)

        assert self.config.time_log.get_periods() == [
                Period(task_id=self.task.id,
                       start=start_dt,
                       duration=self.config.work_period_duration)
        ]

    def test_it_logs_at_a_break_end(self):
        start_dt = datetime.fromtimestamp(self.clock.time())
        timer = self.Timer(self.config)

        timer.start(BREAK_TASK_ID)
        self.clock.advance(self.config.work_period_duration)

        assert self.config.time_log.get_periods() == [
                Period(task_id=BREAK_TASK_ID,
                       start=start_dt,
                       duration=self.config.work_period_duration)
        ]

    def test_logging_with_user_supplied_period_length(self):
        start_dt = datetime.fromtimestamp(self.clock.time())
        timer = self.Timer(self.config)
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
        timer = self.Timer(self.config)

        timer.start(self.task.id)
        self.clock.advance(self.config.work_period_duration / 2)

        assert self.config.time_log.get_periods() == []

    def test_it_logs_on_pause(self):
        start_dt = datetime.fromtimestamp(self.clock.time())
        timer = self.Timer(self.config)

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
        timer = self.Timer(self.config)

        half_duration = self.config.work_period_duration / 2

        timer.start(self.task.id)
        self.clock.advance(half_duration)
        timer.pause()
        timer.resume()
        self.clock.advance(self.config.work_period_duration)

        want_periods = [
                Period(task_id=self.task.id,
                       start=start_dt,
                       duration=half_duration),
                Period(task_id=self.task.id,
                       start=start_dt + half_duration,
                       duration=half_duration)
        ]
        got_periods = self.config.time_log.get_periods()
        # Remove breaks.
        got_periods = [p for p in got_periods if p.task_id > 0]
        assert want_periods == got_periods


class NotificationTestingMixin:
    """A mixin for notification testing."""

    def setUp(self: UnittestTestCaseMixin):  # pylint: disable=invalid-name
        super().setUp()
        self.notifier = mock.Mock(spec=config.DesktopNotifier)  # type: ignore

    def got_notifications(self) -> list[str]:
        return [
            call.kwargs['title']
            for call in self.notifier.send.call_args_list
        ]

    def assert_notifications(self, want_notifications: list[str]) -> None:
        assert self.got_notifications() == want_notifications

    def assert_no_notifications_like(self, notification: str) -> None:
        assert notification not in self.got_notifications()


class TestNotifications(NotificationTestingMixin, TimerMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.config = config.get_test_config(
            notifier=self.notifier,
        )

    def test_notifications_at_the_end_of_a_work_period(self):
        timer = self.Timer(self.config)

        timer.start(self.task.id)
        self.clock.advance(self.config.work_period_duration)

        self.assert_notifications(['Work period ended'])

    def test_notifications_at_the_end_of_a_break(self):
        timer = self.Timer(self.config)

        timer.start(BREAK_TASK_ID)
        self.clock.advance(self.config.work_period_duration)

        self.assert_notifications(['Break ended'])

    # TODO
    def test_no_notifications_after_manually_stopped_period(self):
        pass


class TestBugging(NotificationTestingMixin, TimerMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.config = config.get_test_config(
            bug_after=td('10m'),
            work_period_duration=td('25m'),
            break_duration=td('5m'),
            long_break_after=td('3h'),
            long_break_duration=td('20m'),
            notifier=self.notifier,
        )


    def test_it_bugs_with_a_non_started_timer(self):
        timer = self.Timer(self.config)  # noqa: F841  # pylint: disable=unused-variable

        self.clock.advance('10m1s')

        self.assert_notifications(['Time to do some work!'])

    def test_it_doesnt_bug_during_a_break(self):
        timer = self.Timer(self.config)

        timer.start(self.task.id)
        # Go through the whole work period.
        self.clock.advance('25m')
        # And through the break.
        self.clock.advance('5m')

        # We shouldn't have got any bugging notifications.
        self.assert_no_notifications_like('Time to do some work!')

    def test_it_bugs_when_a_timer_is_paused(self):
        timer = self.Timer(self.config)

        timer.start(self.task.id)
        timer.pause()
        self.clock.advance('10m1s')

        self.assert_notifications(['Time to do some work!'])


class TestCalendar(TimerMixin, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.config = config.get_test_config()
        self.calendar = self.config.calendar = mock.Mock(spec=config.GoogleCalendar)

    def test_an_event_is_added_at_the_end_of_a_work_period(self):
        timer = self.Timer(self.config)

        timer.start(self.task.id)
        self.clock.advance(self.config.work_period_duration)

        assert self.calendar.add_event.call_count == 1

    def test_an_event_is_not_added_at_the_end_of_a_break(self):
        timer = self.Timer(self.config)

        timer.start(BREAK_TASK_ID)
        self.clock.advance(self.config.work_period_duration)

        # No events.
        assert self.calendar.add_event.call_count == 0
        # ...while the break still ended.
        assert len(self.config.time_log.get_periods()) == 1


if __name__ == '__main__':
    unittest.main()
