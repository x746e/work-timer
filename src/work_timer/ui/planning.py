"""UIs for work planning."""
import datetime

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Input, Label, Tree

from work_timer.config import get_dev_config
from work_timer.timelog import TimeLog
from work_timer.taskdb import Task, TaskDB
from work_timer.planning import Plan, PlanDB, Day, Week, format_period
from work_timer.ui.base_task_list import BaseTaskList
from work_timer.ui.base_task_list import TaskSelectionDialog
from work_timer.utils.typing import not_none
from work_timer.utils.time import humanize_td, td


class PlanSelection(Widget):

    """UI to select an existing plan, or to add a new one."""

    BINDINGS = [
        ('a', 'add'),
    ]

    def __init__(self, task_db: TaskDB, time_log: TimeLog, plan_db: PlanDB) -> None:
        super().__init__()
        self._task_db = task_db
        self._time_log = time_log
        self._plan_db = plan_db

    def compose(self) -> ComposeResult:
        tree = Tree(label='/')

        for period, plan in sorted(self._plan_db.get_all().items()):
            tree.root.add_leaf(format_period(period), data=plan)

        tree.root.expand_all()

        yield tree

    @work
    async def action_add(self) -> None:
        planned_period = datetime.date.today()
        plan = Plan(period=Day(planned_period))
        await self.app.push_screen_wait(PlanningScreen(self._task_db, self._time_log, plan))
        self._plan_db.add(plan)
        await self.redraw()

    @work
    async def on_tree_node_selected(self, evt) -> None:
        plan = evt.node.data
        await self.app.push_screen_wait(PlanningScreen(self._task_db, self._time_log, plan))
        self._plan_db.update(plan)
        await self.redraw()

    async def redraw(self) -> None:
        await self.recompose()
        self.query_one(Tree).focus()


class Planning(Widget):

    """UI for displaying and editing a Plan."""

    DEFAULT_CSS = """
    #total-hours-container {
        height: 3;
        Label {
            padding-top: 1;
        }
    }
    """

    def __init__(self, task_db: TaskDB, time_log: TimeLog, plan: Plan) -> None:
        super().__init__()
        self._task_db = task_db
        self._time_log = time_log
        self._plan = plan

    def on_input_changed(self, evt) -> None:
        self._plan.total_hours = float(evt.value)

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label('Total hours:'),
            Input(id='total_hours', value=str(self._plan.total_hours)),
            id='total-hours-container',
        )
        yield PlanningTaskList(self._task_db, self._time_log, self._plan)


class PlanningTaskList(BaseTaskList):

    """A task list with the tasks planned for the period."""

    def __init__(self, task_db: TaskDB, time_log: TimeLog, plan: Plan) -> None:
        super().__init__(task_db, self._planned_task_filter)
        self._time_log = time_log
        self._plan = plan
        self._calc_stats()

    def _planned_task_filter(self, task: Task) -> bool:
        return self._plan.has(task.id)

    BINDINGS = [
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
        if planned := self._plan.get(task.id):
            title += f'--- <p: {planned.proportion}/'
            title += f'{planned.proportion * self._plan.total_hours}h '
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


class PlanningScreen(ModalScreen):

    """A Screen with Plan viewing/editing widgets."""

    BINDINGS = [
        ('ctrl+s', 'save_and_close', 'Save and close'),
    ]

    def __init__(self, task_db: TaskDB, time_log: TimeLog, plan: Plan) -> None:
        super().__init__()
        self._task_db = task_db
        self._time_log = time_log
        self._plan = plan

    def compose(self) -> ComposeResult:
        yield Planning(self._task_db, self._time_log, self._plan)
        yield Footer()

    def action_save_and_close(self) -> None:
        self.dismiss(self._plan)


def main() -> None:
    """A way to exercise the widget in isolation, useful for development."""

    import pathlib  # pylint: disable=import-outside-toplevel

    class PlanningApp(App):  # pylint: disable=missing-class-docstring

        def compose(self) -> ComposeResult:
            config = get_dev_config()
            plan_db_path = pathlib.Path('~/dev-plandb').expanduser()
            plan_db = PlanDB(plan_db_path)
            yield PlanSelection(config.task_db, config.time_log, plan_db)
            yield Footer()

    app = PlanningApp()
    app.run()


if __name__ == '__main__':
    main()
