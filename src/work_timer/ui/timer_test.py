"""Tests for work_timer.ui.task_list."""
import asyncio
from datetime import timedelta
import math
import unittest

from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Footer, Label, ProgressBar
from textual.widgets._footer import FooterKey

from work_timer import taskdb
from work_timer.timelog import TimeLog
from work_timer.ui.timer import Timer, TimeDisplay


class FakeApp(App):

    def __init__(self, period_length: timedelta, timed_task: taskdb.Task) -> None:
        super().__init__()
        self.period_length = period_length
        self.timed_task = timed_task

    def compose(self) -> ComposeResult:
        yield Timer(timed_task=self.timed_task, period_length=self.period_length, time_log=TimeLog())
        yield Footer(show_command_palette=False)


class WalkthroughFunctionalTest(unittest.IsolatedAsyncioTestCase):
    """Go through the whole workflow in one test.

    Generally I prefer much more focused tests validating just one thing,
    but before I figure out all this asyncio programming and how to mock things
    out in it (`asyncio.sleep` mostly), I want to have this one test.

    It will not mock out time, so I don't want to have more than one for now.
    """

    def setUp(self):
        self.period_length = timedelta(seconds=4)
        self.task = taskdb.Task(title='Test task', id=taskdb.TaskID(42))
        self.app = FakeApp(self.period_length, self.task)

    async def test_it(self):
        async with self.app.run_test() as pilot:

            self.check_initial_state(pilot)

            # Start, wait 1 second, check the running state.
            await pilot.press('space')
            await asyncio.sleep(1)
            self.check_running_state(pilot)

            # Pause, wait another second, check the paused state.
            await pilot.press('space')
            await asyncio.sleep(1)
            self.check_paused_state(pilot)

            # Get it run toward completion, check stopped state.
            await pilot.press('space')
            await asyncio.sleep(10)
            self.check_stopped_state(pilot)

    def check_initial_state(self, pilot: Pilot) -> None:
        """Check the Timer widget in the expected state before start."""
        # Check the Digits show the right time.
        display = pilot.app.query_exactly_one(TimeDisplay)
        self.assertEqual(display.value, '00:00:04')
        # The task title is shown.
        assert pilot.app.query_exactly_one('#title', Label).renderable == self.task.title
        # Progress is on zero.
        progress_bar = pilot.app.query_exactly_one(ProgressBar)
        self.assertEqual(progress_bar.total, self.period_length.total_seconds())
        self.assertEqual(progress_bar.progress, 0)
        # The footer says "Start".
        self.assertEqual(
            ['space Start'],
            get_binding(pilot),
        )

    def check_running_state(self, pilot: Pilot) -> None:
        """Check the running widget."""
        # Check the Digits show the right time.
        display = pilot.app.query_exactly_one(TimeDisplay)
        self.assertEqual(display.value, '00:00:03')
        # Progress is not zero.
        progress_bar = pilot.app.query_exactly_one(ProgressBar)
        self.assertEqual(progress_bar.total, self.period_length.total_seconds())
        self.assertEqual(math.floor(progress_bar.progress), 1)
        # Check `pause` and `stop` bindings are active.
        self.assertEqual(
            ['space Pause', 'S Stop'],
            get_binding(pilot),
        )

    def check_paused_state(self, pilot: Pilot) -> None:
        """Check a paused widget."""
        # Check the Digits show and ProgressBar didn't change.
        display = pilot.app.query_exactly_one(TimeDisplay)
        self.assertEqual(display.value, '00:00:03')
        progress_bar = pilot.app.query_exactly_one(ProgressBar)
        self.assertEqual(progress_bar.total, self.period_length.total_seconds())
        self.assertEqual(math.floor(progress_bar.progress), 1)
        # Check `pause` and `stop` bindings are active.
        self.assertEqual(
            ['space Resume', 'S Stop'],
            get_binding(pilot),
        )

    def check_stopped_state(self, pilot: Pilot) -> None:
        # Seconds left should be at zero, progress bar should be completed.
        display = pilot.app.query_exactly_one(TimeDisplay)
        self.assertEqual(display.value, '00:00:00')
        progress_bar = pilot.app.query_exactly_one(ProgressBar)
        self.assertEqual(progress_bar.total, progress_bar.progress)
        # No binding should be active.
        self.assertEqual(get_binding(pilot), [])


def get_binding(pilot: Pilot) -> list[str]:
    """Gets a list of current app bindings from the Footer."""
    bindings = pilot.app.query(FooterKey)
    return [str(b.render()).strip() for b in bindings]


def run_test_app():
    period_length = timedelta(seconds=5)
    timed_task = taskdb.Task(title='Test task', id=taskdb.TaskID(42))
    app = FakeApp(period_length, timed_task)
    app.run()


if __name__ == '__main__':
    run_test_app()
