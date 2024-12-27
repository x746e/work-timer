"""Tests for work_timer.utils.scheduler."""
import unittest

from work_timer.utils.scheduler import Scheduler
from work_timer.utils.testing import FakeClock
from work_timer.utils.time import td


class SchedulerTest(unittest.TestCase):

    def test_scheduler_runs(self):
        clock = FakeClock()
        scheduler = Scheduler(clock)

        ran = False

        def target():
            nonlocal ran
            ran = True

        scheduler.schedule(target, after=td('5m'))

        clock.advance('4m')
        assert not ran
        clock.advance('1m')
        assert ran

    def test_cancelling(self):
        clock = FakeClock()
        scheduler = Scheduler(clock)

        ran = False

        def target():
            nonlocal ran
            ran = True

        evt = scheduler.schedule(target, after=td('5m'))

        scheduler.cancel(evt)
        clock.advance('5m')
        assert not ran
