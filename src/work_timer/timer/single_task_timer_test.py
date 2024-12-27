"""Tests for work_timer.timer."""
from datetime import timedelta
import functools
import random
import time
import unittest

from typing import no_type_check

from work_timer.timer.single_task_timer import SingleTaskTimer as STTimer, TimerInfo
from work_timer.taskdb import TaskID
from work_timer.utils.scheduler import Scheduler
from work_timer.utils.testing import FakeClock
from work_timer.utils.time import td


State = STTimer.State


class STTimerMixin:

    @no_type_check
    def setUp(self):  # pylint: disable=invalid-name
        super().setUp()
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)
        self._scheduler = Scheduler(self._clock)
        self._clock.set_scheduler(self._scheduler)
        self.STTimer = functools.partial(STTimer,  # pylint: disable=invalid-name
                                         scheduler=self._scheduler, clock=self._clock)


class TestStateChanges(STTimerMixin, unittest.TestCase):

    def test_not_started_timer_state(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))
        self.assertEqual(t.get_info().state, State.RUNNING)

    def test_started_timer_state(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))
        self.assertEqual(t.get_info().state, State.RUNNING)

    def test_stopped_timer_state(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))
        t.stop()
        self.assertEqual(t.get_info().state, State.STOPPED)

    def test_paused_state(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))
        t.pause()
        self.assertEqual(t.get_info().state, State.PAUSED)

    def test_state_after_resume(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))
        t.pause()
        t.resume()
        self.assertEqual(t.get_info().state, State.RUNNING)

    def test_stop_after_pause(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))
        t.pause()
        t.stop()
        self.assertEqual(t.get_info().state, State.STOPPED)


class TestTimePassage(STTimerMixin, unittest.TestCase):

    def test_elapsed_time(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))

        self._clock.advance('1m')
        state = t.get_info()

        self.assertEqual(state.elapsed_time, td('1m'))

    def test_elapsed_time_doesnt_increase_after_calling_stop(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))

        self._clock.advance('1m')
        t.stop()
        self._clock.advance('10m')

        self.assertEqual(t.get_info().elapsed_time, td('1m'))

    def test_elapsed_time_doesnt_increase_after_calling_pause(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))

        self._clock.advance('1m')
        t.pause()
        self._clock.advance('10m')

        self.assertEqual(t.get_info().elapsed_time, td('1m'))

    def test_elapsed_time_increases_after_resume(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))

        self._clock.advance('1m')
        t.pause()
        self._clock.advance('10m')
        t.resume()
        self._clock.advance('1m')

        self.assertEqual(t.get_info().elapsed_time, td('2m'))

    def test_stop_after_pause(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))

        self._clock.advance('1m')
        t.pause()
        self._clock.advance('10m')
        t.stop()
        self._clock.advance('1m')

        self.assertEqual(t.get_info().elapsed_time, td('1m'))


class TestScheduledEnding(STTimerMixin, unittest.TestCase):

    def test_it_stops_itself_after_period_end(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))

        self._clock.advance('5m')

        self.assertEqual(t.get_info().state, State.STOPPED)

    def test_it_stops_after_resume_as_well(self):
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))

        t.pause()
        t.resume()
        self._clock.advance('5m')

        self.assertEqual(t.get_info().state, State.STOPPED)

    def test_elapsed_time_after_pause_resume_is_right(self):

        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'))

        self._clock.advance('1m')
        # import time; time.sleep(.1)
        t.pause()
        self._clock.advance('10m')
        # time.sleep(.1)
        t.resume()
        self._clock.advance('10m')
        # time.sleep(.1)

        self.assertEqual(t.get_info().elapsed_time, td('5m'))


class CallbackTest(STTimerMixin, unittest.TestCase):

    def test_callback_gets_called_on_scheduled_end(self):
        callback_called = False
        def callback(unused_s: TimerInfo):
            nonlocal callback_called
            callback_called = True
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'),  # noqa: F841
                         on_period_end_callback=callback)

        self._clock.advance('5m')
        self._clock.advance('5m')

        self.assertTrue(callback_called)

    def test_callback_gets_called_on_explicit_stop(self):
        callback_called = False
        def callback(unused_s: TimerInfo):
            nonlocal callback_called
            callback_called = True
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'),
                         on_period_end_callback=callback)

        self._clock.advance('1m')
        t.stop()

        self.assertTrue(callback_called)

    def test_callback_gets_called_when_stopping_a_paused_timer(self):
        callback_called = False
        def callback(unused_s: TimerInfo):
            nonlocal callback_called
            callback_called = True
        t = self.STTimer(task_id=TaskID(42), period_length=td('5m'),
                         on_period_end_callback=callback)

        self._clock.advance('1m')
        t.pause()
        t.stop()

        self.assertTrue(callback_called)


class SemiRandomTest(unittest.TestCase):

    def setUp(self):
        self.seed = int(time.time())
        # print(f'{self.seed=}')
        # self.seed = 1733161366
        random.seed(self.seed)

        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    def test_it(self):

        num_steps = int(random.uniform(1, 100))

        def should_wait() -> bool:
            return random.random() > .6

        def should_transition() -> bool:
            return random.random() > .5

        class Wait:
            def __init__(self, t=None):
                self.t = t or int(random.uniform(1, 60*10))

            def __repr__(self):
                return f'Wait(t={self.t!r})'

        class Transition:
            def __init__(self, to, method):
                self.to = to
                self.method = method

            def __repr__(self):
                return f'Transition(to={self.to}, method={self.method!r})'

        allowed_transitions = {
                State.RUNNING: [(State.STOPPED, 'stop'), (State.PAUSED, 'pause')],
                State.PAUSED: [(State.STOPPED, 'stop'), (State.RUNNING, 'resume')],
        }

        # Generate the execution plan.
        def make_plan(num_steps):
            plan = []
            state = State.RUNNING
            for step in range(num_steps):  # pylint: disable=unused-variable
                if state == State.STOPPED:
                    break
                if should_wait():
                    plan.append(Wait())
                if should_transition():
                    state, method = random.choice(allowed_transitions[state])
                    plan.append(Transition(to=state, method=method))
                if should_wait():
                    plan.append(Wait())
            return plan

        plan = make_plan(num_steps)
        # print(plan)

        def execute(plan):
            state = State.RUNNING
            elapsed = 0

            def check():
                info = t.get_info()
                self.assertEqual(info.elapsed_time.total_seconds(), elapsed, f'{self.seed=}')
                self.assertEqual(info.state, state, f'{self.seed=}')

            period_length = timedelta(seconds=random.uniform(0, 60 * num_steps))
            total = period_length.total_seconds()
            # print(f'{total=}')

            scheduler = Scheduler(self._clock)
            self._clock.set_scheduler(scheduler)
            t = STTimer(task_id=TaskID(42), scheduler=scheduler,
                        period_length=period_length, clock=self._clock)

            done = False
            for action in plan:
                check()
                #print(f'Doing {action}')
                match action:
                    case Wait():
                        if state == State.RUNNING:
                            if elapsed + action.t > total:
                                elapsed = total
                                state = State.STOPPED
                                done = True
                            else:
                                elapsed += action.t
                        self._clock.advance(timedelta(seconds=action.t))
                    case Transition():
                        state = action.to
                        getattr(t, action.method)()
                check()
                if done:
                    break

        execute(plan)


if __name__ == '__main__':
    unittest.main()
