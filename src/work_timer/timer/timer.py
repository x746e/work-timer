"""The Timer."""
from datetime import date, datetime, timedelta
import time
from typing import no_type_check

from desktop_notifier import Urgency, Icon, Sound
from gcsa.event import Event

from work_timer.config import Config
from work_timer.taskdb import TaskID, BREAK_TASK_ID
from work_timer.timer.single_task_timer import SingleTaskTimer, TimerInfo
from work_timer.utils.clock import Clock


class Timer:

    """The timer.

    For now just forwards everything to the underlying _SingleTaskTimer.  The
    plan is to move all the timing logic from ui.timer into this class.
    """

    State = SingleTaskTimer.State

    def __init__(self, config: Config, clock: Clock = time) -> None:
        self._config = config
        self._time_log = config.time_log
        self._clock = clock
        self._single_task_timer = None
        self._break_manager = _BreakManager(config, clock)

    def start(self, task_id: TaskID, period_length: timedelta | None = None) -> None:
        """Starts a new period for `task_id`.

        If `period_length` is specified, use that.  If not, use the default
        duration from the Config.
        """
        if period_length is None:
            period_length = self._config.work_period_duration
        self._single_task_timer = SingleTaskTimer(task_id, period_length, clock=self._clock)

        self._single_task_timer.set_on_next_sub_period_callback(self._on_next_sub_period)
        if task_id == BREAK_TASK_ID:
            self._single_task_timer.set_on_period_end_callback(self._on_break_end)
        else:
            self._single_task_timer.set_on_period_end_callback(self._on_work_period_end)

    def stop(self) -> None:
        assert self._single_task_timer is not None
        self._single_task_timer.stop()

    def pause(self) -> None:
        assert self._single_task_timer is not None
        self._single_task_timer.pause()

    def resume(self) -> None:
        assert self._single_task_timer is not None
        self._single_task_timer.resume()

    def get_info(self) -> 'NoActiveTimer | TimerInfo':
        if self._single_task_timer is None:
            return NoActiveTimer()
        return self._single_task_timer.get_info()

    def _on_next_sub_period(self, task_id: TaskID, started_at: datetime,
                            duration: timedelta) -> None:
        self._time_log.add_period(
                task_id=task_id, start=started_at, duration=duration)

        task = self._config.task_db.get(task_id)

        if self._config.calendar and task_id != BREAK_TASK_ID:
            self._config.calendar.add_event(
                Event(
                    task.title,
                    start=started_at,
                    end=started_at + duration))

    def _on_break_end(self, info: TimerInfo) -> None:
        assert info.task_id == BREAK_TASK_ID

        self._single_task_timer = None

        if self._config.notifier:
            self._config.notifier.send(
                    # TODO: "Long break ended" for long breaks.
                    title='Break ended', message=str(info.period_length),
                    urgency=Urgency.Critical, icon=_NOTIF['break_ended_icon'],
                    sound=_NOTIF['break_ended_sound'])

    def _on_work_period_end(self, info: TimerInfo) -> None:
        if self._break_manager.time_for_a_break():
            self.start(BREAK_TASK_ID, self._break_manager.get_break_duration())

        if self._config.notifier:
            task = self._config.task_db.get(info.task_id)
            self._config.notifier.send(
                    title='Work period ended', message=task.title,
                    urgency=Urgency.Critical, icon=_NOTIF['period_ended_icon'],
                    sound=_NOTIF['period_ended_sound'])


_NOTIF = _NOTIFICATION_RESOURCES = {
    'period_ended_icon': Icon(name='document-open-recent'),
    'period_ended_sound': Sound(name='complete'),
    'break_ended_icon': Icon(name='document-open-recent'),
    'break_ended_sound': Sound(name='dialog-error'),
}


class _BreakManager:
    """Decides how long is it time to rest (or not)."""

    def __init__(self, config: Config, clock: Clock = time) -> None:
        self._config = config
        self._time_log = config.time_log
        self._clock = clock

    def time_for_a_break(self) -> bool:
        # TODO: Do we always rest?  If the period ended on its own, not when it was
        # cancelled?
        return True

    @no_type_check  # pyright has hard time with the DataFrames for some reason.
    def get_break_duration(self) -> timedelta:
        """Returns the length of the next break.

        Depending on how much work was already done since the last long break,
        may return a `long_break_duration`.
        """
        # TODO: Just noticed it started a long break when it shouldn't had,
        # after the very first period of the day.  Not quite sure why,
        # maybe timezone-related stuff?
        # Add a bunch of logging here to be able to debug this next time it
        # happens.
        logs = self._time_log.get_data_frame()
        # Today logs.
        today = date.fromtimestamp(self._clock.time())
        tlogs = logs[logs.start.dt.date == today]
        twork = tlogs[tlogs.task_id != BREAK_TASK_ID]
        if twork.empty:
            return self._config.break_duration
        tbreaks = tlogs[tlogs.task_id == BREAK_TASK_ID]
        # To decide if it's time for a long break:
        # 1. Find the last long break today, or count from the start of the day
        long_breaks = tbreaks[tbreaks.duration > self._config.break_duration + timedelta(seconds=1)]
        if long_breaks.empty:
            count_from = twork.iloc[0].start
        else:
            count_from = long_breaks.iloc[-1].start
        # 2. Count from count_from how much work time is there.
        #    If it more than, say 3h, it time for a long break!
        worked_since_long_break = twork[twork.start >= count_from].duration.sum()
        time_for_a_long_break = worked_since_long_break >= self._config.long_break_after
        if time_for_a_long_break:
            return self._config.long_break_duration
        return self._config.break_duration


# TODO: Bugger: to bug when the timer is not ticking.


class NoActiveTimer:
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}()'
