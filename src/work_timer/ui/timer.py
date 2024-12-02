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

    class _Restart(Message):
        pass

    can_focus = True

    _ticker: TextualTimer | None
    _wt_timer: timer.Timer | None

    # TODO: We never really need the TimerWidget without a task and period attached.
    def __init__(
            self,
            timed_task = taskdb.Task(title='Test', id=taskdb.TaskID(42)),
            period_length = timedelta(seconds=4)):
        super().__init__()
        self._ticker = None
        self._wt_timer = None
        self._timed_task = timed_task
        self._period_length = period_length

    def compose(self) -> ComposeResult:
        # print('compose')
        yield TimeDisplay(self._period_length.seconds)
        progress_bar = ProgressBar(show_percentage=False, show_eta=False)
        progress_bar.update(progress=0, total=self._period_length.seconds)
        if self._ticker:
            self._ticker.stop()
        self._ticker = self.set_interval(.05, self._tick, pause=True)
        self._wt_timer = None
        yield progress_bar
        self.refresh_bindings()

    def action_start(self) -> None:
        # print('action_start')
        self._wt_timer = timer.Timer()
        self._wt_timer.start(taskdb.TaskID(42), self._period_length)
        self._wt_timer.set_on_period_end_callback(self._on_period_end)
        not_none(self._ticker).resume()
        self.refresh_bindings()

    def _on_period_end(self, info: timer.TimerInfo) -> None:
        del info
        # print(f'_on_period_end({info=})')
        # print(f'{Timer._Restart.handler_name=}')
        self.post_message(Timer._Restart())

    @on(_Restart)
    async def on_timer_restart(self) -> None:
        not_none(self._ticker).stop()
        self._tick()
        self.refresh_bindings()
        # print('on_timer_restart')

    def action_pause(self) -> None:
        # print('action_pause')
        not_none(self._wt_timer).pause()
        self.refresh_bindings()

    def action_resume(self) -> None:
        # print('action_resume')
        not_none(self._wt_timer).resume()
        self.refresh_bindings()

    def check_action(  # pylint: disable=too-many-return-statements
        self, action: str, parameters: tuple[object, ...]
    ) -> bool | None:
        # def inner():
        if self._wt_timer is None:
            if action == 'start':
                return True
            if action in ('pause', 'resume', 'stop'):
                return False
        if self._wt_timer is not None and action in ('start', 'pause', 'resume', 'stop'):
            if action == 'start':
                return False
            match (action, self._wt_timer.get_info().state):
                case ('pause', timer.Timer.State.RUNNING):
                    return True
                case ('resume', timer.Timer.State.PAUSED):
                    return True
                case ('stop', timer.Timer.State.RUNNING):
                    return True
                case ('stop', timer.Timer.State.PAUSED):
                    return True
                case (_, timer.Timer.State.STOPPED):
                    return False
                case _:
                    return False
        return True
        # ret = inner()
        # print(f'check_action({action=}, {parameters=}) -> {ret}')
        # return ret

    def _tick(self) -> None:
        ti = not_none(self._wt_timer).get_info()
        seconds_left = not_none(ti.period_length).total_seconds() - ti.elapsed_time.total_seconds()
        self.query_one(TimeDisplay).seconds_left = max(0, seconds_left)
        self.query_one(ProgressBar).update(total=not_none(ti.period_length).total_seconds(),
                                           progress=ti.elapsed_time.total_seconds())


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
