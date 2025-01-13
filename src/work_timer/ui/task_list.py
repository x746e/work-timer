"""A widget to showing a list (or a tree) of tasks -- the feature-rich version.

For basic tree rendering see ui.base_task_list module.
"""
from datetime import timedelta

from loguru import logger

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Input, Label, Tree

from work_timer.config import Config
from work_timer.taskdb import Task, TaskDB
from work_timer.taskdb.task import duplicate
from work_timer.timer import Timer
from work_timer.ui.base_task_list import BaseTaskList, TaskFilter
from work_timer.ui.task_editor import TaskEditor
from work_timer.utils.time import td
from work_timer.utils.typing import not_none


class TaskListTimerStarter(BaseTaskList):

    """Task list that can start the Timer."""

    BINDINGS = [
        ('s', 'start', 'Start the timer'),  # start the timer with the cursor_node.
        ('S', 'start_custom_period_length', 'Select period lenght before starting'),
    ]

    class TimerStarted(Message):
        pass

    def __init__(self, task_db: TaskDB, timer: Timer,
                 task_filter: TaskFilter | None = None) -> None:
        super().__init__(task_db=task_db, task_filter=task_filter)
        self._timer = timer

    @work
    async def action_start(self, period_length=None) -> None:
        """Start the Timer with the selected task.

        Pushes the TimerScreen.  After the work period ends, starts a break
        period.
        """
        task = self._get_selected_task()
        if not task:
            return
        self._timer.start(task.id, period_length=period_length)
        self.post_message(self.TimerStarted())

    @work
    async def action_start_custom_period_length(self) -> None:
        """Let the user select the period length, then start the Timer."""
        period_length = await self.app.push_screen_wait(PeriodLengthSelectDialog())
        if period_length is not None:
            self.action_start(period_length=period_length)


