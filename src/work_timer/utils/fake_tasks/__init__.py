"""Provides tools and fake data to create `TastDB`s with fake `Task`s for testing."""
from dataclasses import dataclass, field

from typing import Sequence

from work_timer import taskdb
from work_timer.taskdb import TaskID


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
