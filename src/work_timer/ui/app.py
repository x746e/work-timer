"""The main work_time app entry point.

Should start some kind of UI.  For now it's a Textual TUI.
"""
import argparse
from datetime import datetime, timedelta
import os
from pathlib import Path
import sys

from desktop_notifier import DesktopNotifier
from gcsa.google_calendar import GoogleCalendar
from loguru import logger
import platformdirs

from textual.app import App, ComposeResult
from textual.widgets import Footer

from work_timer import taskdb
from work_timer import timelog
from work_timer.ui.task_list import TaskList
from work_timer.utils.time import td


# TODO: Make TaskList a Screen (or wrap it in a Screen)
#       If the timer is running, a TimerStatus line/widget on the top should show the current task,
#       and the timer state.

# TODO: Keys to switch between the TaskList and Timer screens.  And task stats.

# TODO: Tasks stats:
# * Raw log of logged Periods.
# * Group by task, day, week.
# * Drop into ipython with periods dataframe?
# * Or start a Juniper notebook.


class WorkTimer(App):

    # TODO: pylint is right, I need to refactor this.
    # pylint: disable=too-many-instance-attributes

    """The main Textual App."""

    def __init__(self,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                 task_db_path: Path,
                 time_log_path: Path,
                 notifier: DesktopNotifier,
                 calendar: GoogleCalendar,
                 work_period_duration: timedelta,
                 break_duration: timedelta,
                 long_break_duration: timedelta,
                 long_break_after: timedelta) -> None:
        super().__init__()
        self._task_db = taskdb.PersistentTaskDB(task_db_path)
        self._time_log = timelog.PersistentTimeLog(time_log_path)
        self.notifier = notifier
        self.calendar = calendar
        self._work_period_duration = work_period_duration
        self._break_duration = break_duration
        self._long_break_duration = long_break_duration
        self._long_break_after = long_break_after

    def compose(self) -> ComposeResult:
        # TODO: Package all these args into a "config" object of some sort?
        #       That will be potentially changed in the runtime.
        yield TaskList(self._task_db, self._time_log, self._work_period_duration,
                       self._break_duration, self._long_break_duration,
                       self._long_break_after)
        yield Footer()


def directory(p: str) -> Path:
    path = Path(p)
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f'{path} is not a valid directory')
    return path


def existing_file(p: str) -> Path:
    path = Path(p)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f'{path} is not a file')
    return path


def main():
    """The app entrypoint."""
    logger.remove()
    log_dir = platformdirs.user_state_path('wtx')
    process_name = os.path.basename(sys.argv[0])
    pid = os.getpid()
    now = datetime.now().replace(microsecond=0).isoformat()
    logger.add(log_dir / f'{process_name}-{pid}-{now}.log')

    parser = argparse.ArgumentParser()
    parser.add_argument('--taskdb', required=True, type=directory,
                        help='Path to the directory to store the tasks data.')
    parser.add_argument('--timelog', required=True, type=existing_file,
                        help='Path to the file to store the time log.')
    parser.add_argument('--work-period-duration', type=td, default='25m',
                        help='Work period duration')
    parser.add_argument('--break-duration', type=td, default='5m',
                        help='Break duration')
    parser.add_argument('--long-break-duration', type=td, default='20m',
                        help='Long break duration')
    parser.add_argument('--long-break-after', type=td, default='3h',
                        help='Have long break after working for this long')
    args = parser.parse_args()

    notifier = DesktopNotifier(app_name='Work Timer')
    calendar = GoogleCalendar(
            'd5fbba89f4666458ede53c569d41103943eb08325997ebd73d6d4db6156fa518@group.calendar.google.com')

    app = WorkTimer(task_db_path=args.taskdb, time_log_path=args.timelog,
                    notifier=notifier,
                    calendar=calendar,
                    work_period_duration=args.work_period_duration,
                    break_duration=args.break_duration,
                    long_break_duration=args.long_break_duration,
                    long_break_after=args.long_break_after)
    app.run()


if __name__ == "__main__":
    main()
