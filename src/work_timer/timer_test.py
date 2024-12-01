"""Tests for work_timer.timer."""
import unittest

from work_timer import timer
from work_timer.taskdb import TaskID
from work_timer.utils.testing import FakeClock, td


State = timer.Timer.State


class TestStateChanges(unittest.TestCase):

    def setUp(self):
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    def test_not_started_timer_state(self):
        t = timer.Timer(clock=self._clock)
        self.assertEqual(t.get_info().state, State.STOPPED)

    def test_started_timer_state(self):
        t = timer.Timer(clock=self._clock)
        t.start(task_id=TaskID(42), period_length=td('5m'))
        self.assertEqual(t.get_info().state, State.RUNNING)

    def test_stopped_timer_state(self):
        t = timer.Timer(clock=self._clock)
        t.start(task_id=TaskID(42), period_length=td('5m'))
        t.stop()
        self.assertEqual(t.get_info().state, State.STOPPED)

    def test_paused_state(self):
        t = timer.Timer(clock=self._clock)
        t.start(task_id=TaskID(42), period_length=td('5m'))
        t.pause()
        self.assertEqual(t.get_info().state, State.PAUSED)

    def test_state_after_resume(self):
        t = timer.Timer(clock=self._clock)
        t.start(task_id=TaskID(42), period_length=td('5m'))
        t.pause()
        t.resume()
        self.assertEqual(t.get_info().state, State.RUNNING)

    def test_stop_after_pause(self):
        t = timer.Timer(clock=self._clock)
        t.start(task_id=TaskID(42), period_length=td('5m'))
        t.pause()
        t.stop()
        self.assertEqual(t.get_info().state, State.STOPPED)


class TestTimePassage(unittest.TestCase):

    def setUp(self):
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    def test_elapsed_time(self):
        t = timer.Timer(clock=self._clock)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        self._clock.advance('1m')
        state = t.get_info()

        self.assertEqual(state.elapsed_time, td('1m'))

    def test_elapsed_time_doesnt_increase_after_calling_stop(self):
        t = timer.Timer(clock=self._clock)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        self._clock.advance('1m')
        t.stop()
        self._clock.advance('10m')

        self.assertEqual(t.get_info().elapsed_time, td('1m'))

    def test_elapsed_time_doesnt_increase_after_calling_pause(self):
        t = timer.Timer(clock=self._clock)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        self._clock.advance('1m')
        t.pause()
        self._clock.advance('10m')

        self.assertEqual(t.get_info().elapsed_time, td('1m'))

    def test_elapsed_time_increases_after_resume(self):
        t = timer.Timer(clock=self._clock)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        self._clock.advance('1m')
        t.pause()
        self._clock.advance('10m')
        t.resume()
        self._clock.advance('1m')

        self.assertEqual(t.get_info().elapsed_time, td('2m'))

    def test_stop_after_pause(self):
        t = timer.Timer(clock=self._clock)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        self._clock.advance('1m')
        t.pause()
        self._clock.advance('10m')
        t.stop()
        self._clock.advance('1m')

        self.assertEqual(t.get_info().elapsed_time, td('1m'))


class TestScheduledEnding(unittest.TestCase):

    def setUp(self):
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    def test_it_stops_itself_after_period_end(self):
        t = timer.Timer(clock=self._clock)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        self._clock.advance('5m')

        self.assertEqual(t.get_info().state, State.STOPPED)

    def test_elapsed_time_is_right(self):
        t = timer.Timer(clock=self._clock)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        self._clock.advance('10m')

        self.assertEqual(t.get_info().elapsed_time, td('5m'))

    def test_it_stops_after_resume_as_well(self):
        t = timer.Timer(clock=self._clock)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        t.pause()
        t.resume()
        self._clock.advance('5m')

        self.assertEqual(t.get_info().state, State.STOPPED)

    def test_elapsed_time_after_pause_resume_is_right(self):
        t = timer.Timer(clock=self._clock)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        self._clock.advance('1m')
        t.pause()
        self._clock.advance('10m')
        t.resume()
        self._clock.advance('10m')

        self.assertEqual(t.get_info().elapsed_time, td('5m'))


class CallbackTest(unittest.TestCase):

    def setUp(self):
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    def test_callback_gets_called_on_scheduled_end(self):
        t = timer.Timer(clock=self._clock)
        callback_called = False
        def callback(unused_s: timer.TimerInfo):
            nonlocal callback_called
            callback_called = True
        t.set_on_period_end_callback(callback)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        self._clock.advance('5m')
        self._clock.advance('5m')

        self.assertTrue(callback_called)

    def test_callback_gets_called_on_explicit_stop(self):
        t = timer.Timer(clock=self._clock)
        callback_called = False
        def callback(unused_s: timer.TimerInfo):
            nonlocal callback_called
            callback_called = True
        t.set_on_period_end_callback(callback)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        self._clock.advance('1m')
        t.stop()

        self.assertTrue(callback_called)

    def test_callback_gets_called_when_stopping_a_paused_timer(self):
        t = timer.Timer(clock=self._clock)
        callback_called = False
        def callback(unused_s: timer.TimerInfo):
            nonlocal callback_called
            callback_called = True
        t.set_on_period_end_callback(callback)

        t.start(task_id=TaskID(42), period_length=td('5m'))
        self._clock.advance('1m')
        t.pause()
        t.stop()

        self.assertTrue(callback_called)


if __name__ == '__main__':
    unittest.main()
