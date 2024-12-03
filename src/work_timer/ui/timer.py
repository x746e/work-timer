"""Timer interface."""
from datetime import timedelta

from textual import on
from textual.app import App, ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer as TextualTimer
from textual.widget import Widget
from textual.widgets import Digits, Footer, ProgressBar

from work_timer import timer
from work_timer import taskdb
from work_timer.utils.profiling import log_call


class TimeDisplay(Digits):
    """Shows the remaining time."""

    seconds_left = reactive(0.0)

    def __init__(self, seconds_left: float) -> None:
        super().__init__()
        self.seconds_left = seconds_left

    def watch_seconds_left(self, time: float) -> None:
        minutes, seconds = divmod(time, 60)
        hours, minutes = divmod(minutes, 60)
        self.update(f"{hours:02,.0f}:{minutes:02.0f}:{seconds:02.0f}")

# TODO: @log_call on a class should:
# Log when the class is instantiated;
# and add a @log_call to each method.
class Timer(Widget):
    """Timer interface widget."""

    BINDINGS = [
        ("space", "start", "Start"),
        ("space", "pause", "Pause"),
        ("space", "resume", "Resume"),
        ("S", "stop", "Stop"),
    ]

    # TODO: Set .pause / .running classes to the Timer.
    # TODO: From the app, set .work_period / .break classes.

    # TODO: Don't have any non-started timers around.
    # Maybe "RunningTimer" subclass, with the logic that doesn't need to check
    # for self._timer is not None?
    #
    # From the app, create the timer in already started state.
    #
    # Do I want to open the overall app with the last task?
    # Do I want to switch to the task list after a break?
    #   - In some cases, and initially, it's probably a good idea: I'm prone to
    #     doing interesting work for too long, and not leaving enough time for
    #     important but unpleasant work.
    #     Getting back to the list tasks will make it a bit harder.
    #   - But in some cases switching back to the task list can get me out of the
    #     flow state.  If that's what I'm going to see in practice, I may want to:
    #       - Give the TimerWidget a "non-started" state.
    #       # TODO: Actually why isn't Timer created with task/period already in paused state?
    #           Why does anything has to be None?
    #
    # TODO: Maybe rename it to TimerWidget?  Too many Timer classes.

    class PeriodEnded(Message):
        pass

    can_focus = True

    _ticker: TextualTimer
    _wt_timer: timer.Timer

    def __init__(self, timed_task: taskdb.Task, period_length: timedelta):
        super().__init__()
        self._ticker = self.set_interval(.05, self._tick, pause=True)
        self._timed_task = timed_task
        self._period_length = period_length
        self._wt_timer = timer.Timer(self._timed_task.id, self._period_length)

    def compose(self) -> ComposeResult:
        yield TimeDisplay(self._period_length.seconds)
        progress_bar = ProgressBar(show_percentage=False, show_eta=False)
        progress_bar.update(progress=0, total=self._period_length.total_seconds())
        yield progress_bar
        self.refresh_bindings()

    def action_start(self) -> None:
        self._wt_timer.start()
        self._wt_timer.set_on_period_end_callback(self._on_period_end)
        self._ticker.resume()
        self.refresh_bindings()

    def _on_period_end(self, info: timer.TimerInfo) -> None:
        del info
        self.post_message(Timer.PeriodEnded())

    @on(PeriodEnded)
    async def on_period_end(self) -> None:
        self._ticker.stop()
        self._tick()
        self.disabled = True
        self.refresh_bindings()

    def action_pause(self) -> None:
        self._wt_timer.pause()
        self.refresh_bindings()

    def action_resume(self) -> None:
        self._wt_timer.resume()
        self.refresh_bindings()

    #@log_call(when=lambda args: args.action == 'stop', locals=True)
    # locals should print locals at `return`.

    #@log_call(watch=lambda: f'{self._wt_timer.get_info()=}')
    # (equivalent to)
    #@log_call(watch='self._wt_timer.get_info()')

    #@log_call(when=lambda args: args.action == 'stop', trace=True)
    # Print each executed line, along with resolved local variables:
    # match (action /*='stop'*/, self._wt_timer..... /*=STOPPED*/):
    # ...

    # Make a library that use profiling to store all the possible information
    # for all the calls, and that make an interface to query that info
    # afterwards.

    @log_call
    def check_action(  # pylint: disable=too-many-return-statements
        self, action: str, parameters: tuple[object, ...]
    ) -> bool | None:
        match (action, self._wt_timer.get_info().state):
            case ('start', timer.Timer.State.STOPPED):
                return True
            case ('pause', timer.Timer.State.RUNNING):
                return True
            case ('resume', timer.Timer.State.PAUSED):
                return True
            case ('stop', timer.Timer.State.RUNNING):
                return True
            case ('stop', timer.Timer.State.PAUSED):
                return True
            case _:
                return False

    def _tick(self) -> None:
        ti = self._wt_timer.get_info()
        seconds_left = ti.period_length.total_seconds() - ti.elapsed_time.total_seconds()
        self.query_one(TimeDisplay).seconds_left = max(0, seconds_left)
        self.query_one(ProgressBar).update(total=ti.period_length.total_seconds(),
                                           progress=ti.elapsed_time.total_seconds())


class TimerScreen(Screen):

    """A screen with a Timer widget."""

    CSS_PATH = 'timer.tcss'

    def __init__(self, timed_task: taskdb.Task, period_length: timedelta):
        super().__init__()
        self._timed_task = timed_task
        self._period_length = period_length

    def compose(self) -> ComposeResult:
        yield Timer(self._timed_task, self._period_length)
        yield Footer()

    @on(Timer.PeriodEnded)
    async def on_period_end(self) -> None:
        self.dismiss()


def main() -> None:
    """A way to exercise the widget in isolation, useful for development."""

    class TimerApp(App):

        CSS_PATH = 'timer.tcss'

        def compose(self) -> ComposeResult:
            yield Timer(timed_task = taskdb.Task(title='Test', id=taskdb.TaskID(42)),
                        period_length = timedelta(seconds=4))
            yield Footer()

    app = TimerApp()
    app.run()


if __name__ == '__main__':
    main()
