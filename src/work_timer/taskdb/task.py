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


ROOT_TASK_ID = TaskID(-10)


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
        P3 = enum.auto()

    class Type(LowerCaseStrEnum):  # pylint: disable=missing-class-docstring
        REGULAR = enum.auto()
        BUG = enum.auto()
        PROJECT = enum.auto()
        MOONSHOT = enum.auto()
        EPIC = enum.auto()
        WORKFLOW = enum.auto()
        REFACTORING = enum.auto()
        IMPROVEMENT = enum.auto()
        IDEA = enum.auto()
        FEATURE = enum.auto()

    title: str
    id: TaskID = UNSET_TASK_ID
    description: str = ''
    parent_id: TaskID = ROOT_TASK_ID
    status: Status = Status.NEW
    priority: Priority = Priority.P2
    type: Type = Type.REGULAR
    child_ids: list[TaskID] = field(default_factory=list)
    _commit: str | None = field(default=None, compare=False)

    def __repr__(self):
        title = textwrap.shorten(self.title, width=40, placeholder='...')
        if self._commit:
            commit = self._commit[:4]
        else:
            commit = 'uncommitted'
        return (f'<Task#{self.id}: {title} | {self.status} {self.priority} '
                f'{self.child_ids} @{commit}>')


TYPE_SYMBOLS = {
    Task.Type.BUG: '🐞',
    Task.Type.PROJECT: '🚀',
    Task.Type.MOONSHOT: '🌕🚀',
    Task.Type.EPIC: '🧭',
    Task.Type.WORKFLOW: '⚙️',
    Task.Type.REFACTORING: '🛠️',
    Task.Type.IMPROVEMENT: '✨',
    Task.Type.IDEA: '💡',
    Task.Type.FEATURE: '🎁',
}


_ROOT_TASK = Task('Root task', id=ROOT_TASK_ID)


BREAK_TASK_ID = TaskID(-2)
BREAK = Task('Not really a task -- a break!', id=BREAK_TASK_ID,
             priority=Task.Priority.P0)

INTERNAL_TASKS = {
    ROOT_TASK_ID: _ROOT_TASK,
    BREAK_TASK_ID: BREAK,
}
