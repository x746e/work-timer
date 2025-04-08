"""Support code for BDD tests in task_list.feature."""
# TODO:
# - Integrate Textual snapshotting: on failures show the screencast of what went wrong.
import asyncio
from collections import namedtuple
import functools

import pytest
from pytest_bdd import scenarios, parsers, given, when, then

from textual.app import App
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from work_timer import taskdb
from work_timer.config import get_test_config
from work_timer.timer import Timer
from work_timer.ui import ui_testing
from work_timer.ui.task_list import TaskList
from work_timer.utils import fake_tasks
from work_timer.utils.fake_tasks import FakeTask
from work_timer.utils.scheduler import Scheduler
from work_timer.utils.time import td

# I'm using ui_testing.display_screen(app) quite often.
_ = ui_testing

# It's customary to inject a pytest fixture by using its name as an parameter.
# pylint: disable=redefined-outer-name


# It's OK to duplicate a bit of test code.
# pylint: disable=duplicate-code
class FakeApp(App):  # pylint: disable=missing-class-docstring

    def __init__(self, task_db: taskdb.TaskDB) -> None:
        super().__init__()
        self._task_db = task_db
        self._config = get_test_config(
                task_db=self._task_db, work_period_duration=td('25m'),
                break_duration=td('5m'), long_break_duration=td('20m'),
                long_break_after=td('3h'))
        self.timer = Timer(self._config, scheduler=Scheduler())
        self.timer_started = False

    def compose(self):
        yield TaskList(self._config.task_db, self.timer)


def async_to_sync(fn):
    """Convert async function to sync function."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))

    return wrapper


# TODO: Consider defining the tasks tree we are working on inside a given step.
# Something like:
# Given a task list like
#   | - parent task
#   |   - child task
#   |      - grandchild task
#   | - and another top level task
#   | - can be extended to support attributes
#   |   - important !p1
#   |   - everything's borked #bug
#   |   - etcetera
#   | + collapsed parent
#   |   - not visible child
@pytest.fixture
def task_db():
    initial_tasks = [
        FakeTask('task_a'),
        FakeTask('task_b'),
    ]
    return fake_tasks.get_task_db(initial_tasks)


@given('I opened a task list', target_fixture='app')
def i_opened_a_task_list(task_db):
    # TODO: Actually just use the real app, and make sure we are on the task list page.
    return FakeApp(task_db)


def _node_is_visible(node: TreeNode) -> bool:

    def all_parents_are_expanded(node: TreeNode | None) -> bool:
        if not node:
            return True
        if not node.is_expanded:
            return False
        return all_parents_are_expanded(node.parent)

    return all_parents_are_expanded(node.parent)


def _select_node(tree: Tree, node_selector: str, node_filter = _node_is_visible) -> TreeNode:
    node = None

    if node_selector == 'a leaf node':

        def find(node: TreeNode) -> TreeNode | None:
            if not node.children and node_filter(node):
                return node
            for child in node.children:
                if maybe_node := find(child):
                    return maybe_node
            return None

        node = find(tree.root)

    elif node_selector == 'a task':

        def find(node: TreeNode) -> TreeNode | None:
            if node_filter(node) and node != tree.root:
                return node
            for child in node.children:
                if maybe_node := find(child):
                    return maybe_node
            return None

        node = find(tree.root)

    else:
        raise NotImplementedError(f'Unsupported node selector: {node_selector!r}.')

    if node is None:
        raise LookupError(f"Can't find a node mathing {node_selector!r}.")
    return node



@when(parsers.re(r'I add a child task to (?P<parent_node_selector>.*)'), target_fixture='parent_node')
@async_to_sync
async def add_child_to(app, parent_node_selector):
    """Adds a new task as a child to any node matching `parent_node_selector`.

    The selected node is then available for other steps as `parent_node` pytest fixture.
    """
    async with app.run_test() as pilot:
        tree = app.query_one(Tree)

        # Find a node to add the child to.
        expectant_parent = _select_node(tree, parent_node_selector)

        # Now focus on that node.
        tree.select_node(expectant_parent)

        # Now add a child to it.
        await pilot.press('c')  # Enter the task creation dialog.
        await pilot.press(*list('new_child'))  # Enter the task title.
        await pilot.press('ctrl+s')  # Save and close the dialog.

    return expectant_parent


ChildAndParentNodes = namedtuple('ChildAndParentNodes', 'child_node parent_node')


@when(parsers.re(r'I reparent a task into (?P<node_selector>.*)'),
      target_fixture='child_and_parent_nodes')
@async_to_sync
async def reparent_a_task(app: App, node_selector: str) -> ChildAndParentNodes:
    """Change (any) task's parent to the one selected by `node_selector`.

    The selected child and parent tasks are exposed as `child_and_parent_nodes` fixture.
    If needed the tests can use `parent_node` and (not currently added) `child_node` fixtures that can
    extract nodes from the `child_and_parent_nodes` tuple.
    """
    async with app.run_test() as pilot:
        tree = app.query_one(Tree)
        # Find the nodes.
        parent_node = _select_node(tree, node_selector)
        child_node = _select_node(tree, 'a task',
                                  node_filter=lambda node: (node != parent_node and
                                                       node.parent != parent_node and
                                                       _node_is_visible(node)))
        # Now reparent the child node.  Can be done in two steps: (1) move the child task right after
        # the parent task; (2) make move into parent task's children with C-right.
        if parent_node.parent != child_node.parent:
            raise NotImplementedError(
                    'So far only reparanting of siblings is implemented. '
                    f'{parent_node=}, {parent_node.parent=} '
                    f'{child_node=}, {child_node.parent=} ')
        if parent_node.line == -1 or child_node.line == -1:
            raise ValueError('Both child and parent should be displayed.')
        tree.select_node(child_node)
        if parent_node.line > child_node.line:
            # Parent is below the child.  Move the child down.
            while parent_node.line > child_node.line:
                await pilot.press('ctrl+down')
        else:
            # Parent is above the child.  Move the child up, if needed.
            while parent_node.line < child_node.line - 1:
                await pilot.press('ctrl+up')
        assert parent_node.line == child_node.line - 1
        # Move into parent's children.
        await pilot.press('ctrl+right')

    return ChildAndParentNodes(child_node, parent_node)


@pytest.fixture
def parent_node(child_and_parent_nodes: ChildAndParentNodes) -> TreeNode:
    return child_and_parent_nodes.parent_node


@then(parsers.re(r'the parent node should get expanded'))
@async_to_sync
async def then_the_node_should_get_expanded(parent_node: TreeNode) -> None:
    assert parent_node.is_expanded


scenarios('.')
