"""The base TaskDB is defined in this module.

TaskDB is the main interface for the Task DB, plus it contains some base
implementation.  It doesn't store anything persistently, see PersistentTaskDB
class for that.
"""
import copy
import threading

from loguru import logger
import pandas as pd

from work_timer.taskdb.task import Task, TaskID, UNSET_TASK_ID


class TaskDB:

    """A class with tasks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._reload()

    def get_all(self) -> dict[TaskID, Task]:
        with self._lock:
            return copy.deepcopy(self._tasks)

    def get_data_frame(self) -> pd.DataFrame:
        """Returns (a copy of) tasks as a Pandas DataFrame."""
        tasks = self.get_all()
        if not tasks:
            return pd.DataFrame()
        df = pd.DataFrame(tasks.values())
        df = df.convert_dtypes()
        df = df.drop(columns=['_commit'])
        df = df.set_index('id')
        df.status = df.status.astype('category')
        return df

    def get(self, task_id: TaskID) -> Task:
        with self._lock:
            return copy.deepcopy(self._tasks[task_id])

    def get_children(self, parent_id: TaskID) -> list[Task]:
        with self._lock:
            return [task for task in self._tasks.values() if task.parent_id == parent_id]

    def add(self, task: Task) -> TaskID:
        """Add a task to the DB."""
        logger.debug(f'Adding {task.__dict__}')

        with self._lock:
            task = copy.deepcopy(task)
            if task.id != UNSET_TASK_ID:
                raise ValueError("Directly setting Task.id is not supported")
            if task.parent_id and task.parent_id not in self._tasks:
                raise ValueError(f"Can't add {task}, parent #{task.parent_id} doesn't exist.")
            task.id = self._get_next_id()
            assert task.id not in self._tasks
            self._tasks[task.id] = task
            self._persist(why=f'Adding {task}')
            return task.id

    def update(self, task: Task) -> None:
        """Update the `task` in the DB."""
        logger.debug(f'Updating {task.__dict__}')
        with self._lock:
            if task.id == UNSET_TASK_ID:
                raise ValueError(f"Can't update a Task with an unset id: {task}.  Add it first.")
            if task.id not in self._tasks:
                raise KeyError(f"No task with id {task.id} to update.")
            if task.parent_id and task.parent_id not in self._tasks:
                raise ValueError(f"Can't update {task}, parent #{task.parent_id} doesn't exist.")
            self._tasks[task.id] = copy.deepcopy(task)
            self._persist(why=f'Updating {task}')

    def delete(self, task_id: TaskID) -> None:
        with self._lock:
            if self.get_children(task_id):
                raise ValueError(f"Can't delete {self.get(task_id)}, "
                                 f"it has children: {self.get_children(task_id)}.")
            task = self._tasks.pop(task_id)
            self._persist(why=f'Deleting {task}')

    def _get_next_id(self):
        with self._lock:
            next_id = self._next_id
            self._next_id += 1
        return TaskID(next_id)

    def _reload(self):
        with self._lock:
            self._tasks, self._next_id = self._load()

    # Methods for overriding in subclasses.

    def _load(self) -> tuple[dict[TaskID, Task], int]:
        return {}, 1

    def _persist(self, why: str) -> None:
        pass
