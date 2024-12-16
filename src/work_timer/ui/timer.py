"""Timer interface."""
from datetime import timedelta

from textual import on
from textual.app import App, ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer as TextualTimer
from textual.widget import Widget
from textual.widgets import Digits, Footer, Label, ProgressBar

from work_timer import timer
from work_timer import taskdb
from work_timer.timelog import TimeLog


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


class TimerWidget(Widget):
    """Timer interface widget."""

    BINDINGS = [
        ("space", "pause", "Pause"),
        ("space", "resume", "Resume"),
        ("S", "stop", "Stop"),
    ]

    class PeriodEnded(Message):
        pass

    can_focus = True

    _ticker: TextualTimer
    _wt_timer: timer.Timer

    def __init__(self,
                 wt_timer: timer.Timer,
                 timed_task: taskdb.Task,
                 period_length: timedelta):
        super().__init__()
        self._ticker = self.set_interval(.05, self._tick)
        self._timed_task = timed_task
        self._period_length = period_length
        self._wt_timer = wt_timer
        self._wt_timer.set_on_period_end_callback(self._on_period_end)
        if timed_task.id == taskdb.BREAK_TASK_ID:
            self.classes = 'break'

    def compose(self) -> ComposeResult:
        yield Label(self._timed_task.title, id='title')
        yield TimeDisplay(self._period_length.seconds)
        progress_bar = ProgressBar(show_percentage=False, show_eta=False)
        progress_bar.update(progress=0, total=self._period_length.total_seconds())
        yield progress_bar
        self.refresh_bindings()  # TODO: Is this needed?

    def _on_period_end(self, info: timer.TimerInfo) -> None:
        del info
        self.post_message(TimerWidget.PeriodEnded())

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

    def action_stop(self) -> None:
        self._wt_timer.stop()

    def check_action(  # pylint: disable=too-many-return-statements
        self, action: str, parameters: tuple[object, ...]
    ) -> bool | None:
        match (action, self._wt_timer.get_info().state):
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

    def __init__(self, timed_task: taskdb.Task, period_length: timedelta, time_log: TimeLog):
        super().__init__()
        self._timed_task = timed_task
        self._period_length = period_length
        self._time_log = time_log
        self._wt_timer = timer.Timer(self._timed_task.id, self._period_length, time_log)

    def compose(self) -> ComposeResult:
        yield TimerWidget(self._wt_timer, self._timed_task, self._period_length)
        yield Footer()

    @on(TimerWidget.PeriodEnded)
    async def on_period_end(self) -> None:
        self.dismiss()


def main() -> None:
    """A way to exercise the widget in isolation, useful for development."""

    class TimerApp(App):  # pylint: disable=missing-class-docstring

        CSS_PATH = 'timer.tcss'

        def compose(self) -> ComposeResult:
            timed_task = taskdb.Task(title='Test', id=taskdb.TaskID(42))
            period_length = timedelta(seconds=4)
            time_log = TimeLog()
            wt_timer = timer.Timer(timed_task.id, period_length, time_log)
            yield TimerWidget(wt_timer = wt_timer,
                        timed_task = timed_task,
                        period_length = period_length)
            yield Footer()

    app = TimerApp()
    app.run()


if __name__ == '__main__':
    main()
