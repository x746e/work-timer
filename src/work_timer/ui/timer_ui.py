"""Timer interface."""
# TODO: Rename to `timer_ui`.
import math

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer as TextualTimer
from textual.widget import Widget
from textual.widgets import Digits, Footer, Label, ProgressBar

from work_timer import taskdb
from work_timer.ui.base_task_list import TaskSelectionDialog
from work_timer.ui.debug_panel import DebugPanel
from work_timer.timer import NoActiveTimer, Timer, TimerInfo



class TimeDisplay:
    """Shows the remaining time."""

    seconds_left = reactive(0.0)

    def watch_seconds_left(self, time: float) -> None:
        minutes, seconds = divmod(time, 60)
        hours, minutes = divmod(minutes, 60)
        self.update(f'{hours:02,.0f}:{minutes:02.0f}:{seconds:02.0f}')  # type: ignore # pylint: disable=no-member


class DigitsTimeDisplay(Digits, TimeDisplay):


    def __init__(self, seconds_left: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self.seconds_left = seconds_left


class SingleLineTimeDisplay(Label, TimeDisplay):
    pass


class TimerWidget(Widget):
    """Timer interface widget."""

    BINDINGS = [
        ('space', 'pause', 'Pause'),
        ('space', 'resume', 'Resume'),
        ('S', 'stop', 'Stop'),
        ('r', 'replace', 'Replace current task'),
        ('w', 'switch', 'Switch to another task'),
    ]

    class TimerStopped(Message):
        pass

    can_focus = True

    _ticker: TextualTimer | None
    _timer: Timer

    _update_interval = .1

    def __init__(self,
                 timer: Timer,
                 task_db: taskdb.TaskDB):
        super().__init__()
        self._task_db = task_db
        self._timer = timer

        self._timer_is_stopped = True
        self._last_timer_info = None
        # Widget cache.  TODO: Actually measure if it meaningfully improves performance.
        self._w = {}

    def on_mount(self):
        self._ticker = self.set_interval(self._update_interval, self._tick, pause=True)

    def resume_updates(self):
        assert self._ticker is not None
        self._ticker.resume()

    def pause_updates(self):
        assert self._ticker is not None
        self._ticker.pause()

    def compose(self) -> ComposeResult:
        self._w['title'] = Label('NOT RUNNING', id='title')
        self._w['time_display'] = DigitsTimeDisplay(0, id='time_display')
        self._w['progress_bar'] = ProgressBar(show_percentage=False, show_eta=False)

        ti = self._timer.get_info()
        if isinstance(ti, TimerInfo):
            self._update_classes(ti)
            self._update_title(ti, self._w['title'])
            self._update_time_display(ti, self._w['time_display'])
            self._update_progress_bar(ti, self._w['progress_bar'])

        yield self._w['title']
        yield self._w['time_display']
        yield self._w['progress_bar']

    def action_pause(self) -> None:
        self._timer.pause()
        self.refresh_bindings()

    def action_resume(self) -> None:
        self._timer.resume()
        self.refresh_bindings()

    def action_stop(self) -> None:
        self._timer.stop()

    @work
    async def action_replace(self) -> None:
        """Replace the current task with another one.

        Useful for the cases when you realize you've been working on another
        task all along.
        """
        new_task_id = await self.app.push_screen_wait(TaskSelectionDialog(self._task_db))
        if new_task_id is None:
            return
        self._timer.replace(task_id=new_task_id)
        self._refresh()

    @work
    async def action_switch(self) -> None:
        """Switch to another task.

        Useful when you want to work the rest of the current period on another task.
        """
        new_task_id = await self.app.push_screen_wait(TaskSelectionDialog(self._task_db))
        if new_task_id is None:
            return
        self._timer.switch(task_id=new_task_id)
        self._refresh()

    def check_action(  # pylint: disable=too-many-return-statements
        self, action: str, parameters: tuple[object, ...]
    ) -> bool | None:
        ti = self._timer.get_info()
        if not isinstance(ti, TimerInfo):
            return False
        if action in ('replace', 'switch') and ti.task_id != taskdb.BREAK_TASK_ID:
            return True
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
        self._refresh()

    def _refresh(self):
        ti = self._timer.get_info()

        if isinstance(ti, NoActiveTimer):
            self._timer_is_stopped = True
            self._on_timer_stopped()
            return

        if self._timer_is_stopped:
            self._timer_is_stopped = False
            self._on_timer_started()

        self._update_progress_bar(ti, self._w['progress_bar'])
        self._update_time_display(ti, self._w['time_display'])

        state_changed = task_changed = True
        if self._last_timer_info:
            state_changed = task_changed = False
            if self._last_timer_info.state != ti.state:
                state_changed = True
            if self._last_timer_info.task_id != ti.task_id:
                task_changed = True
        self._last_timer_info = ti

        if task_changed:
            self._update_title(ti, self._w['title'])

        if state_changed or task_changed:
            self._update_classes(ti)
            # `refresh_bindings` triggers `.recompose()` of the `Footer`, which
            # is CPU intensive and appears to leak memory.
            self.refresh_bindings()

    def _on_timer_started(self):
        pass

    def _on_timer_stopped(self):
        self.post_message(self.TimerStopped())

    def _update_title(self, ti: TimerInfo, title: Label) -> Label:
        task = self._task_db.get(ti.task_id)
        title.update(f'#{task.id} {task.title}')
        return title

    def _update_time_display(self, ti: TimerInfo, disp: TimeDisplay) -> TimeDisplay:
        seconds_left = math.ceil(
                ti.period_length.total_seconds() - ti.elapsed_time.total_seconds())
        disp.seconds_left = max(0, seconds_left)  # type: ignore
        return disp

    def _update_progress_bar(self, ti, pb: ProgressBar) -> ProgressBar:
        pb.update(total=ti.period_length.total_seconds(),
                  progress=ti.elapsed_time.total_seconds())
        return pb

    def _update_classes(self, ti: TimerInfo) -> None:
        classes = set()
        if ti.task_id == taskdb.BREAK_TASK_ID:
            classes.add('break')

        self.classes = classes


class MicroTimerWidget(TimerWidget):
    """A small version of TimerWidget, intended to be docked to the top of other screens."""

    DEFAULT_CSS = """
    MicroTimerWidget {
        height: 1;
        dock: top;
        * {
            padding-right: 1;
        }
        display: none;
    }
    """

    can_focus = False
    _update_interval = 1

    def compose(self) -> ComposeResult:
        self._w['title'] = Label('NOT RUNNING', id='title')
        self._w['time_display'] = SingleLineTimeDisplay(0)  # type: ignore
        self._w['progress_bar'] = ProgressBar(show_percentage=False, show_eta=False)

        ti = self._timer.get_info()
        if isinstance(ti, TimerInfo):
            self._update_classes(ti)
            self._update_title(ti, self._w['title'])
            self._update_time_display(ti, self._w['time_display'])
            self._update_progress_bar(ti, self._w['progress_bar'])

        with Horizontal():
            yield self._w['title']
            yield self._w['progress_bar']
            yield self._w['time_display']

    def _on_timer_stopped(self):
        self.display = False

    def _on_timer_started(self):
        self.display = True

    def on_mount(self):
        super().on_mount()
        self.resume_updates()


class TimerScreen(Screen):

    """A screen with a Timer widget."""

    CSS_PATH = 'timer_ui.tcss'

    def __init__(self, task_db: taskdb.TaskDB, timer: Timer, name: str | None = None) -> None:
        super().__init__(name=name)
        self._task_db = task_db
        self._timer = timer

    def on_screen_resume(self):
        self.query_one(TimerWidget).resume_updates()

    def on_screen_suspend(self):
        self.query_one(TimerWidget).pause_updates()

    def compose(self) -> ComposeResult:
        yield TimerWidget(self._timer, self._task_db)
        if self.app._config.debug:  # type: ignore  # pylint: disable=protected-access
            yield DebugPanel()
        yield Footer()


def main() -> None:
    """A way to exercise the widget in isolation, useful for development."""
    # pylint: disable=import-outside-toplevel
    from work_timer.config import get_test_config
    from work_timer.utils.scheduler import Scheduler

    class TimerApp(App):  # pylint: disable=missing-class-docstring

        CSS_PATH = 'timer.tcss'

        def compose(self) -> ComposeResult:
            config = get_test_config()
            timer = Timer(config, scheduler=Scheduler())
            task = list(config.task_db.get_all().values())[0]
            timer.start(task.id)
            yield TimerWidget(timer, config.task_db)
            yield Footer()

    app = TimerApp()
    app.run()


if __name__ == '__main__':
    main()
