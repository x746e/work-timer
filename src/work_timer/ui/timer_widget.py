"""Timer interface."""
from datetime import datetime
import math

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

    class TimerStopped(Message):
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

    def compose(self) -> ComposeResult:
        title = Label('NOT RUNNING', id='title')
        time_display = TimeDisplay(0)
        progress_bar = ProgressBar(show_percentage=False, show_eta=False)

        ti = self._timer.get_info()
        if isinstance(ti, TimerInfo):
            self._update_classes(ti)
            self._update_title(ti, title)
            self._update_time_display(ti, time_display)
            self._update_progress_bar(ti, progress_bar)

        yield title
        yield time_display
        yield progress_bar

    @on(TimerStopped)
    async def on_timer_stopped(self) -> None:
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
        ti = self._timer.get_info()
        if not isinstance(ti, TimerInfo):
            return False
        match (action, ti.state):
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
        if not isinstance(ti, TimerInfo):
            return

        self._update_progress_bar(ti, self.query_one(ProgressBar))
        self._update_time_display(ti, self.query_one(TimeDisplay))
        self._update_title(ti, self.query_one('#title', Label))

        self._update_classes(ti)

        if ti.state == Timer.State.STOPPED:
            self.post_message(TimerWidget.TimerStopped())

    def _update_title(self, ti: TimerInfo, title: Label) -> Label:
        task = self._task_db.get(ti.task_id)
        title.update(task.title)
        return title

    def _update_time_display(self, ti: TimerInfo, disp: TimeDisplay) -> TimeDisplay:
        seconds_left = math.ceil(
                ti.period_length.total_seconds() - ti.elapsed_time.total_seconds())
        print(f'[{datetime.now().second:<2}] upd: left: {seconds_left}; ID: {ti.task_id}  | {ti}')
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

    CSS_PATH = 'timer_widget.tcss'

    def __init__(self, task_db: taskdb.TaskDB, timer: Timer) -> None:
        super().__init__()
        self._task_db = task_db
        self._timer = timer

    def compose(self) -> ComposeResult:
        yield TimerWidget(self._timer, self._task_db)
        yield Footer()

    @on(TimerWidget.TimerStopped)
    async def on_period_end(self) -> None:
        self.dismiss()


def main() -> None:
    """A way to exercise the widget in isolation, useful for development."""

    from work_timer.config import get_test_config  # pylint: disable=import-outside-toplevel

    class TimerApp(App):  # pylint: disable=missing-class-docstring

        CSS_PATH = 'timer.tcss'

        def compose(self) -> ComposeResult:
            config = get_test_config()
            timer = Timer(config)
            task = list(config.task_db.get_all().values())[0]
            timer.start(task.id)
            yield TimerWidget(timer, config.task_db)
            yield Footer()

    app = TimerApp()
    app.run()


if __name__ == '__main__':
    main()
