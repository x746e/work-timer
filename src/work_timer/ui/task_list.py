"""A widget to showing a list (or a tree) of tasks."""
import collections
from datetime import timedelta

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from work_timer import taskdb
from work_timer.timelog import TimeLog
from work_timer.ui.timer import TimerScreen
from work_timer.ui.task_editor import TaskEditor
from work_timer.utils.typing import not_none


class TaskList(Widget):
    """A widget to showing a list (or a tree) of tasks."""

    BINDINGS = [
        ('e', 'edit', 'Edit'),
        ('m', 'mark_done', 'Mark DONE'),
        ('c', 'create', 'New task'),  # with the cursor_node as a parent.
        # TODO: ('m', 'move', 'Move the task'),
        #       that will change the TaskList into a special mode.
        #       up/down will move the task's order between it's siblings
        #       left/right will reparent the task
        #       enter will commit the change to the TaskDB
        #       escape will cancel the change
        #       Probably that should be done in another Screen
        ('s', 'start', 'Start the timer'),  # start the timer with the cursor_node.
        ('-', 'dec_prio', 'Decrease priority'),
        ('+', 'inc_prio', 'Increase priority'),
        ('q', 'quit', 'Quit'),
        ('j', 'cursor_down'),
        ('k', 'cursor_up'),
    ]

    def __init__(self, task_db: taskdb.TaskDB, time_log: TimeLog,
                 work_period_duration: timedelta, break_duration: timedelta):
        super().__init__()
        self._task_db = task_db
        self._time_log = time_log
        self._work_period_duration = work_period_duration
        self._break_duration = break_duration

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
            case TaskEditor.Changed(_, updated_task):
                # TODO: Check changed.fields.
                # TODO: If reparented, move the node, then focus on it.
                node.set_label(_title_with_style(updated_task))
                node.data = updated_task
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
            parent_node.allow_expand = True
            parent_node.add_leaf(_title_with_style(changed.new), changed.new)

    @work
    async def action_start(self) -> None:
        """Start the Timer with the selected task.

        Pushes the TimerScreen.  After the work period ends, starts a break
        period.
        """
        node = self._get_selected_task_node()
        if not node:
            return

        # TODO: All this logic doesn't really belong there.

        task = not_none(node.data)
        # TODO: duration=self.app.settings.work_period_duration.
        await self.app.push_screen_wait(TimerScreen(task, self._work_period_duration,
                                                    self._time_log))
        await self.app.notifier.send(  # type: ignore
                title='Work period ended', message=task.title,
                icon='document-open-recent', sound='complete')

        def should_rest() -> bool:
            # TODO: Do we always rest?  If the period ended on its own, not when it was
            # cancelled?
            return True

        def get_rest_length() -> timedelta:
            # TODO: Implement some logic there, like long rest every 3 hours or something.
            return self._break_duration

        if should_rest():
            await self.app.push_screen_wait(
                    TimerScreen(taskdb.BREAK, get_rest_length(), self._time_log, start=True))
            await self.app.notifier.send(  # type: ignore
                    title='Break ended', message='', icon='document-open-recent',
                    sound='dialog-error')

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
        tasks = list(self._task_db.get_all().values())
        parent_to_task = self._group_tasks_by_parent_id(tasks)

        def add_task(task: taskdb.Task, parent_node: TreeNode) -> None:
            if whole_subtree_is_completed(task):
                return
            node = parent_node.add(_title_with_style(task), data=task)
            children = parent_to_task.get(task.id, [])
            for child_task in children:
                add_task(child_task, parent_node=node)
            if not children:
                node.allow_expand = False

        def whole_subtree_is_completed(task: taskdb.Task) -> bool:
            if task.status != taskdb.Task.Status.DONE:
                return False
            children = parent_to_task.get(task.id, [])
            return all(whole_subtree_is_completed(child) for child
                       in children)

        tree = Tree[taskdb.Task]('')

        for task in parent_to_task[None]:
            add_task(task, parent_node=tree.root)

        tree.root.expand_all()
        return tree

    def _group_tasks_by_parent_id(
            self, tasks: list[taskdb.Task]) -> dict[None | taskdb.TaskID, list[taskdb.Task]]:
        ret = collections.defaultdict(list)
        for t in tasks:
            ret[t.parent_id].append(t)
        return dict(ret)


def _title_with_style(task: taskdb.Task) -> Text:
    def get_style() -> str:
        match task.priority:
            case taskdb.Task.Priority.P0:
                return 'bright_red'
            case taskdb.Task.Priority.P1:
                return 'yellow'
            case _:
                return ''
    return Text(task.title, style=get_style())
