"""UIs for work planning."""
import datetime
from datetime import timedelta

from bigtree.tree.construct import dataframe_to_tree_by_relation
from bigtree.tree.export import tree_to_dataframe

from rich.text import Text

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import Footer, Input, Label, Tree
from textual.widgets.tree import TreeNode

from work_timer.config import get_dev_config
from work_timer.planning import Plan, PlanDB, Day, Week, format_period
from work_timer.timelog import TimeLog
from work_timer.taskdb import Task, TaskDB
from work_timer.timer import Timer
from work_timer.ui.base_task_list import TaskSelectionDialog
from work_timer.ui.debug_panel import DebugPanel
from work_timer.ui.task_list import TaskListTimerStarter
from work_timer.utils.typing import not_none
from work_timer.utils.time import round_td, humanize_td, td


class _PlanSelection(Widget):

    """UI to select an existing plan, or to add a new one."""

    BINDINGS = [
        ('a', 'add'),
    ]

    def __init__(self, task_db: TaskDB, time_log: TimeLog, timer: Timer,
                 plan_db: PlanDB) -> None:
        super().__init__()
        self._task_db = task_db
        self._time_log = time_log
        self._timer = timer
        self._plan_db = plan_db

    def compose(self) -> ComposeResult:
        tree = Tree(label='/')

        for period, plan in sorted(self._plan_db.get_all().items()):
            tree.root.add_leaf(format_period(period), data=plan)

        tree.root.expand_all()

        yield tree

    @work
    async def action_add(self) -> None:
        """Add a new plan."""
        planned_period = datetime.date.today()
        plan = Plan(period=Day(planned_period))
        await self.app.push_screen_wait(
            _PlanEditorScreen(
                task_db=self._task_db,
                time_log=self._time_log,
                timer=self._timer,
                plan=plan,
            )
        )
        self._plan_db.add(plan)
        await self.redraw()

    @work
    async def on_tree_node_selected(self, evt) -> None:
        """Open the selected plan."""
        plan = evt.node.data
        await self.app.push_screen_wait(
            _PlanEditorScreen(
                task_db=self._task_db,
                time_log=self._time_log,
                timer=self._timer,
                plan=plan,
            )
        )
        self._plan_db.update(plan)
        await self.redraw()

    async def redraw(self) -> None:
        await self.recompose()
        self.query_one(Tree).focus()


class PlanningScreen(Screen):
    """A screen with PlanningScreen widget."""

    # pylint: disable=too-many-arguments,too-many-positional-arguments

    def __init__(self, task_db: TaskDB, time_log: TimeLog, timer: Timer,
                 plan_db: PlanDB, name: str | None = None) -> None:
        super().__init__(name=name)
        self._task_db = task_db
        self._time_log = time_log
        self._timer = timer
        self._plan_db = plan_db

    def compose(self) -> ComposeResult:
        yield _PlanSelection(task_db=self._task_db,
                             timer=self._timer,
                             time_log=self._time_log,
                             plan_db=self._plan_db)
        yield Footer()


class _PlanEditor(Widget):

    """UI for displaying and editing a Plan."""

    DEFAULT_CSS = """
    #total-hours-container {
        height: 3;
        Label {
            padding-top: 1;
        }
    }
    """

    def __init__(self, task_db: TaskDB, time_log: TimeLog, timer: Timer, plan: Plan) -> None:
        super().__init__()
        self._task_db = task_db
        self._time_log = time_log
        self._timer = timer
        self._plan = plan

    def on_input_changed(self, evt) -> None:
        self._plan.total_hours = float(evt.value)

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label('Total hours:'),
            Input(id='total_hours', value=str(self._plan.total_hours)),
            id='total-hours-container',
        )
        yield _PlanningTaskList(task_db=self._task_db,
                                time_log=self._time_log,
                                timer=self._timer,
                                plan=self._plan)


