"""The Task class plus some special "internal" tasks are defined here."""
from dataclasses import dataclass, field
import enum
import textwrap
from typing import NewType


TaskID = NewType('TaskID', int)  # pylint: disable=invalid-name


# TODO: Mark as internal API.
UNSET_TASK_ID = TaskID(-1)


class LowerCaseStrEnum(enum.StrEnum):

    @staticmethod
    def _generate_next_value_(name, start, count, last_values) -> str:
        del start, count, last_values
        return name


@dataclass
class Task:  # pylint: disable=too-many-instance-attributes
    """A single task."""

    class Status(enum.StrEnum):
        NEW = enum.auto()
        DONE = enum.auto()

    class Priority(LowerCaseStrEnum):
        P0 = enum.auto()
        P1 = enum.auto()
        P2 = enum.auto()

    title: str
    id: TaskID = UNSET_TASK_ID
    description: str = ''
    parent_id: TaskID | None = None
    status: Status = Status.NEW
    priority: Priority = Priority.P2
    child_ids: list[TaskID] = field(default_factory=list, compare=False)
    _commit: str = field(default='', compare=False)

    def __repr__(self):
        title = textwrap.shorten(self.title, width=40, placeholder='...')
        return f'<Task#{self.id}: {title} | {self.status} {self.priority}>'


BREAK_TASK_ID = TaskID(-2)

BREAK = Task('Not really a task -- a break!', id=BREAK_TASK_ID,
             priority=Task.Priority.P0)
