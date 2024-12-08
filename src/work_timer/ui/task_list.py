"""A widget to showing a list (or a tree) of tasks."""
import collections
from datetime import date, datetime, timedelta
from typing import no_type_check

from gcsa.event import Event

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from work_timer import taskdb
from work_timer.config import Config
from work_timer.taskdb import TaskID, Task
from work_timer.ui.timer import TimerScreen
from work_timer.ui.task_editor import TaskEditor
from work_timer.utils.typing import not_none


class TaskList(Widget):
    """A widget to showing a list (or a tree) of tasks."""

    # pylint: disable=too-many-instance-attributes

    BINDINGS = [
        ('e', 'edit', 'Edit'),
        ('m', 'mark_done', 'Mark DONE'),
        ('c', 'create', 'New task'),  # with the cursor_node as a parent.
        ('s', 'start', 'Start the timer'),  # start the timer with the cursor_node.
        ('-', 'dec_prio', 'Decrease priority'),
        ('+', 'inc_prio', 'Increase priority'),
        ('q', 'quit', 'Quit'),
        ('j', 'cursor_down'),
        ('k', 'cursor_up'),
    ]

    def __init__(self, config: Config):
        super().__init__()
        self._task_db = config.task_db
        self._time_log = config.time_log

        self._tasks = list(self._task_db.get_all().values())
        self._parent_to_task = self._group_tasks_by_parent_id(self._tasks)
        self._task_id_to_node_id = {}

        self._config = config

        self._is_timer_ticking = False
        self._not_ticking_since = datetime.now()
        self._bugged_last_at = None
        self.set_interval(5, self._maybe_bug_about_not_ticking_timer)

    async def _maybe_bug_about_not_ticking_timer(self) -> None:
        if self._is_timer_ticking:
            return
        if not self._config.bug_after:
            return
        if datetime.now() - self._not_ticking_since < self._config.bug_after:
            return
        if (self._bugged_last_at and
                datetime.now() - self._bugged_last_at < not_none(self._config.bug_every)):
            return
        if self._config.notifier:
            await self._config.notifier.send(
                    title='The timer is not ticking!', message='Go do some work!',
                    icon='document-open-recent')
        self._bugged_last_at = datetime.now()

    def compose(self) -> ComposeResult:
        yield self._make_tree_with_tasks()

    def _get_selected_task_node(self) -> TreeNode | None:
        cursor_node = not_none(self._get_tree().cursor_node)
        if cursor_node.is_root:
            return None
        assert cursor_node.data is not None
        assert isinstance(cursor_node.data, taskdb.Task)
        return cursor_node

    def _get_tree(self) -> Tree:
        return not_none(self.query_one(Tree))

    def action_mark_done(self) -> None:
        """Mark the task as DONE.

        Hide it from the view if doesn't have children.
        """
        node = not_none(self._get_selected_task_node())

        # Mark as done.
        task = not_none(node.data)
        task.status = taskdb.Task.Status.DONE
        self._task_db.update(task)

        # If deleting this node makes the parent "childless", then remove the
        # expand/collapse triangular marker from the parent node.
        if node.parent and not node.children:
            if len(node.siblings) == 1:
                node.parent.allow_expand = False

        # And remove it from the UI.
        if not node.children:
            node.remove()

    def action_dec_prio(self) -> None:
        """Decrease the Task's priority by one."""
        node = not_none(self._get_selected_task_node())
        task = not_none(node.data)

        all_priorities = list(taskdb.Task.Priority)
        idx = all_priorities.index(task.priority)
        if idx + 1 >= len(all_priorities):
            return

        task.priority = all_priorities[idx + 1]
        self._task_db.update(task)

        node.set_label(_title_with_style(task))
        node.refresh()

    def action_inc_prio(self) -> None:
        """Increase the Task's priority by one."""
        node = not_none(self._get_selected_task_node())
        task = not_none(node.data)

        all_priorities = list(taskdb.Task.Priority)
        idx = all_priorities.index(task.priority)
        if idx - 1 < 0:
            return

        task.priority = all_priorities[idx - 1]
        self._task_db.update(task)

        node.set_label(_title_with_style(task))
        node.refresh()

    @work
    async def action_edit(self) -> None:
        """Action to edit the currently selected task.

        Pushes the `TaskEditor` Screen, then updates the UI according to the
        returned `TaskEditor.Changed` message.  `TaskEditor` takes care of
        updating the `TaskDB`.
        """
        node = self._get_selected_task_node()
        if not node:
            return

        task = not_none(node.data)
        resp = await self.app.push_screen_wait(TaskEditor(self._task_db, task))
        match resp:
            case TaskEditor.Changed(old_task, new_task):
                if old_task.parent_id != new_task.parent_id:
                    # If reparented, remove the node, then readd it with its children.
                    node.remove()
                    new_node = self._add_task(new_task)
                    # Not sure why, but it appears I need both these calls.
                    self._get_tree().move_cursor(new_node)
                    self._get_tree().select_node(new_node)
                else:
                    node.set_label(_title_with_style(new_task))
                    node.data = new_task
                    node.refresh()
            case TaskEditor.Deleted():
                assert not node.children
                node.remove()
            case None:
                pass
            case _:
                assert False, 'unreachable'

    @work
    async def action_create(self) -> None:
        """Action to create a new Task.

        The new task will have the currently selected task in the tree set as
        its parent.

        Uses `TaskEditor` screen to create the task.  The editor takes care of
        adding the task to the DB.  This function then adds the task using the
        information on the returned `TaskEditor.Changed` message.
        """
        parent_id = None
        parent_node = not_none(self._get_tree().cursor_node)
        if not parent_node.is_root:
            parent_id = not_none(parent_node.data).id

        new_task = taskdb.Task(title='', parent_id=parent_id)
        changed = await self.app.push_screen_wait(TaskEditor(self._task_db, new_task))
        if changed:
            self._add_task(changed.new)

    @work
    async def action_start(self) -> None:
        """Start the Timer with the selected task.

        Pushes the TimerScreen.  After the work period ends, starts a break
        period.
        """
        node = self._get_selected_task_node()
        if not node:
            return

        # TODO: All this logic doesn't really belong here.

        task = not_none(node.data)

        if self._config.calendar:
            self._config.calendar.add_event(
                Event(
                    task.title,
                    start=datetime.now(), end=datetime.now() + self._config.work_period_duration))

        self._is_timer_ticking = True
        await self.app.push_screen_wait(TimerScreen(task, self._config.work_period_duration,
                                                    self._time_log, start=True))
        self._is_timer_ticking = False
        self._not_ticking_since = datetime.now()
        if self._config.notifier:
            await self._config.notifier.send(
                    title='Work period ended', message=task.title,
                    icon='document-open-recent', sound='complete')  # type: ignore

        def should_rest() -> bool:
            # TODO: Do we always rest?  If the period ended on its own, not when it was
            # cancelled?
            return True

        @no_type_check  # pyright has hard time with the DataFrames for some reason.
        def get_rest_length() -> timedelta:
            logs = self._time_log.get_data_frame()
            # Today logs.
            tlogs = logs[logs.start.dt.date == date.today()]
            twork = tlogs[tlogs.task_id != taskdb.BREAK_TASK_ID]
            if twork.empty:
                return self._config.break_duration
            tbreaks = tlogs[tlogs.task_id == taskdb.BREAK_TASK_ID]
            # To decide if it's time for a long break:
            # 1. Find the last long break today, or count from the start of the day
            long_breaks = tbreaks[tbreaks.duration > self._config.break_duration + timedelta(seconds=1)]
            if long_breaks.empty:
                count_from = twork.iloc[0].start
            else:
                count_from = long_breaks.iloc[-1].start
            # 2. Count from count_from how much work time is there.
            #    If it more than, say 3h, it time for a long break!
            worked_since_long_break = twork[twork.start > count_from].duration.sum()
            time_for_a_long_break = worked_since_long_break > self._config.long_break_after
            if time_for_a_long_break:
                return self._config.long_break_duration
            return self._config.break_duration

        if should_rest():
            rest_length = get_rest_length()
            await self.app.push_screen_wait(
                    TimerScreen(taskdb.BREAK, rest_length, self._time_log, start=True))
            if self._config.notifier:
                await self._config.notifier.send(
                        title='Break ended', message=str(rest_length), icon='document-open-recent',
                        sound='dialog-error')  # type: ignore

    def action_cursor_up(self):
        self._get_tree().action_cursor_up()

    def action_cursor_down(self):
        self._get_tree().action_cursor_down()

    def action_quit(self):
        self.app.exit()

    def check_action(
        self, action: str, parameters: tuple[object, ...]
    ) -> bool | None:
        if action in ('edit', 'mark_done', 'start', 'inc_prio', 'dec_prio'):
            if not self._get_selected_task_node():
                return None  # Mark the action as disabled.
        return True

    # On selection change, get Textual to call `check_action` to disable the
    # task-changing ones when no tasks are selected.
    def on_tree_node_highlighted(self, unused_event: Tree.NodeHighlighted) -> None:
        self.refresh_bindings()

    def _make_tree_with_tasks(self) -> Tree:
        """Returns a Tree widget populated with Tasks."""

        tree = Tree[taskdb.Task]('')

        for task in self._parent_to_task[None]:
            if not self._whole_subtree_is_completed(task):
                self._add_task(task, parent_node=tree.root)

        tree.root.expand_all()
        return tree

    def _add_task(self, task: Task, parent_node: TreeNode | None = None) -> TreeNode:
        """Adds a `task`, with all its children, as a child of `parent_node`."""

        def get_node_by_task_id(task_id: TaskID | None) -> TreeNode:
            if task_id is None:
                return self._get_tree().root
            node_id = self._task_id_to_node_id[task_id]
            return self._get_tree().get_node_by_id(node_id)

        if not parent_node:
            parent_node = get_node_by_task_id(task.parent_id)

        node = parent_node.add(_title_with_style(task), data=task)
        parent_node.allow_expand = True
        self._task_id_to_node_id[task.id] = node.id
        children = self._parent_to_task.get(task.id, [])
        children_to_show = [c for c in children if not self._whole_subtree_is_completed(c)]

        for child_task in children_to_show:
            self._add_task(child_task, parent_node=node)

        if not children_to_show:
            node.allow_expand = False

        return node

    def _whole_subtree_is_completed(self, task: Task) -> bool:
        if task.status != Task.Status.DONE:
            return False
        children = self._parent_to_task.get(task.id, [])
        return all(self._whole_subtree_is_completed(child) for child in children)

    def _group_tasks_by_parent_id(
            self, tasks: list[taskdb.Task]) -> dict[None | taskdb.TaskID, list[taskdb.Task]]:
        ret = collections.defaultdict(list)
        for t in tasks:
            ret[t.parent_id].append(t)
        return dict(ret)


_PRIO_TO_STYLE = {
    taskdb.Task.Priority.P0: 'bright_red',
    taskdb.Task.Priority.P1: 'yellow',
    taskdb.Task.Priority.P2: '',
}


def _title_with_style(task: taskdb.Task) -> Text:
    return Text.from_markup(task.title, style=_PRIO_TO_STYLE[task.priority])
