"""A place to store the task to be timed by the timer."""
import copy
from dataclasses import dataclass
import threading

from typing import NewType


TaskID = NewType('TaskID', int)  # pylint: disable=invalid-name


UNSET_TASK_ID = TaskID(-1)

@dataclass
class Task:
    title: str
    id: TaskID = UNSET_TASK_ID
    parent_id: TaskID | None = None


class TaskDB:

    """A class with tasks."""

    def __init__(self) -> None:
        self._tasks = {}
        self._lock = threading.Lock()
        self._next_id = 1

    def get_all(self) -> dict[TaskID, Task]:
        return copy.deepcopy(self._tasks)

    def get(self, task_id: TaskID) -> Task:
        return copy.deepcopy(self._tasks[task_id])

    def add(self, task: Task) -> TaskID:
        task = copy.deepcopy(task)
        if task.id != UNSET_TASK_ID:
            raise ValueError("Directly setting Task.id is not supported")
        task.id = self._get_next_id()
        self._tasks[task.id] = task
        return task.id

    def update(self, task: Task) -> None:
        if task.id == UNSET_TASK_ID:
            raise ValueError(f"Can't update a Task with an unset id: {task}.  Add it first.")
        if task.id not in self._tasks:
            raise KeyError(f"No task with id {task.id} to update.")
        self._tasks[task.id] = copy.deepcopy(task)

    def delete(self, task_id: TaskID) -> None:
        del self._tasks[task_id]

    def _get_next_id(self):
        with self._lock:
            next_id = self._next_id
            self._next_id += 1
        return TaskID(next_id)
