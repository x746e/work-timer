"""A widget to showing a list (or a tree) of tasks."""
from datetime import date, datetime, timedelta
from typing import no_type_check

from desktop_notifier import Urgency
from gcsa.event import Event
from loguru import logger

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from work_timer import taskdb
from work_timer.config import Config
from work_timer.taskdb import TaskID, Task, ROOT_TASK_ID
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
        ('-', 'dec_prio', '--priority'),
        ('+', 'inc_prio', '++priority'),
        ('ctrl+up', 'reorder_up', 'Reorder up'),
        ('ctrl+down', 'reorder_down', 'Reorder down'),
        ('ctrl+left', 'reparent_up', 'Reparent up'),
        ('ctrl+right', 'reparent_down', 'Reparent down'),
        ('q', 'quit', 'Quit'),
        ('j', 'cursor_down'),
        ('k', 'cursor_up'),
    ]

    def __init__(self, config: Config):
        super().__init__()
        self._task_db = config.task_db
        self._time_log = config.time_log

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
                    urgency=Urgency.Critical, icon='document-open-recent')
        self._bugged_last_at = datetime.now()

    def compose(self) -> ComposeResult:
        yield self._make_tree_with_tasks()

    def _get_selected_task_node(self) -> TreeNode | None:
        cursor_node = not_none(self._get_tree().cursor_node)
        if cursor_node.is_root:
            return None
        assert cursor_node.data is not None
        return cursor_node

    def _get_tree(self) -> Tree:
        return not_none(self.query_one(Tree))

    def _get_task(self, node: TreeNode) -> Task:
        task_id = not_none(node.data)
        return self._task_db.get(task_id)

    def action_mark_done(self) -> None:
        """Mark the task as DONE.

        Hide it from the view if doesn't have children.
        """
        node = not_none(self._get_selected_task_node())

        # Mark as done.
        task = self._get_task(node)
        task.status = taskdb.Task.Status.DONE
        self._task_db.update(task)

        # And remove it from the UI.
        if not node.children:
            self._remove_node(node)

    def _remove_node(self, node: TreeNode) -> None:
        """Remove the node from the tree.

        If it's the last displayed node of the parent, remove the expand/collapse
        triangular marker from its parent node.
        """
        if node.parent and len(node.parent.children) == 1:
            node.parent.allow_expand = False
        node.remove()

    def action_dec_prio(self) -> None:
        """Decrease the Task's priority by one."""
        node = not_none(self._get_selected_task_node())
        task = self._get_task(node)

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
        task = self._get_task(node)

        all_priorities = list(taskdb.Task.Priority)
        idx = all_priorities.index(task.priority)
        if idx - 1 < 0:
            return

        task.priority = all_priorities[idx - 1]
        self._task_db.update(task)

        node.set_label(_title_with_style(task))
        node.refresh()

    def action_reorder_up(self) -> None:
        """Move the focused task before its previous sibling."""
        node = not_none(self._get_selected_task_node())
        task = self._get_task(node)

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
        task = self._get_task(node)

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
        task = self._get_task(node)
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
        task = self._get_task(node)
        logger.debug(f'Reparent down {task}')

        if not node.previous_sibling:
            return

        prev_task = self._get_task(node.previous_sibling)
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

        task = self._get_task(node)
        resp = await self.app.push_screen_wait(TaskEditor(self._task_db, task))
        match resp:
            case TaskEditor.Changed(old_task, new_task):
                if old_task.parent_id != new_task.parent_id:
                    # If reparented, remove the node, then readd it with its children.
                    self._remove_node(node)
                    self._add_task(new_task, focus=True)
                else:
                    node.set_label(_title_with_style(new_task))
                    node.data = new_task.id
                    node.refresh()
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

        new_task = taskdb.Task(title='', parent_id=parent_id)
        changed = await self.app.push_screen_wait(TaskEditor(self._task_db, new_task))
        if changed:
            self._add_task(changed.new, focus=True)

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

        task = self._get_task(node)

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
        # TODO: Move this into a work_timer.notifications.Notifier.
        #       NoopNotifier if disabled.
        #       Make Deps, self._config.deps.notifier?
        if self._config.notifier:
            await self._config.notifier.send(
                    title='Work period ended', message=task.title,
                    urgency=Urgency.Critical, icon='document-open-recent',
                    sound='complete')  # type: ignore

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
                        title='Break ended', message=str(rest_length),
                        urgency=Urgency.Critical, icon='document-open-recent',
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

        tree = Tree[taskdb.TaskID](label='/', data=ROOT_TASK_ID)
        self._task_id_to_node_id[ROOT_TASK_ID] = tree.root.id

        for task in self._task_db.get_children(parent_id=ROOT_TASK_ID):
            if not self._whole_subtree_is_completed(task):
                self._add_task(task, parent_node=tree.root)

        tree.root.expand_all()
        return tree

    def _add_task(self, task: Task, parent_node: TreeNode | None = None, focus=False) -> TreeNode:
        """Adds a `task`, with all its children, as a child of `parent_node`."""

        # TODO: Check the task isn't added yet?

        def get_node_by_task_id(task_id: TaskID | None) -> TreeNode:
            if task_id is None:
                return self._get_tree().root
            node_id = self._task_id_to_node_id[task_id]
            return self._get_tree().get_node_by_id(node_id)

        task = self._task_db.get(task.id)  # Refresh .parent_id / .child_ids
        if not parent_node:
            parent_node = get_node_by_task_id(task.parent_id)

        def insert_loc() -> dict[str, int]:
            if not task.parent_id:
                return {}
            child_ids_added_so_far = [
                    not_none(child_node.data) for child_node in parent_node.children
            ]
            parent_task = self._task_db.get(task.parent_id)
            index = parent_task.child_ids.index(task.id)
            for prev_id in reversed(parent_task.child_ids[0:index]):
                if prev_id in child_ids_added_so_far:
                    return {'after': child_ids_added_so_far.index(prev_id)}
            return {'before': 0}

        node = parent_node.add(_title_with_style(task), data=task.id, **insert_loc())  # type: ignore
        parent_node.allow_expand = True
        self._task_id_to_node_id[task.id] = node.id
        children = self._task_db.get_children(task.id)
        children_to_show = [c for c in children if not self._whole_subtree_is_completed(c)]

        for child_task in children_to_show:
            self._add_task(child_task, parent_node=node)

        if not children_to_show:
            node.allow_expand = False

        if focus:
            # Not sure why, but it appears I need both these calls.
            self._get_tree().move_cursor(node)
            self._get_tree().select_node(node)

        return node

    def _whole_subtree_is_completed(self, task: Task) -> bool:
        if task.status != Task.Status.DONE:
            return False
        children = self._task_db.get_children(task.id)
        return all(self._whole_subtree_is_completed(child) for child in children)


_PRIO_TO_COLOR = {
    taskdb.Task.Priority.P0: Color.parse('bright_red'),
    taskdb.Task.Priority.P1: Color.parse('yellow'),
    taskdb.Task.Priority.P2: None,
}


def _title_with_style(task: taskdb.Task) -> Text:
    style = Style(color=_PRIO_TO_COLOR[task.priority])
    if task.status == Task.Status.DONE:
        style = style.combine([Style(strike=True)])
    title = task.title
    if task.description:
        title += ' :memo:'
    return Text.from_markup(title, style=style)
