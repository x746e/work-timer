"""Tests for work_timer.ui.timer_widget."""
import asyncio
from datetime import timedelta
import math
import unittest

from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Footer, Label, ProgressBar
from textual.widgets._footer import FooterKey

from work_timer.config import get_test_config
from work_timer.taskdb import TaskDB
from work_timer.timer import Timer
from work_timer.ui.timer_widget import TimerWidget, TimeDisplay
from work_timer.utils.scheduler import Scheduler
from work_timer.utils.testing import FakeClock
from work_timer.utils.typing import not_none


class FakeApp(App):  # pylint: disable=missing-class-docstring

    def __init__(self, task_db: TaskDB, timer: Timer) -> None:
        super().__init__()
        self._timer = timer
        self._task_db = task_db
        self._timer_widget = None

    def compose(self) -> ComposeResult:
        self._timer_widget = TimerWidget(self._timer, self._task_db)
        yield self._timer_widget
        yield Footer(show_command_palette=False)


class WalkthroughFunctionalTest(unittest.IsolatedAsyncioTestCase):
    """Go through the whole workflow in one test."""

    def setUp(self):
        self.period_length = timedelta(seconds=4)
        self.config = get_test_config(
                work_period_duration=self.period_length,
                break_duration=timedelta(seconds=3),
        )
        self.clock = FakeClock()
        self.scheduler = Scheduler(self.clock)
        self.clock.set_scheduler(self.scheduler)
        self.timer = Timer(self.config, clock=self.clock, scheduler=self.scheduler)
        self.task = list(self.config.task_db.get_all().values())[-1]
        self.timer.start(self.task.id)

        self.app = FakeApp(self.config.task_db, self.timer)

    async def test_it(self):

        async def time_travel(to):
            self.clock.advance(to)
            not_none(self.app._timer_widget)._tick()  # pylint: disable=protected-access
            await asyncio.sleep(.1)

        async with self.app.run_test() as pilot:

            # Should be started in the running state.
            self.check_initial_state(pilot)

            # Wait 1 second, check again.
            await time_travel('1s')
            self.check_running_state(pilot)

            # Pause, wait another second, check the paused state.
            await pilot.press('space')
            await time_travel('1s')
            self.check_paused_state(pilot)

            # At this point it was running for a second, and paused for a
            # second.  Let's run the remaining 3 seconds of the working period.
            await pilot.press('space')
            await time_travel('3s')
            # Now it should switch to a three second break.
            self.check_break(pilot)

    def check_initial_state(self, pilot: Pilot) -> None:
        """Check the Timer widget in the expected state before start."""
        # Check the Digits show the right time.
        display = pilot.app.query_exactly_one(TimeDisplay)
        self.assertEqual(display.value, '00:00:04')
        # The task title is shown.
        assert pilot.app.query_exactly_one('#title', Label).renderable == self.task.title
        # Progress is about zero.
        progress_bar = pilot.app.query_exactly_one(ProgressBar)
        self.assertEqual(progress_bar.total, self.period_length.total_seconds())
        self.assertEqual(math.floor(progress_bar.progress), 0)
        # Check the bindings.
        assert get_binding(pilot) == [
            'space Pause', 'S Stop', 'r Replace current task', 'w Switch to another task']

    def check_running_state(self, pilot: Pilot) -> None:
        """Check the running widget."""
        # Check the Digits show the right time.
        display = pilot.app.query_exactly_one(TimeDisplay)
        self.assertEqual(display.value, '00:00:03')
        # Progress is not zero.
        progress_bar = pilot.app.query_exactly_one(ProgressBar)
        self.assertEqual(progress_bar.total, self.period_length.total_seconds())
        self.assertEqual(math.floor(progress_bar.progress), 1)
        # Check the bindings.
        assert get_binding(pilot) == [
            'space Pause', 'S Stop', 'r Replace current task', 'w Switch to another task']

    def check_paused_state(self, pilot: Pilot) -> None:
        """Check a paused widget."""
        # Check the Digits show and ProgressBar didn't change.
        display = pilot.app.query_exactly_one(TimeDisplay)
        self.assertEqual(display.value, '00:00:03')
        progress_bar = pilot.app.query_exactly_one(ProgressBar)
        self.assertEqual(progress_bar.total, self.period_length.total_seconds())
        self.assertEqual(math.floor(progress_bar.progress), 1)
        # Check the bindings.
        assert get_binding(pilot) == [
            'space Resume', 'S Stop', 'r Replace current task', 'w Switch to another task']

    def check_break(self, pilot: Pilot) -> None:
        timer_widget = pilot.app.query_exactly_one(TimerWidget)
        assert 'break' in timer_widget.classes
        # We should be at the start of a 3 second break.
        display = pilot.app.query_exactly_one(TimeDisplay)
        self.assertEqual(display.value, '00:00:03')
        # Check `pause` and `stop` bindings are active.
        assert get_binding(pilot) == ['space Pause', 'S Stop']


def get_binding(pilot: Pilot) -> list[str]:
    """Gets a list of current app bindings from the Footer."""
    bindings = pilot.app.query(FooterKey)
    return [str(b.render()).strip() for b in bindings]


def run_dev_app():
    """Run an app with the TimerWidget.

    Useful for development.
    """
    config = get_test_config(
            work_period_duration=timedelta(seconds=4),
            break_duration=timedelta(seconds=3),
            enable_notifications=True,
            bug_after=timedelta(seconds=1),
            bug_every=timedelta(seconds=1),
    )
    task = list(config.task_db.get_all().values())[-1]
    timer = Timer(config, scheduler=Scheduler())
    timer.start(task.id)
    app = FakeApp(config.task_db, timer)
    app.run()


if __name__ == '__main__':
    run_dev_app()
