"""Tools to assert the state of the TaskDB or the UI in the tests."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.widgets import Tree

# pylint gets thown off by the TYPE_CHECKING block above.
# pylint: disable=wrong-import-position

from work_timer import taskdb
from work_timer.utils.fake_tasks import FakeTask


def fake_tasks_from_tree(tree: 'Tree') -> list[FakeTask]:
    """Extracts FakeTasks out of a Tree widget."""

    from work_timer.ui.task_list import _PRIO_TO_COLOR  # pylint: disable=import-outside-toplevel

    _COLOR_TO_PRIO = dict(map(reversed, _PRIO_TO_COLOR.items()))  # type: ignore  # pylint: disable=invalid-name

    def node_to_task(node):
        status = (taskdb.Task.Status.DONE if node.label.style.strike else
                  taskdb.Task.Status.NEW)

        return FakeTask(
                node.label.plain,
                status=status,
                priority=_COLOR_TO_PRIO[node.label.style.color],  # type: ignore
                kids=get_kids(node))

    def get_kids(node):
        return [node_to_task(child) for child in node.children]

    return [node_to_task(task) for task in tree.root.children]


def fake_tasks_from_db(task_db: taskdb.TaskDB) -> list[FakeTask]:
    """Pulls all the tasks from `task_db` into a list of `FakeTask`s.

    Useful to compare the state of the `TaskDB` in tests.
    """
    def make_task(task: taskdb.Task) -> FakeTask:
        return FakeTask(
                task.title,
                status=task.status,
                priority=task.priority,
                kids=[make_task(t) for t in task_db.get_children(task.id)])

    return [make_task(t) for t in task_db.get_children(taskdb.ROOT_TASK_ID)]