class _PlanningTaskList(TaskListTimerStarter):

    """A task list with the tasks planned for the period."""

    def __init__(self, task_db: TaskDB, timer: Timer, time_log: TimeLog, plan: Plan) -> None:
        self._task_db = task_db
        self._time_log = time_log
        self._plan = plan
        self._calc_stats()
        super().__init__(task_db=task_db, task_filter=self._planned_task_filter,
                         timer=timer)

    def _planned_task_filter(self, task: Task) -> bool:
        return (self._plan.has(task.id) or task.id in self._time_spent)

    BINDINGS = TaskListTimerStarter.BINDINGS + [
        ('a', 'add'),
        ('r', 'remove'),
        ('+', 'inc_proportion'),
        ('-', 'dec_proportion'),
        ('R', 'refresh', 'Refresh tasks'),
    ]

    def on_mount(self) -> None:
        self._tree.root.expand_all()

    def _calc_stats(self):
        logs = self._time_log.get_data_frame()
        tasks = self._task_db.get_data_frame()
        logs = logs.merge(tasks, left_on='task_id', right_on='id', how='left')

        # TODO: Special handling for the periods that go over midnight.
        # TODO: Factor this out somewhere.
        match self._plan.period:
            case Day() as day:
                dt_start = datetime.datetime.combine(day.day, datetime.time())
                dt_end = dt_start + datetime.timedelta(days=1)
            case Week():
                raise NotImplementedError

        self._time_spent = dict(
            logs[
                (logs.start >= dt_start) & (logs.start < dt_end) &
                (logs.task_id > 0)
            ].groupby('task_id')[['duration']].sum().itertuples()
        )

        root = dataframe_to_tree_by_relation(
                tasks[tasks.index > 0].reset_index(), child_col='id', parent_col='parent_id',
                attribute_cols=[])

        total_time_planned = timedelta(hours=self._plan.total_hours)

        def rollup_time_spent(node) -> timedelta:
            task_id = node.node_name

            spent_on_this_task = self._time_spent.get(task_id, timedelta())
            spent_on_children = sum(
                (rollup_time_spent(child) for child in node.children),
                start=timedelta())

            spent_time = spent_on_this_task + spent_on_children
            node.set_attrs({'spent_time': spent_time})
            return spent_time

        def rollup_time_planned(node) -> timedelta:
            task_id = node.node_name

            planned_for_this_task = timedelta()
            if planned := self._plan.get(task_id):
                planned_for_this_task = planned.proportion * total_time_planned
            planned_for_children = sum(
                (rollup_time_planned(child) for child in node.children),
                start=timedelta())

            planned_time = planned_for_this_task + planned_for_children
            node.set_attrs({'planned_time': planned_time})
            return planned_time

        rollup_time_spent(root)
        rollup_time_planned(root)

        df = tree_to_dataframe(
            root, attr_dict={'spent_time': 'spent_time', 'planned_time': 'planned_time'}
        )
        df = df.drop(columns=['path'])
        self._rolled_up_time_spent = dict(
                df.drop(columns=['planned_time']).itertuples(index=False))
        self._rolled_up_time_planned = dict(
                df.drop(columns=['spent_time']).itertuples(index=False))

    def _add_extra_task_info(self, title: str, task: Task,
                             parent_node: TreeNode, tree: Tree) -> str:

        def fmt_td(t: timedelta) -> str:
            return humanize_td(round_td(t, td('1m')))

        def tree_depth() -> int:
            node = parent_node
            n = 1
            while node != tree.root:
                n += 1
                node = not_none(node.parent)
            return n

        screen_width = self.app.size.width
        indent = tree_depth() * tree.guide_depth
        twidth = indent + Text.from_markup(title).cell_len
        col_padding = 1
        available_space = screen_width - twidth - col_padding

        t_planned = self._rolled_up_time_planned[task.id]

        t_actual = self._rolled_up_time_spent[task.id]

        if t_actual or t_planned:
            einfo = f'({fmt_td(t_actual)}/{fmt_td(t_planned)}) '
            einfo += _time_graph(
                planned=t_planned,
                actual=t_actual,
            )
            einfo = einfo.rjust(available_space, ' ')
            title += einfo

        if not t_planned:
            title = f'[i]{title}[/i]'

        return title

    @work
    async def action_add(self) -> None:
        task_id = await self.app.push_screen_wait(TaskSelectionDialog(self._task_db))
        if not task_id:
            return
        self._plan.add(task_id)
        await self.action_refresh()

    def action_remove(self) -> None:
        tree_node = not_none(self._get_selected_task_node())
        task = self._node_to_task(tree_node)
        self._plan.remove(task.id)
        self._remove_node(tree_node)

    async def action_inc_proportion(self) -> None:
        node = not_none(self._get_selected_task_node())
        task = self._node_to_task(node)
        self._plan.inc(task.id, by=td('30m'))
        self._refresh_node(node, task)

    async def action_dec_proportion(self) -> None:
        node = not_none(self._get_selected_task_node())
        task = self._node_to_task(node)
        self._plan.dec(task.id, by=td('30m'))
        self._refresh_node(node, task)

    async def action_refresh(self):
        await self.recompose()
        self._tree.focus()
        self._tree.root.expand_all()


def _time_graph(planned: timedelta, actual: timedelta) -> str:
    """
    >>> _time_graph(planned=td('3h'), actual=td('0h'))
    '------'
    >>> _time_graph(planned=td('3h'), actual=td('2h'))
    '====--'
    >>> _time_graph(planned=td('1h'), actual=td('2h'))
    '==!!'
    """
    if actual <= planned:
        planned_spent = actual
        planned_not_spent = planned - actual
        overspent = timedelta()
    else:
        planned_spent = planned
        planned_not_spent = timedelta()
        overspent = actual - planned
    i_len = td('30m')
    planned_spent_i = round(planned_spent / i_len)
    planned_not_spent_i = round(planned_not_spent / i_len)
    overspent_i = round(overspent / i_len)
    return ('=' * planned_spent_i +
            '-' * planned_not_spent_i +
            '!' * overspent_i)


class _PlanEditorScreen(ModalScreen):

    """A Screen with Plan viewing/editing widgets."""

    BINDINGS = [
        ('ctrl+s', 'save_and_close', 'Save and close'),
    ]

    def __init__(self, task_db: TaskDB, time_log: TimeLog, timer: Timer, plan: Plan) -> None:
        super().__init__()
        self._task_db = task_db
        self._time_log = time_log
        self._timer = timer
        self._plan = plan

    def compose(self) -> ComposeResult:
        yield _PlanEditor(task_db=self._task_db,
                          time_log=self._time_log,
                          timer=self._timer,
                          plan=self._plan)
        if self.app._config.debug:  # type: ignore  # pylint: disable=protected-access
            yield DebugPanel()
        yield Footer()

    def action_save_and_close(self) -> None:
        self.dismiss(self._plan)


def main() -> None:
    """A way to exercise the widget in isolation, useful for development."""

    # pylint: disable=import-outside-toplevel
    import pathlib
    from work_timer.utils.scheduler import Scheduler

    class PlanningApp(App):  # pylint: disable=missing-class-docstring

        def compose(self) -> ComposeResult:
            config = get_dev_config()
            timer = Timer(config, scheduler=Scheduler())
            plan_db_path = pathlib.Path('~/dev-plandb').expanduser()
            plan_db = PlanDB(plan_db_path)
            yield _PlanSelection(task_db=config.task_db,
                                 timer=timer,
                                 time_log=config.time_log,
                                 plan_db=plan_db)
            yield Footer()

    app = PlanningApp()
    app.run()


if __name__ == '__main__':
    main()
