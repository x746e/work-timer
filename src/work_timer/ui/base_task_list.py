"""A widget to showing a list (or a tree) of tasks -- basic tree rendering."""
from random import choice
from typing import Callable

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from work_timer import taskdb
from work_timer.taskdb import Task, TaskDBView, TaskID, ROOT_TASK_ID
from work_timer.taskdb.task import TYPE_SYMBOLS
from work_timer.utils.typing import not_none


type TaskFilter = Callable[[Task], bool]


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

    def __init__(self, task_db: TaskDBView, task_filter: TaskFilter | None = None,
                 filter_include_children=False, filter_include_parents=True) -> None:
        super().__init__()
        self._task_db = task_db

        # Filtering options.  TODO: Try inner class?
        if task_filter is None:
            def is_open(task: Task) -> bool:
                return not task.status.is_closed
            self._task_filter = is_open
        else:
            self._task_filter = task_filter
        self._filter_include_children = filter_include_children
        self._filter_include_parents = filter_include_parents

        self._task_id_to_node_id = {}
        # TODO TODO TODO: Setting it there to not work around `None`-s.  Probably shouldn't be there.
        self._tree = self._make_tree_with_tasks()

    def set_task_filter(self, task_filter: TaskFilter) -> None:
        self._task_filter = task_filter

    def compose(self) -> ComposeResult:
        # TODO TODO TODO: Why did I try to put the next line into __init__?
        self._tree = self._make_tree_with_tasks()
        yield self._tree

    def action_cursor_up(self):
        self._tree.action_cursor_up()

    def action_cursor_down(self):
        self._tree.action_cursor_down()

    async def action_refresh(self):
        self._tree = self._make_tree_with_tasks()
        await self.recompose()
        self._tree.focus()

    def _get_selected_task(self) -> Task | None:
        node = self._get_selected_task_node()
        if node is None:
            return None
        return self._node_to_task(node)

    def _get_selected_task_node(self) -> TreeNode | None:
        cursor_node = not_none(self._tree.cursor_node)
        if cursor_node.is_root:
            return None
        assert cursor_node.data is not None
        return cursor_node

    def _node_to_task(self, node: TreeNode) -> Task:
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
            if not self._whole_subtree_is_filtered_out(task):
                self._add_task(task, parent_node=tree.root, tree=tree)

        tree.root.expand()
        return tree

    def _add_task(self, task: Task, parent_node: TreeNode | None = None,
                  tree: Tree | None = None, focus=False) -> None:
        """Adds a `task`, with all its children, as a child of the `parent_node`."""

        assert task.id not in self._task_id_to_node_id, (
                f'{task} is already added to the task list')

        if not tree:
            tree = self._tree

        def get_node_by_task_id(task_id: TaskID | None) -> TreeNode:
            if task_id is None:
                return tree.root
            node_id = self._task_id_to_node_id[task_id]
            return tree.get_node_by_id(node_id)

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

        node = parent_node.add(self._title_with_style(task, parent_node, tree),
                               data=task.id, **insert_loc())  # type: ignore
        parent_node.allow_expand = True
        self._task_id_to_node_id[task.id] = node.id
        children = self._task_db.get_children(task.id)
        children_to_show = [c for c in children if not self._whole_subtree_is_filtered_out(c)]

        for child_task in children_to_show:
            self._add_task(child_task, parent_node=node, tree=tree)

        if not children_to_show:
            node.allow_expand = False

        if focus:
            # Not sure why, but it appears I need both these calls.
            self._tree.move_cursor(node)
            self._tree.select_node(node)

    def _whole_subtree_is_filtered_out(self, task: Task) -> bool:
        if self._task_filter(task):
            return False
        children = self._task_db.get_children(task.id)
        return all(self._whole_subtree_is_filtered_out(child) for child in children)

    def _refresh_node(self, node: TreeNode, task: Task) -> None:
        if self._whole_subtree_is_filtered_out(task):
            self._remove_node(node)
                    # TODO TODO TODO: Not sure what's up here.
                    #                 Am I concerned about self._tree?
        parent_node = self._tree.get_node_by_id(self._task_id_to_node_id[task.parent_id])
        node.set_label(
            self._title_with_style(
                task, parent_node=parent_node, tree=not_none(self._tree)))
        node.data = task.id
        node.refresh()

    def _title_with_style(self, task: Task, parent_node: TreeNode, tree: Tree) -> Text:
        style = Style(color=_PRIO_TO_COLOR[task.priority])
        if task.status == Task.Status.DONE:
            style = style.combine([style, Style(strike=True)])
        title = task.title
        if task.type != Task.Type.REGULAR:
            title = f'{TYPE_SYMBOLS[task.type]} {title}'
        if task.description:
            title += ' :memo:'

        title = self._add_extra_task_info(title, task, parent_node, tree)

        return Text.from_markup(title, style=style)

    def _add_extra_task_info(self, title: str, task: Task, parent_node: TreeNode,
                             tree: Tree) -> str:
        """A hook for subclasses to add to the `title`."""
        del task, parent_node, tree
        return title


_PRIO_TO_COLOR = {
    Task.Priority.P0: Color.parse('bright_red'),
    Task.Priority.P1: Color.parse('yellow'),
    Task.Priority.P2: None,
    Task.Priority.P3: Color.parse('grey50'),
}


class TaskSelectionDialog(ModalScreen[TaskID | None]):
    """A TaskList in a modal screen for selecting tasks."""

    DEFAULT_CSS = """
    TaskSelectionDialog {
        padding: 1;
    }
    """

    def __init__(self, task_db: TaskDBView) -> None:
        super().__init__()
        self._task_db = task_db

    def key_escape(self) -> None:
        self.dismiss()

    def on_tree_node_selected(self, evt: Tree.NodeSelected) -> None:
        self.dismiss(evt.node.data)

    def compose(self) -> ComposeResult:
        yield BaseTaskList(self._task_db)