class TaskList(TaskListTimerStarter):
    """A widget to show and manipulate a list (or tree) of tasks."""

    BINDINGS = TaskListTimerStarter.BINDINGS + [
        ('e', 'edit', 'Edit'),
        ('d', 'mark_done', 'Mark as done'),
        ('c', 'create', 'New task'),  # with the cursor_node as a parent.
        ('-', 'dec_prio', '--priority'),
        ('+', 'inc_prio', '++priority'),
        # TODO: Make it a :duplicate command.
        # Or a pallete-only command.
        # It's not often needed, but `D` is confusing.
        # Or C-x d.
        ('D', 'duplicate', 'Make a duplicate of the task'),
        ('ctrl+up', 'reorder_up', 'Reorder up'),
        ('ctrl+down', 'reorder_down', 'Reorder down'),
        ('ctrl+left', 'reparent_up', 'Reparent up'),
        ('ctrl+right', 'reparent_down', 'Reparent down'),
    ]

    _task_db: TaskDB

    def __init__(self, task_db: TaskDB, timer: Timer) -> None:
        super().__init__(task_db=task_db, timer=timer)

    def action_mark_done(self) -> None:
        """Mark the task as DONE.

        Hide it from the view if doesn't have children.
        """
        node = not_none(self._get_selected_task_node())

        # Mark as done.
        task = self._node_to_task(node)
        task.status = Task.Status.DONE
        self._task_db.update(task)

        # And remove it from the UI.
        if not node.children:
            self._remove_node(node)

    def action_dec_prio(self) -> None:
        """Decrease the Task's priority by one."""
        node = not_none(self._get_selected_task_node())
        task = self._node_to_task(node)

        all_priorities = list(Task.Priority)
        idx = all_priorities.index(task.priority)
        if idx + 1 >= len(all_priorities):
            return

        task.priority = all_priorities[idx + 1]
        self._task_db.update(task)

        self._refresh_node(node, task)

    def action_inc_prio(self) -> None:
        """Increase the Task's priority by one."""
        node = not_none(self._get_selected_task_node())
        task = self._node_to_task(node)

        all_priorities = list(Task.Priority)
        idx = all_priorities.index(task.priority)
        if idx - 1 < 0:
            return

        task.priority = all_priorities[idx - 1]
        self._task_db.update(task)

        self._refresh_node(node, task)

    def action_reorder_up(self) -> None:
        """Move the focused task before its previous sibling."""
        node = not_none(self._get_selected_task_node())
        task = self._node_to_task(node)

        if not task.parent_id:
            return
        if not node.previous_sibling:
            return

        parent = self._task_db.get(task.parent_id)
        my_idx = parent.child_ids.index(task.id)
        prev_idx = parent.child_ids.index(not_none(node.previous_sibling.data))
        parent.child_ids.pop(my_idx)
        parent.child_ids.insert(prev_idx, task.id)
        self._task_db.update(parent)

        self._remove_node(node)
        self._add_task(task, focus=True)

    def action_reorder_down(self) -> None:
        """Move the focused task after its next sibling."""
        node = not_none(self._get_selected_task_node())
        task = self._node_to_task(node)

        if not task.parent_id:
            return
        if not node.next_sibling:
            return

        parent = self._task_db.get(task.parent_id)
        my_idx = parent.child_ids.index(task.id)
        next_idx = parent.child_ids.index(not_none(node.next_sibling.data))
        parent.child_ids.insert(next_idx + 1, task.id)
        parent.child_ids.pop(my_idx)
        self._task_db.update(parent)

        self._remove_node(node)
        self._add_task(task, focus=True)

    def action_reparent_up(self) -> None:
        """Set task's grandparent as its parent."""
        node = not_none(self._get_selected_task_node())
        task = self._node_to_task(node)
        logger.debug(f'Reparent up {task}')

        if not task.parent_id:
            return
        parent = self._task_db.get(task.parent_id)
        if not parent.parent_id:
            return
        grandparent = self._task_db.get(parent.parent_id)
        parent_idx = grandparent.child_ids.index(parent.id)
        grandparent.child_ids.insert(parent_idx + 1, task.id)
        self._task_db.update(grandparent)

        self._remove_node(node)
        self._add_task(task, focus=True)

    def action_reparent_down(self) -> None:
        """Set task's previous sibling as its parent."""
        node = not_none(self._get_selected_task_node())
        task = self._node_to_task(node)
        logger.debug(f'Reparent down {task}')

        if not node.previous_sibling:
            return

        prev_task = self._node_to_task(node.previous_sibling)
        prev_task = self._task_db.get(prev_task.id)
        prev_task.child_ids.append(task.id)
        self._task_db.update(prev_task)

        self._remove_node(node)
        self._add_task(task, focus=True)

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

        task = self._node_to_task(node)
        resp = await self.app.push_screen_wait(TaskEditor(self._task_db, task))
        match resp:
            case TaskEditor.Changed(old_task, new_task):
                if old_task.parent_id != new_task.parent_id:
                    # If reparented, remove the node, then readd it with its children.
                    self._remove_node(node)
                    self._add_task(new_task, focus=True)
                else:
                    self._refresh_node(node, new_task)
            case TaskEditor.Deleted():
                assert not node.children
                self._remove_node(node)
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
        parent_node = not_none(self._get_tree().cursor_node)
        parent_id = not_none(parent_node.data)

        new_task = Task(title='', parent_id=parent_id)
        changed = await self.app.push_screen_wait(TaskEditor(self._task_db, new_task))
        if changed:
            self._add_task(changed.new, focus=True)

    def action_duplicate(self) -> None:
        task = self._get_selected_task()
        if not task:
            return
        new_task_id = self._task_db.add(duplicate(task))
        new_task = self._task_db.get(new_task_id)
        self._add_task(new_task, focus=True)

    def check_action(
        self, action: str, parameters: tuple[object, ...]
    ) -> bool | None:
        if action in ('edit', 'mark_done', 'start', 'inc_prio', 'dec_prio'):
            if not self._get_selected_task():
                return None  # Mark the action as disabled.
        return True

    # On selection change, get Textual to call `check_action` to disable the
    # task-changing ones when no tasks are selected.
    def on_tree_node_highlighted(self, unused_event: Tree.NodeHighlighted) -> None:
        self.refresh_bindings()


class PeriodLengthSelectDialog(ModalScreen[timedelta | None]):
    """A custom period length selection dialog."""

    DEFAULT_CSS = """
    PeriodLengthSelectDialog {
        align: center middle;
    }
    #dialog {
        padding: 0 1;
        width: 60;
        height: auto;
        border: thick $background 80%;
        background: $surface;

        Label {
            padding: 0 1 1 1;
        }
    }
    """

    def key_escape(self) -> None:
        self.dismiss()

    def on_input_submitted(self, evt: Input.Submitted) -> None:
        try:
            self.dismiss(td(evt.value))
        except ValueError:
            pass

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label('Enter the work period duration:'),
            Input(id='duration'),
            id='dialog',
        )


class TaskListScreen(Screen):

    def __init__(self, config: Config, timer: Timer, name: str | None = None) -> None:
        super().__init__(name=name)
        self._config = config
        self._timer = timer

    def compose(self) -> ComposeResult:
        yield TaskList(self._config.task_db, self._timer)
        yield Footer()
