"""A widget to showing a list (or a tree) of tasks -- basic tree rendering."""
from random import choice

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from work_timer import taskdb
from work_timer.taskdb import Task, TaskDB, TaskID, ROOT_TASK_ID
from work_timer.taskdb.task import TYPE_SYMBOLS
from work_timer.utils.typing import not_none


class BaseTaskList(Widget):
    """The widget that can render a tree of tasks.

    This was factored out of `TaskList` below to contain only base
    tree-rendering functionality.  The different logic of manipulating the
    tasks in the tree lives in subclasses.
    """

    BINDINGS = [
        ('k', 'cursor_up'),
        ('j', 'cursor_down'),
        ('R', 'refresh', 'Refresh tasks'),
    ]

    def __init__(self, task_db: TaskDB) -> None:
        super().__init__()
        self._task_db = task_db
        self._task_id_to_node_id = {}

    def compose(self) -> ComposeResult:
        yield self._make_tree_with_tasks()

    def action_cursor_up(self):
        self._get_tree().action_cursor_up()

    def action_cursor_down(self):
        self._get_tree().action_cursor_down()

    async def action_refresh(self):
        await self.recompose()
        self._get_tree().focus()

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

    def _remove_node(self, node: TreeNode) -> None:
        """Remove the node from the tree.

        If it's the last displayed node of the parent, remove the expand/collapse
        triangular marker from its parent node.
        """
        if node.parent and len(node.parent.children) == 1:
            node.parent.allow_expand = False

        def remove_id_mapping(node: TreeNode) -> None:
            task_id = not_none(node.data)
            self._task_id_to_node_id.pop(task_id)
            for child in node.children:
                remove_id_mapping(child)

        remove_id_mapping(node)
        node.remove()

    def _make_tree_with_tasks(self) -> Tree:
        """Returns a Tree widget populated with Tasks."""

        icons = [
            (' ', ' '),
            (' ', ' '),
            (' ', ' '),
            (' ', ' '),
            (' ', ' '),
        ]

        tree = Tree[taskdb.TaskID](label='/', data=ROOT_TASK_ID)
        tree.ICON_NODE, tree.ICON_NODE_EXPANDED = choice(icons)  # type: ignore
        tree.LINES['default'] = (
            "  ",
            "│ ",
            "╰─",
            "├─",
        )
        tree.guide_depth = 3

        self._task_id_to_node_id = {
            ROOT_TASK_ID: tree.root.id,
        }

        for task in self._task_db.get_children(parent_id=ROOT_TASK_ID):
            if not self._whole_subtree_is_closed(task):
                self._add_task(task, parent_node=tree.root)

        tree.root.expand()
        return tree

    def _add_task(self, task: Task, parent_node: TreeNode | None = None, focus=False) -> TreeNode:
        """Adds a `task`, with all its children, as a child of the `parent_node`."""

        assert task.id not in self._task_id_to_node_id, (
                f'{task} is already added to the task list')

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
        children_to_show = [c for c in children if not self._whole_subtree_is_closed(c)]

        for child_task in children_to_show:
            self._add_task(child_task, parent_node=node)

        if not children_to_show:
            node.allow_expand = False

        if focus:
            # Not sure why, but it appears I need both these calls.
            self._get_tree().move_cursor(node)
            self._get_tree().select_node(node)

        return node

    def _whole_subtree_is_closed(self, task: Task) -> bool:
        if not task.status.is_closed:
            return False
        children = self._task_db.get_children(task.id)
        return all(self._whole_subtree_is_closed(child) for child in children)

    def _refresh_node(self, node: TreeNode, task: Task) -> None:
        if self._whole_subtree_is_closed(task):
            self._remove_node(node)
        node.set_label(_title_with_style(task))
        node.data = task.id
        node.refresh()


_PRIO_TO_COLOR = {
    Task.Priority.P0: Color.parse('bright_red'),
    Task.Priority.P1: Color.parse('yellow'),
    Task.Priority.P2: None,
    Task.Priority.P3: Color.parse('grey50'),
}


def _title_with_style(task: taskdb.Task) -> Text:
    style = Style(color=_PRIO_TO_COLOR[task.priority])
    if task.status == Task.Status.DONE:
        style = style.combine([style, Style(strike=True)])
    title = task.title
    if task.type != Task.Type.REGULAR:
        title = f'{TYPE_SYMBOLS[task.type]} {title}'
    if task.description:
        title += ' :memo:'
    return Text.from_markup(title, style=style)


class TaskSelectionDialog(ModalScreen[TaskID | None]):
    """A TaskList in a modal screen for selecting tasks."""

    DEFAULT_CSS = """
    TaskSelectionDialog {
        padding: 1;
    }
    """

    def __init__(self, task_db: TaskDB) -> None:
        super().__init__()
        self._task_db = task_db

    def key_escape(self) -> None:
        self.dismiss()

    def on_tree_node_selected(self, evt: Tree.NodeSelected) -> None:
        self.dismiss(evt.node.data)

    def compose(self) -> ComposeResult:
        yield BaseTaskList(self._task_db)
