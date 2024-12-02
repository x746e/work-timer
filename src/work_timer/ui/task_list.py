"""A widget to showing a list (or a tree) of tasks."""
import collections

from textual import work
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from work_timer import taskdb
from work_timer.ui.task_editor import TaskEditor
from work_timer.utils.typing import not_none


class TaskList(Widget):
    """A widget to showing a list (or a tree) of tasks."""

    BINDINGS = [
        ('d', 'delete', 'Delete task'),
        ('e', 'edit', 'Edit task'),
        ('c', 'create', 'Create a new task'),  # with the cursor_node as a parent.
        # TODO: ('m', 'move', 'Move the task'),
        #       that will change the TaskList into a special mode.
        #       up/down will move the task's order between it's siblings
        #       left/right will reparent the task
        #       enter will commit the change to the TaskDB
        #       escape will cancel the change
        #       Probably that should be done in another Screen
        # TODO: ('s', 'start', 'Start the timer '),  # start the timer with the cursor_node.
        ('q', 'quit', 'Quit'),
    ]

    def __init__(self, task_db: taskdb.TaskDB):
        super().__init__()
        self._task_db = task_db

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

    def action_delete(self) -> None:
        """Action to delete the currently selected Task.

        Removes the task from the UI and deletes it from `self._task_db`.
        """
        node = self._get_selected_task_node()
        if not node:
            return

        # Handle the case if the deleted node has children.
        if node.children:
            raise NotImplementedError('Not sure what to do when deleting parent tasks. '
                                      'Delete the whole subtree?')

        # If deleting this node makes the parent "childless", then remove the
        # expand/collapse triangular marker from the parent node.
        if node.parent:
            if len(node.siblings) == 1:
                node.parent.allow_expand = False

        # Delete the Task from the TaskDB.
        task = not_none(node.data)
        self._task_db.delete(task.id)

        # And remove it from the UI.
        node.remove()

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
        changed = await self.app.push_screen_wait(TaskEditor(self._task_db, task))
        if changed:
            # TODO: Check changed.fields.
            # TODO: If reparented, move the node, then focus on it.
            node.set_label(changed.new.title)
            node.data = changed.new

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
            parent_node.add_leaf(changed.new.title, changed.new)

    def action_quit(self):
        self.app.exit()

    def check_action(
        self, action: str, parameters: tuple[object, ...]
    ) -> bool | None:
        if action in ('delete', 'edit'):
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
            node = parent_node.add(task.title, data=task)
            children = parent_to_task.get(task.id, [])
            for child_task in children:
                add_task(child_task, parent_node=node)
            if not children:
                node.allow_expand = False

        def whole_subtree_is_completed(task: taskdb.Task) -> bool:
            if task.status != taskdb.TaskStatus.COMPLETED:
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
