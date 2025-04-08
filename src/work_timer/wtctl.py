"""A CLI for the work timer."""
# ruff: noqa: F401, F841
import argparse
from datetime import date, datetime, time, timedelta
from pathlib import Path
import re
from typing import no_type_check

from bigtree.node.node import Node as BigTreeNode
from bigtree.tree.construct import dataframe_to_tree_by_relation
from bigtree.tree.export import stdout

from traitlets.config import Config
from IPython import embed
import pandas as pd

from work_timer import config
from work_timer import taskdb
from work_timer import timelog
from work_timer.utils.time import td, humanize_td, round_td


@no_type_check  # pyright has issues with Pandas.
def console(args):
    """Pull in tasks and time log DataFrames, and switch to an IPython console."""
    # pylint: disable=unused-variable,possibly-unused-variable

    task_db = taskdb.PersistentTaskDB(args.taskdb)
    time_log = timelog.PersistentTimeLog(args.timelog)

    tasks = task_db.get_data_frame()
    logs = time_log.get_data_frame()
    logs = logs.merge(tasks, left_on='task_id', right_on='id', how='left')
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

    # Some stats.
    print('So far today:')
    summary = tlogs.groupby(['title'])[['duration']].sum()
    summary.sort_values('duration', ascending=False, inplace=True)
    print(format_timedelta_columns(summary))
    print()

    ## Planning stats
    # Find planned for today parent task.
    @no_type_check
    def get_tag(descr: str, tag: str) -> str:
        return re.search(rf'^{tag}=(?P<tag_value>.*)$', descr, re.M).group('tag_value')

    today_planned_task = tasks[tasks.title == '2025-01-02']
    if len(today_planned_task) == 1:

        total = td(get_tag(descr=today_planned_task.description.iloc[0], tag='TOTAL'))
        # print(f'Estimated work hours today: {humanize_td(total)}')

        planned_tasks = tasks[tasks.index.isin(today_planned_task.child_ids.iloc[0])]
        # print(planned_tasks)
        # print(planned_tasks.description.apply(lambda desc: get_tag(desc, 'PLANNED')))

        # For each task there look at PLANNED= tag in description.
        # Show alongside with the summary.

    # TODO: Pull the current period as well if the timer is running.

    # TODO: A `refresh()` function to pull new data.
    # TODO: Watch the DB changes, either just refresh automatically, or print about
    #       it in the console.

    # For reference, inside ipython that's the way to change the formatters:
    # ip = get_ipython()
    # formatter = ip.display_formatter.formatters['text/plain']
    # formatter.for_type(pd.DataFrame, data_frame_formatter)
    print('\n')
    c = Config()
    c.PlainTextFormatter.type_printers = {pd.DataFrame: _data_frame_formatter}
    embed(config=c)


def _data_frame_formatter(df, p, cycle):
    assert not cycle
    p.text(str(format_timedelta_columns(df)))


def format_timedelta_columns(df: pd.DataFrame) -> pd.DataFrame:
    timedelta_columns = [
            column
            for column, type_ in zip(df.columns, df.dtypes)
            if pd.api.types.is_timedelta64_dtype(type_)]
    return df.assign(**{column: df[column].apply(humanize_td)
                     for column in timedelta_columns})


def edit_task(args) -> None:
    """CLI command to edit a Task."""
    db = taskdb.PersistentTaskDB(args.taskdb)
    task = db.get(args.task_id)

    assert args.status or args.priority, (
        'No `wtctl edit` action is specified.')

    if args.status:
        task.status = args.status
    if args.priority:
        task.priority = args.priority
    db.update(task, message=args.message)


