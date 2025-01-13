"""UIs for work planning."""
import datetime
from datetime import timedelta

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import Footer, Input, Label, Tree

from work_timer.config import get_dev_config
from work_timer.planning import Plan, PlanDB, Day, Week, format_period
from work_timer.timelog import TimeLog
from work_timer.taskdb import Task, TaskDB
from work_timer.timer import Timer
from work_timer.ui.base_task_list import TaskSelectionDialog
from work_timer.ui.task_list import TaskListTimerStarter
from work_timer.utils.typing import not_none
from work_timer.utils.time import humanize_td, td


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
        super().__init__(task_db=task_db, task_filter=self._planned_task_filter,
                         timer=timer)
        self._time_log = time_log
        self._plan = plan
        self._calc_stats()

    def _planned_task_filter(self, task: Task) -> bool:
        return self._plan.has(task.id)

    BINDINGS = TaskListTimerStarter.BINDINGS + [
        ('a', 'add'),
        ('r', 'remove'),
        ('+', 'inc_proportion'),
        ('-', 'dec_proportion'),
        ('R', 'refresh', 'Refresh tasks'),
    ]

    def on_mount(self) -> None:
        self._get_tree().root.expand_all()

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
        self._stats = dict(
                logs[
                    (logs.start >= dt_start) & (logs.start < dt_end) &
                    (logs.task_id > 0)
                ].groupby('task_id')[['duration']].sum().itertuples()
        )

    def _add_extra_task_info(self, title: str, task: Task) -> str:

        def t_round(hours: float) -> str:
            t = datetime.timedelta(hours=hours)
            # Round to the minute.
            floor = timedelta(minutes=t // timedelta(minutes=1))
            if floor % timedelta(minutes=1) > timedelta(seconds=30):
                floor += timedelta(minutes=1)
            return humanize_td(floor)

        if planned := self._plan.get(task.id):
            title += f'--- <p: {planned.proportion:.2f}/'
            title += f'{t_round(planned.proportion * self._plan.total_hours)} '
            if task.id in self._stats:
                title += f' a: {humanize_td(self._stats[task.id])}'
            title += '>'
        else:
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
        tree = self._get_tree()
        tree.focus()
        tree.root.expand_all()


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
