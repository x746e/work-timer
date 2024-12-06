"""A CLI for the work timer."""
# ruff: noqa: F401, F841
from datetime import date, datetime, timedelta
from pathlib import Path

from IPython import embed
import pandas as pd

from work_timer import taskdb
from work_timer import timelog


def console():
    """Pull in tasks and time log DataFrames, and switch to an IPython console."""
    # pylint: disable=unused-variable
    task_db = taskdb.PersistentTaskDB(Path('~/dev-tasks/'))
    time_log = timelog.PersistentTimeLog(Path('~/dev-timelog.json'))
    # task_db = taskdb.PersistentTaskDB(Path('~/tasks/'))
    # time_log = timelog.PersistentTimeLog(Path('~/timelog.json'))
    tasks = task_db.get_data_frame()
    logs = time_log.get_data_frame()
    # Today logs.
    tlogs = logs[logs.start.dt.date == date.today()]
    twork = tlogs[tlogs.task_id != -2]
    tbreaks = tlogs[tlogs.task_id == -2]

    embed()


def main():
    console()


if __name__ == '__main__':
    main()
