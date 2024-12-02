"""Tests for work_timer.ui.task_list."""
import asyncio
from datetime import timedelta
import math
import unittest

from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Footer, ProgressBar
from textual.widgets._footer import FooterKey

from work_timer.ui.timer import Timer, TimeDisplay


class FakeApp(App):

    def __init__(self, period_length: timedelta = timedelta(seconds=5)) -> None:
        super().__init__()
        self._period_length = period_length

    def compose(self) -> ComposeResult:
        yield Timer(period_length=self._period_length)
        yield Footer(show_command_palette=False)


# TODO:

# Start. Check:
# - Classes: .not-started is gone, .started is added.

# Pause.  Check:
# - Classes: .paused

class WalkthroughFunctionalTest(unittest.IsolatedAsyncioTestCase):
    """Go through the whole workflow in one test.

    Generally I prefer much more focused tests validating just one thing,
    but before I figure out all this asyncio programming and how to mock things
    out in it (`asyncio.sleep` mostly), I want to have this one test.

    It will not mock out time, so I don't want to have more than one for now.
    """

    def setUp(self):
        self.period_length = timedelta(seconds=4)
        self.app = FakeApp(period_length=self.period_length)

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
        # Progress is on zero.
        progress_bar = pilot.app.query_exactly_one(ProgressBar)
        self.assertEqual(progress_bar.total, self.period_length.total_seconds())
        self.assertEqual(progress_bar.progress, 0)
        # The footer says "Start".
        bindings = pilot.app.query(FooterKey)
        self.assertEqual(
            ['space Start'],
            [str(b.render()).strip() for b in bindings],
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
        bindings = pilot.app.query(FooterKey)
        self.assertEqual(
            ['space Pause', 'S Stop'],
            [str(b.render()).strip() for b in bindings],
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
        bindings = pilot.app.query(FooterKey)
        self.assertEqual(
            ['space Resume', 'S Stop'],
            [str(b.render()).strip() for b in bindings],
        )

    def check_stopped_state(self, pilot: Pilot) -> None:
        # Seconds left should be at zero, progress bar should be completed.
        display = pilot.app.query_exactly_one(TimeDisplay)
        self.assertEqual(display.value, '00:00:00')
        progress_bar = pilot.app.query_exactly_one(ProgressBar)
        self.assertEqual(progress_bar.total, progress_bar.progress)
        # No binding should be active.
        self.assertCountEqual(pilot.app.query(FooterKey), [])


def run_test_app():
    app = FakeApp()
    app.run()


# TODO: How to mock out all the time Textual timer is using?
#       I'll need to know more about asyncio it looks like.

if __name__ == '__main__':
    run_test_app()
    # unittest.main()
