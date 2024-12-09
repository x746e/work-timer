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

    # TODO: Add a root task, don't allow parent_id to be None?
    def get_children(self, parent_id: TaskID | None) -> list[Task]:
        with self._lock:
            if parent_id is None:
                return [t for t in self._tasks.values() if t.parent_id is None]
            parent = self.get(parent_id)
            return [self.get(child_id) for child_id in parent.child_ids]

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
            # Add itself to the parent's .child_ids
            if task.parent_id:
                parent = self.get(task.parent_id)
                parent.child_ids.append(task.id)
                self.update(parent, _update_relationships=False)
            self._persist(why=f'Adding {task}')
            return task.id

    def update(self, task: Task, _update_relationships=True) -> None:
        """Update the `task` in the DB."""
        logger.debug(f'Updating {task.__dict__}, {_update_relationships=}')
        with self._lock:
            if task.id == UNSET_TASK_ID:
                raise ValueError(f"Can't update a Task with an unset id: {task}.  Add it first.")
            if task.id not in self._tasks:
                raise KeyError(f"No task with id {task.id} to update.")
            if task.parent_id and task.parent_id not in self._tasks:
                raise ValueError(f"Can't update {task}, parent #{task.parent_id} doesn't exist.")
            if task.child_ids and not all(cid in self._tasks for cid in task.child_ids):
                missing_ids = [cid for cid in task.child_ids if cid not in self._tasks]
                raise ValueError(f"Can't update {task}, these child IDs doesn't exist: {missing_ids}")
            if _update_relationships:
                self._update_relationships(task)

            self._tasks[task.id] = copy.deepcopy(task)
            if _update_relationships:
                self._persist(why=f'Updating {task}')
            # TODO: Can this run `self._conflict_check()` which subclasses can
            #       implement instead of overriding .update()?

    def _update_relationships(self, task: Task) -> None:
        orig = self.get(task.id)

        # On .child_ids update:
        if orig.child_ids != task.child_ids:
            # For new children:
            added_ids = set(task.child_ids) - set(orig.child_ids)
            for new_child_id in added_ids:
                new_child = self.get(new_child_id)
                # - Remove the child ID from its parent's .child_ids, if not None.
                if new_child.parent_id:
                    old_parent = self.get(new_child.parent_id)
                    old_parent.child_ids.remove(new_child_id)
                    self.update(old_parent, _update_relationships=False)
                # - Set child.parent_id to self.
                new_child.parent_id = task.id
                self.update(new_child, _update_relationships=False)
            # For removed children:
            removed_ids = set(orig.child_ids) - set(task.child_ids)
            for removed_child_id in removed_ids:
                removed_child = self.get(removed_child_id)
                # - Set their .parent_id to None
                removed_child.parent_id = None
                # TODO: Maybe update ROOT task's child_ids.
                self.update(removed_child, _update_relationships=False)

        # On .parent_id update:
        if orig.parent_id != task.parent_id:
            # - Remove itself from previous parent's .child_ids
            if orig.parent_id:
                old_parent = self.get(orig.parent_id)
                old_parent.child_ids.remove(task.id)
                self.update(old_parent, _update_relationships=False)
            # - Add itself to the new parent's .child_ids
            if task.parent_id:
                new_parent = self.get(task.parent_id)
                new_parent.child_ids.append(task.id)
                self.update(new_parent, _update_relationships=False)

    def delete(self, task_id: TaskID) -> None:
        """Deletes the task."""
        with self._lock:
            if self.get_children(task_id):
                raise ValueError(f"Can't delete {self.get(task_id)}, "
                                 f"it has children: {self.get_children(task_id)}.")
            task = self._tasks.pop(task_id)
            # Remove itself from the parent's .child_ids
            if task.parent_id:
                old_parent = self.get(task.parent_id)
                old_parent.child_ids.remove(task.id)
                self.update(old_parent, _update_relationships=False)
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
