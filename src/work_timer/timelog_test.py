"""Tests for work_timer.timelog."""
import dataclasses
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from flaky import flaky

from work_timer import timer
from work_timer.taskdb import TaskID
from work_timer.timelog import TimeLog, PersistentTimeLog, Period
from work_timer.utils.testing import FakeClock, td


class TimeLogTest(unittest.TestCase):

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


EXPECTED_DATA = {
    'data': [
        {
            'duration': 300000000000,
            'index': 0,
            'start': '1969-12-31T16:20:34.000',
            'task_id': 42,
        },
        {
            'duration': 18000000000000,
            'index': 1,
            'start': '1970-01-01T02:20:34.000',
            'task_id': 24,
        },
    ],
    'schema': {
        'fields': [
            {
                'name': 'index',
                'type': 'integer',
            },
            {
                'name': 'task_id',
                'type': 'integer',
            },
            {
                'name': 'start',
                'type': 'datetime',
            },
            {
                'name': 'duration',
                'type': 'integer',
            },
        ],
        'pandas_version': '1.4.0',
        'primaryKey': [
            'index',
        ],
    },
}


class PersistentTimeLogTest(unittest.TestCase):

    def setUp(self):
        start_dt = datetime.fromtimestamp(1234)
        self.periods = [
            Period(task_id=TaskID(42), start=start_dt, duration=td('5m')),
            Period(task_id=TaskID(24), start=start_dt + td('10h'), duration=td('5h')),
        ]

    def test_saving(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'timelog.json'
            log = PersistentTimeLog(path)

            for period in self.periods:
                log.add_period(**dataclasses.asdict(period))

            with path.open() as f:
                data = json.load(f)
            assert data == EXPECTED_DATA

    def test_loading(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'timelog.json'
            with path.open('w') as f:
                json.dump(EXPECTED_DATA, f)

            log = PersistentTimeLog(path)

            assert self.periods == log.get_periods()


if __name__ == '__main__':
    unittest.main()
