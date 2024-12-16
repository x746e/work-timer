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

from work_timer import taskdb
from work_timer.timer import Timer, TimerInfo
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
    _timer: Timer

    def __init__(self,
                 timer: Timer,
                 task_db: taskdb.TaskDB):
        super().__init__()
        self._ticker = self.set_interval(.05, self._tick)
        self._task_db = task_db
        self._timer = timer
        self._timer.set_on_period_end_callback(self._on_period_end)

    def compose(self) -> ComposeResult:
        ti = self._timer.get_info()

        self._update_classes(ti)

        title = Label('', id='title')
        yield self._update_title(ti, title)
        yield self._update_time_display(ti, TimeDisplay(42))
        progress_bar = ProgressBar(show_percentage=False, show_eta=False)
        yield self._update_progress_bar(ti, progress_bar)

    def _on_period_end(self, info: TimerInfo) -> None:
        del info
        self.post_message(TimerWidget.PeriodEnded())

    @on(PeriodEnded)
    async def on_period_end(self) -> None:
        self._ticker.stop()
        self._tick()
        self.disabled = True
        self.refresh_bindings()

    def action_pause(self) -> None:
        self._timer.pause()
        self.refresh_bindings()

    def action_resume(self) -> None:
        self._timer.resume()
        self.refresh_bindings()

    def action_stop(self) -> None:
        self._timer.stop()

    def check_action(  # pylint: disable=too-many-return-statements
        self, action: str, parameters: tuple[object, ...]
    ) -> bool | None:
        match (action, self._timer.get_info().state):
            case ('pause', Timer.State.RUNNING):
                return True
            case ('resume', Timer.State.PAUSED):
                return True
            case ('stop', Timer.State.RUNNING):
                return True
            case ('stop', Timer.State.PAUSED):
                return True
            case _:
                return False

    def _tick(self) -> None:
        ti = self._timer.get_info()
        self._update_progress_bar(ti, self.query_one(ProgressBar))
        self._update_time_display(ti, self.query_one(TimeDisplay))
        self._update_title(ti, self.query_one('#title', Label))
        self._update_classes(ti)

    def _update_title(self, ti: TimerInfo, title: Label) -> Label:
        task = self._task_db.get(ti.task_id)
        title.update(task.title)
        return title

    def _update_time_display(self, ti: TimerInfo, disp: TimeDisplay) -> TimeDisplay:
        seconds_left = ti.period_length.total_seconds() - ti.elapsed_time.total_seconds()
        disp.seconds_left = max(0, seconds_left)
        return disp

    def _update_progress_bar(self, ti, pb: ProgressBar) -> ProgressBar:
        pb.update(total=ti.period_length.total_seconds(),
                  progress=ti.elapsed_time.total_seconds())
        return pb

    def _update_classes(self, ti: TimerInfo) -> None:
        if ti.task_id == taskdb.BREAK_TASK_ID:
            self.classes = 'break'


class TimerScreen(Screen):

    """A screen with a Timer widget."""

    CSS_PATH = 'timer.tcss'

    def __init__(self, task_db: taskdb.TaskDB, timed_task: taskdb.Task,
                 period_length: timedelta, time_log: TimeLog):
        super().__init__()
        self._task_db = task_db
        self._timed_task = timed_task
        self._period_length = period_length
        self._time_log = time_log
        self._timer = Timer(self._timed_task.id, self._period_length, time_log)

    def compose(self) -> ComposeResult:
        yield TimerWidget(self._timer, self._task_db)
        yield Footer()

    @on(TimerWidget.PeriodEnded)
    async def on_period_end(self) -> None:
        self.dismiss()


def main() -> None:
    """A way to exercise the widget in isolation, useful for development."""

    from work_timer.utils import fake_tasks  # pylint: disable=import-outside-toplevel

    class TimerApp(App):  # pylint: disable=missing-class-docstring

        CSS_PATH = 'timer.tcss'

        def compose(self) -> ComposeResult:
            db = fake_tasks.get_task_db()
            task = list(db.get_all().values())[0]
            period_length = timedelta(seconds=4)
            time_log = TimeLog()
            timer = Timer(task.id, period_length, time_log)
            yield TimerWidget(timer, db)
            yield Footer()

    app = TimerApp()
    app.run()


if __name__ == '__main__':
    main()
