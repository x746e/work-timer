"""Timer interface."""
from datetime import timedelta

from textual import on
from textual.app import App, ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.timer import Timer as TextualTimer
from textual.widget import Widget
from textual.widgets import Digits, Footer, ProgressBar

from work_timer import timer
from work_timer import taskdb
from work_timer.utils.typing import not_none


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


class Timer(Widget):
    """Timer interface widget."""

    BINDINGS = [
        ("s", "start", "Start"),
        ("S", "stop", "Stop"),
        ("p", "pause", "Pause"),
        ("c", "continue_", "Continue"),
        # TODO: Do I need all these start/pause/continue_, bound to different keys?
        #       Why not just do everything on <Space>?
    ]

    class _Restart(Message):
        pass

    can_focus = True

    _ticker: TextualTimer | None
    _wt_timer: timer.Timer | None

    def __init__(self):
        super().__init__()
        self._ticker = None
        self._wt_timer = None
        self._timed_task = taskdb.Task(title='Test', id=taskdb.TaskID(42))
        self._period_length = timedelta(seconds=2)

    def compose(self) -> ComposeResult:
        print('compose')
        yield TimeDisplay(self._period_length.seconds)
        progress_bar = ProgressBar(show_percentage=False, show_eta=False)
        progress_bar.update(progress=0, total=self._period_length.seconds)
        if self._ticker:
            self._ticker.stop()
        self._ticker = self.set_interval(1, self._tick, pause=True)
        self._wt_timer = None
        yield progress_bar
        self.refresh_bindings()

    def action_start(self) -> None:
        print('action_start')
        self._wt_timer = timer.Timer()
        self._wt_timer.start(taskdb.TaskID(42), self._period_length)
        self._wt_timer.set_on_period_end_callback(self._on_period_end)
        not_none(self._ticker).resume()
        self.refresh_bindings()

    def _on_period_end(self, info: timer.TimerInfo) -> None:
        print(f'_on_period_end({info=})')
        print(f'{Timer._Restart.handler_name=}')
        self.post_message(Timer._Restart())

    @on(_Restart)
    async def on_timer_restart(self) -> None:
        await self.recompose()
        self.refresh_bindings()
        print('on_timer_restart')

    def action_pause(self) -> None:
        print('action_pause')
        not_none(self._wt_timer).pause()
        self.refresh_bindings()

    def action_continue_(self) -> None:
        print('action_continue_')
        not_none(self._wt_timer).resume()
        self.refresh_bindings()

    def check_action(  # pylint: disable=too-many-return-statements
        self, action: str, parameters: tuple[object, ...]
    ) -> bool | None:
        if self._wt_timer is None:
            if action == 'start':
                return True
            if action in ('pause', 'continue_'):
                return False
        if self._wt_timer is not None and action in ('start', 'pause', 'continue_'):
            if action == 'start':
                return None
            match (action, self._wt_timer.get_info().state):
                case ('pause', timer.Timer.State.RUNNING):
                    return True
                case ('continue_', timer.Timer.State.PAUSED):
                    return True
                case _:
                    return False
        return True

    def _tick(self) -> None:
        ti = not_none(self._wt_timer).get_info()
        seconds_left = not_none(ti.period_length).seconds - ti.elapsed_time.seconds
        self.query_one(TimeDisplay).seconds_left = seconds_left
        self.query_one(ProgressBar).update(total=not_none(ti.period_length).seconds,
                                           progress=ti.elapsed_time.seconds)


class TimerApp(App):

    CSS_PATH = 'timer.tcss'

    def compose(self) -> ComposeResult:
        yield Timer()
        yield Footer()


def main() -> None:
    # db = fake_tasks.get_task_db()
    # task = next(iter(db.get_all().values()))
    app = TimerApp()
    app.run()


if __name__ == '__main__':
    main()
