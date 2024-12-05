"""Provides tools and fake data to create `TastDB`s with fake `Task`s for testing."""
from collections import defaultdict
from dataclasses import dataclass, field

from typing import Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.widgets import Tree

from work_timer import taskdb  # pylint: disable=wrong-import-position


Status = taskdb.Task.Status


@dataclass
class FakeTask:
    title: str
    status: Status = Status.NEW
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


def add_fake_tasks(task_db: taskdb.TaskDB, tasks: Sequence[FakeTask] = FAKE_TASKS) -> None:
    """Add some fake `tasks` to the supplied `task_db`."""

    def add_child(parent_id: taskdb.TaskID, child: FakeTask) -> None:
        t_id = task_db.add(
                taskdb.Task(child.title, status=child.status, parent_id=parent_id))
        for grandchild in child.kids:
            add_child(parent_id=t_id, child=grandchild)

    for top_level in tasks:
        t_id = task_db.add(taskdb.Task(top_level.title, status=top_level.status))
        for child in top_level.kids:
            add_child(parent_id=t_id, child=child)


def fake_tasks_from_tree(tree: 'Tree') -> list[FakeTask]:

    def node_to_task(node):
        return FakeTask(node.data.title, status=node.data.status, kids=get_kids(node))

    def get_kids(node):
        return [node_to_task(child) for child in node.children]

    return [node_to_task(task) for task in tree.root.children]


def fake_tasks_from_db(task_db: taskdb.TaskDB) -> list[FakeTask]:
    """Pulls all the tasks from `task_db` into a list of `FakeTask`s.

    Useful to compare the state of the `TaskDB` in tests.
    """
    # This duplicates (in approach) the code from
    # work_timer.ui.task_list.TaskList._make_tree_with_tasks.
    tasks_by_parent_id = defaultdict(list)
    for t in task_db.get_all().values():
        tasks_by_parent_id[t.parent_id].append(t)
    tasks_by_parent_id = dict(tasks_by_parent_id)

    def make_task(task: taskdb.Task) -> FakeTask:
        return FakeTask(
                task.title,
                status=task.status,
                kids=[make_task(t) for t in tasks_by_parent_id.get(task.id, [])])

    return [make_task(t) for t in tasks_by_parent_id.get(None, [])]
