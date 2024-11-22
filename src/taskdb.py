import copy
from dataclasses import dataclass
import threading

from typing import TypeAlias


TaskID: TypeAlias = int


_UNSET_TASK_ID = -1

@dataclass
class Task:
    title: str
    id: TaskID = _UNSET_TASK_ID
    parent: TaskID | None = None


class TaskDB:

    def __init__(self):
        self._tasks = {}
        self._lock = threading.Lock()
        self._next_id = 1

    def get_all(self) -> dict[TaskID, Task]:
        return copy.deepcopy(self._tasks)

    def get(self, task_id: TaskID) -> Task:
        return copy.deepcopy(self._tasks[task_id])

    def add(self, task: Task) -> TaskID:
        task = copy.deepcopy(task)
        if task.id != _UNSET_TASK_ID:
            raise ValueError("Directly setting Task.id is not supported")
        task.id = self._get_next_id()
        self._tasks[task.id] = task
        return task.id

    def update(self, task: Task):
        if task.id == _UNSET_TASK_ID:
            raise ValueError(f"Can't update a Task with an unset id: {task}.  Add it first.")
        if task.id not in self._tasks:
            raise KeyError(f"No task with id {task.id} to update.")
        self._tasks[task.id] = copy.deepcopy(task)

    def _get_next_id(self):
        with self._lock:
            next_id = self._next_id
            self._next_id += 1
        return next_id
