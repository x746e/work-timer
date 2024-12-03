"""A place to store the task to be timed by the timer."""
import copy
from dataclasses import dataclass
import enum
from pathlib import Path
import subprocess
import threading
from typing import NewType

import pandas as pd


TaskID = NewType('TaskID', int)  # pylint: disable=invalid-name


UNSET_TASK_ID = TaskID(-1)


@dataclass
class Task:

    class Status(enum.StrEnum):
        NEW = enum.auto()
        DONE = enum.auto()

    title: str
    id: TaskID = UNSET_TASK_ID
    parent_id: TaskID | None = None
    status: Status = Status.NEW


class TaskDB:

    """A class with tasks."""

    def __init__(self) -> None:
        self._tasks = self._load_tasks()
        self._lock = threading.Lock()
        if self._tasks:
            self._next_id = max(t.id for t in self._tasks.values()) + 1
        else:
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
        with self._lock:
            self._persist(why=f'Adding {task}')
        return task.id

    def update(self, task: Task) -> None:
        if task.id == UNSET_TASK_ID:
            raise ValueError(f"Can't update a Task with an unset id: {task}.  Add it first.")
        if task.id not in self._tasks:
            raise KeyError(f"No task with id {task.id} to update.")
        self._tasks[task.id] = copy.deepcopy(task)
        with self._lock:
            self._persist(why=f'Updating {task}')

    def delete(self, task_id: TaskID) -> None:
        task = self._tasks.pop(task_id)
        with self._lock:
            self._persist(why=f'Deleting {task}')

    def _get_next_id(self):
        with self._lock:
            next_id = self._next_id
            self._next_id += 1
        return TaskID(next_id)

    # Methods for overriding in subclasses.

    def _load_tasks(self) -> dict[TaskID, Task]:
        return {}

    def _persist(self, why: str) -> None:
        pass


class PersistentTaskDB(TaskDB):
    """A TaskDB that stores its tasks in a persistent storage.

    The current implementation uses JSON, through Pandas.
    """

    def __init__(self, repo_path: Path):
        self._repo_path = repo_path.expanduser()
        self._path = self._repo_path / 'tasks.json'
        super().__init__()

    def get_data_frame(self) -> pd.DataFrame:
        """Returns (a copy of) tasks as a Pandas DataFrame."""
        tasks = self.get_all()
        df = pd.DataFrame(tasks.values()).convert_dtypes().set_index('id')
        df.status = df.status.astype('category')
        return df

    def _load_tasks(self) -> dict[TaskID, Task]:
        if not self._path.exists():
            return {}
        df = pd.read_json(self._path, orient='table')
        return self._from_df(df)

    def _persist(self, why: str) -> None:
        df = self.get_data_frame()
        df.to_json(self._path, orient='table', indent=2)
        subprocess.check_call(['git', '-C', self._repo_path, 'add', self._path])
        subprocess.check_call(['git', '-C', self._repo_path, 'commit', '-m', why])

    def _from_df(self, df: pd.DataFrame) -> dict[TaskID, Task]:
        return {d['id']: Task(**d) for d in df.reset_index().to_dict(orient='records')}
