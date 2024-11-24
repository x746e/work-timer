"""Tests for work_timer.timelog."""
import datetime
import unittest

from work_timer import timer
from work_timer import timelog
from work_timer.utils.testing import FakeClock, td


class TimeLogTest(unittest.TestCase):

    def setUp(self):
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    def test_it(self):
        log = timelog.TimeLog()
        start_dt = datetime.datetime.fromtimestamp(self._clock.time())
        t = timer.Timer(clock=self._clock, time_log=log)

        t.start(task_id=42, period_length=td('5m'))
        self._clock.advance('5m')

        self.assertEqual(
                log.get_periods(),
                [timelog.Period(task_id=42, start=start_dt, duration=td('5m'))])


if __name__ == '__main__':
    unittest.main()
