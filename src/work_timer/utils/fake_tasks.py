"""Provides tools and fake data to create `TastDB`s with fake `Task`s for testing."""
from dataclasses import dataclass, field

from typing import Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.widgets import Tree

from work_timer import taskdb  # pylint: disable=wrong-import-position
from work_timer.taskdb import TaskID  # pylint: disable=wrong-import-position


Status = taskdb.Task.Status


@dataclass
class FakeTask:
    title: str
    status: Status = Status.NEW
    priority: taskdb.Task.Priority = taskdb.Task.Priority.P2
    kids: list['FakeTask'] = field(default_factory=list)


FAKE_TASKS = (
    FakeTask('Write Work Time app', kids=[
        FakeTask('Write a Textual TUI', kids=[
            FakeTask('Task list'),
            FakeTask('Task create / edit'),
            FakeTask('Timer', status=Status.DONE),
        ]),
        FakeTask('Calendar integration'),
    ]),
)


def get_task_db(fake_tasks: Sequence[FakeTask] = FAKE_TASKS) -> taskdb.TaskDB:
    task_db = taskdb.TaskDB()
    add_fake_tasks(task_db, fake_tasks)
    return task_db


def add_fake_tasks(task_db: taskdb.TaskDB, tasks: Sequence[FakeTask] = FAKE_TASKS) -> dict[str, TaskID]:
    """Add some fake `tasks` to the supplied `task_db`.

    Returns a map from the title to the task ID.
    """
    ret = {}

    def add_child(parent_id: taskdb.TaskID, child: FakeTask) -> None:
        t_id = task_db.add(
                taskdb.Task(child.title, status=child.status, parent_id=parent_id))
        ret[child.title] = t_id
        for grandchild in child.kids:
            add_child(parent_id=t_id, child=grandchild)

    for top_level in tasks:
        t_id = task_db.add(taskdb.Task(top_level.title, status=top_level.status))
        ret[top_level.title] = t_id
        for child in top_level.kids:
            add_child(parent_id=t_id, child=child)

    return ret


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
