"""The Task class plus some special "internal" tasks are defined here."""
import dataclasses
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


@dataclasses.dataclass
class Task:
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
    _commit: str = dataclasses.field(default='', compare=False)

    def __repr__(self):
        title = textwrap.shorten(self.title, width=40, placeholder='...')
        return f'<Task#{self.id}: {title} | {self.status} {self.priority}>'


BREAK_TASK_ID = TaskID(-2)

BREAK = Task('Not really a task -- a break!', id=BREAK_TASK_ID,
             priority=Task.Priority.P0)
