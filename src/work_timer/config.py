"""Configuration for the project.

Includes an ArgumentParser to get the Config object from command line
arguments.
"""
import argparse
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from desktop_notifier.sync import DesktopNotifierSync as DesktopNotifier
from gcsa.google_calendar import GoogleCalendar

from work_timer import taskdb
from work_timer import timelog
from work_timer.utils.time import td


@dataclass(kw_only=True)
class Config:  # pylint: disable=too-many-instance-attributes
    """Project configuration."""
    # Dependencies.
    task_db: taskdb.TaskDB
    time_log: timelog.TimeLog
    calendar: GoogleCalendar | None = None
    notifier: DesktopNotifier | None = None

    # Settings.
    work_period_duration: timedelta
    break_duration: timedelta
    long_break_duration: timedelta
    long_break_after: timedelta
    bug_after: timedelta | None = None
    bug_every: timedelta | None = None


def get_config_from_args() -> Config:
    """Parses sys.argv into a Config object."""
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

    parser.add_argument('--calendar-id',
                        help='If set, add an event to that Google Calendar for each work period.')

    parser.add_argument('--enable-notifications', action='store_true',
                        help='Notify about ends of work periods and breaks.')
    parser.add_argument('--bug-after', type=td,
                        help='Bug with a notification after timer is not running for this much time.')
    parser.add_argument('--bug-every', type=td,
                        help='How often to bug after the first bugging notification.  If not set, '
                             'defaults to the value of --bug-after')
    args = parser.parse_args()

    if (args.bug_after or args.bug_every) and not args.enable_notifications:
        parser.error('--enable-notifications must be set for --bug-* arguments to make sense.')
    if args.bug_every and not args.bug_after:
        parser.error('--bug-every is set, but bugging is not enabled: you probably want '
                     'to set --bug-after instead.')
    if args.bug_after and not args.bug_every:
        args.bug_every = args.bug_after

    config = {}
    config['task_db'] = taskdb.PersistentTaskDB(args.taskdb)
    config['time_log'] = timelog.PersistentTimeLog(args.timelog)
    if args.calendar_id:
        config['calendar'] = GoogleCalendar(args.calendar_id)
    if args.enable_notifications:
        config['notifier'] = DesktopNotifier(app_name='Work Timer')

    config['work_period_duration'] = args.work_period_duration
    config['break_duration'] = args.break_duration
    config['long_break_duration'] = args.long_break_duration
    config['long_break_after'] = args.long_break_after

    config['bug_after'] = args.bug_after
    config['bug_every'] = args.bug_every

    return Config(**config)  # pylint: disable=missing-kwoa


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


def get_test_config(**overrides) -> Config:
    """Generate a Config suitable for use for tests and development."""
    from work_timer.utils import fake_tasks  # pylint: disable=import-outside-toplevel
    task_db = fake_tasks.get_task_db()
    conf = {
        'task_db': task_db,
        'time_log': timelog.TimeLog(),
        'work_period_duration': td('10s'),
        'break_duration': td('5s'),
        'long_break_duration': td('20s'),
        'long_break_after': td('20s')
    }
    conf.update(overrides)
    config = Config(**conf)
    return config
