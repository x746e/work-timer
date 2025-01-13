"""The package defines the DB to store the timed tasks.

The main pieces:
- TaskDB: an interface and an in-memory implementation of the DB.
- Task: the class representing one task.
- PersistentTaskDB: a TaskDB you actually want to use, that can save the Tasks.
"""

from work_timer.taskdb.base import TaskDB, TaskDBView
from work_timer.taskdb.task import (Task, TaskID, BREAK_TASK_ID, BREAK, UNSET_TASK_ID, ROOT_TASK_ID,)
from work_timer.taskdb.persistence import PersistentTaskDB, UpdateConflict

__all__ = [
    'TaskDB', 'TaskDBView', 'Task', 'TaskID', 'BREAK_TASK_ID', 'BREAK',
    'UNSET_TASK_ID', 'ROOT_TASK_ID', 'PersistentTaskDB', 'UpdateConflict',
]
