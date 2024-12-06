"""A CLI for the work timer."""
# ruff: noqa: F401, F841
from datetime import date, datetime, timedelta
from pathlib import Path

from traitlets.config import Config
from IPython import embed
import pandas as pd

from work_timer import taskdb
from work_timer import timelog
from work_timer.utils.time import humanize_td


def console():
    """Pull in tasks and time log DataFrames, and switch to an IPython console."""
    # pylint: disable=unused-variable,possibly-unused-variable

    # TODO: Select the DBs according to a config.
    # task_db = taskdb.PersistentTaskDB(Path('~/dev-tasks/'))
    # time_log = timelog.PersistentTimeLog(Path('~/dev-timelog.json'))

    task_db = taskdb.PersistentTaskDB(Path('~/tasks/'))
    time_log = timelog.PersistentTimeLog(Path('~/timelog.json'))

    tasks = task_db.get_data_frame()
    logs = time_log.get_data_frame()
    logs = logs.merge(tasks, left_on='task_id', right_on='id', how='left')
    # Drop microseconds.  TODO: Do it somewhere in the DBs instead.
    logs.start = logs.start.apply(lambda dt: dt.replace(microsecond=0))
    logs.duration = logs.duration.apply(lambda td: pd.Timedelta(seconds=int(td.total_seconds())))
    # Today logs.
    tlogs = logs[logs.start.dt.date == date.today()]
    tlogs = tlogs.drop(columns=['description'])
    tlogs.start = tlogs.start.apply(lambda dt: dt.time())
    twork = tlogs[tlogs.task_id != -2]
    tbreaks = tlogs[tlogs.task_id == -2]

    # Print out what objects are available.
    print(f'Variables available: {list(sorted(locals()))}')

    pd.set_option('display.width', 0)
    pd.set_option('display.max_columns', 10)

    # TODO: Maybe print out some overall stats for today.

    # TODO: Pull the current period as well if the timer is running.

    # TODO: A `refresh()` function to pull new data.
    # TODO: Watch the DB changes, either just refresh automatically, or print about
    #       it in the console.

    # For reference, inside ipython that's the way to change the formatters:
    # ip = get_ipython()
    # formatter = ip.display_formatter.formatters['text/plain']
    # formatter.for_type(pd.DataFrame, data_frame_formatter)
    c = Config()
    c.PlainTextFormatter.type_printers = {pd.DataFrame: data_frame_formatter}
    embed(config=c)


def data_frame_formatter(df, p, cycle):
    assert not cycle
    timedelta_columns = [
            column
            for column, type_ in zip(df.columns, df.dtypes)
            if pd.api.types.is_timedelta64_dtype(type_)]
    df = df.assign(**{column: df[column].apply(humanize_td)
                      for column in timedelta_columns})
    p.text(str(df))


def main():
    console()


if __name__ == '__main__':
    main()