@no_type_check  # pyright has issues with Pandas.
def stats(args) -> None:
    """Print statistics about work done today."""

    task_db = taskdb.PersistentTaskDB(args.taskdb)
    time_log = timelog.PersistentTimeLog(args.timelog)

    tasks = task_db.get_data_frame()
    logs = time_log.get_data_frame()

    if args.weekly:
        today = date.today()
        days_since_monday = today.weekday()
        this_weeks_monday = today - timedelta(days=days_since_monday)
        logs = logs[this_weeks_monday <= logs.start.dt.date]
    else:
        logs = logs[logs.start.dt.date == date.today()]

    logs = logs[logs.task_id > 0]
    logs = logs.merge(tasks, left_on='task_id', right_on='id', how='left')

    time_spent_by_task = {
        task_id: round_td(duration, td('5m'))
        for task_id, duration in logs[
            # That are real tasks, not breaks, root, etc.
            (logs.task_id > 0)
        ].groupby('task_id')  # Group the time spend by task id,
        [['duration']].sum()  # sum all the individual log records.
        .itertuples()         # Convert into (task_id, timedelta) tuples.
    }

    task_tree = dataframe_to_tree_by_relation(
        tasks[tasks.index > 0].reset_index(), child_col='id', parent_col='parent_id',
        attribute_cols=['title'])

    def rollup_time_spent(node: BigTreeNode) -> timedelta:
        task_id = node.node_name

        spent_on_this_task = time_spent_by_task.get(task_id, timedelta())
        spent_on_children = sum(
            (rollup_time_spent(child) for child in node.children),
            start=timedelta())
        spent_on_subtree = spent_on_this_task + spent_on_children

        alias = node.get_attr('title') or '/'
        if spent_on_subtree:
            alias += f': [green]{humanize_td(spent_on_subtree)}[/]'
        if spent_on_this_task and spent_on_this_task != spent_on_subtree:
            alias += f' ({humanize_td(spent_on_this_task)} on node)'

        node.set_attrs({'spent_on_node': spent_on_this_task,
                        'spent_on_subtree': spent_on_subtree,
                        'alias': alias})
        return spent_on_subtree

    rollup_time_spent(task_tree)


    def filter_out_empty(node: BigTreeNode) -> BigTreeNode:
        assert node.get_attr('spent_on_subtree')
        return BigTreeNode(node.node_name, children=[
            filter_out_empty(child) for child in node.children if child.get_attr('spent_on_subtree')
        ], alias=node.get_attr('alias'))

    task_tree = filter_out_empty(task_tree)

    _print_tree(task_tree)


def _print_tree(task_tree):
    _monkey_patch_print_tree()
    stdout.print_tree(task_tree, alias='alias')


# TODO: Do I really need bigtree?  The need to monkey patch suggests I may be better off with a simple
# local solution.
def _monkey_patch_print_tree():
    # pylint: disable=redefined-builtin,import-outside-toplevel
    from rich import print
    if not hasattr(stdout, 'print'):
        stdout.print = print  # type: ignore


def _all_parent_titles(task_id, tasks):

    def titles(task_id):
        if task_id == -10:  # root task
            return []
        task = tasks[tasks.index == task_id].iloc[0]
        return titles(task.parent_id) + [task.title]

    return ' '.join(titles(task_id))


def main():
    """The main entrypoint for the wtctl tool."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--taskdb', required=True, type=config.directory,
                        help='Path to the directory to store the tasks data.')
    parser.add_argument('--timelog', required=True, type=config.existing_file,
                        help='Path to the file to store the time log.')

    subparsers = parser.add_subparsers(required=True)

    # wtctl console / wtctl cli
    console_parser = subparsers.add_parser('console', aliases=['cli'])
    console_parser.set_defaults(func=console)

    # wtctl stats
    stats_parser = subparsers.add_parser('stats')
    stats_parser.add_argument('--weekly', action='store_true')
    stats_parser.set_defaults(func=stats)

    # wtctl edit -t 123 --status done
    edit_parser = subparsers.add_parser('edit-task', aliases=['edit'])
    edit_parser.add_argument('-t', '--task-id', required=True, type=int,
                             help='Task ID to edit.')
    edit_parser.add_argument('-s', '--status', type=taskdb.Task.Status,
                             choices=list(taskdb.Task.Status))
    edit_parser.add_argument('-p', '--priority', type=taskdb.Task.Priority,
                             choices=list(taskdb.Task.Priority))
    edit_parser.add_argument('-m', '--message')
    edit_parser.set_defaults(func=edit_task)
    # TODO: Do parser.error() when no task edit action is specified.  E.g.:
    #   edit_parser.set_defaults(validate=validate_edit_args)
    #   args.validate(args)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
