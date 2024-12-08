"""A widget for editing a Task."""
import copy
import dataclasses

from loguru import logger

from textual import on
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Grid
from textual.message import Message
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button, Label, Input, Footer, Select, TextArea

from work_timer import taskdb
from work_timer.ui.dialogs import Confirm


class TaskEditorWidget(Widget):

    """A Task editing Widget."""

    class Created(Message):

        __match_args__ = ('new',)

        def __init__(self, new: taskdb.Task) -> None:
            super().__init__()
            self.new = new

    class Changed(Message):

        __match_args__ = ('old', 'new')

        def __init__(self, old: taskdb.Task, new: taskdb.Task) -> None:
            super().__init__()
            self.old = old
            self.new = new

    class Deleted(Message):
        pass

    class Dismiss(Message):
        pass

    BINDINGS = [
        ('escape', 'dismiss'),
        ('ctrl+s', 'save', 'Save'),
        ('ctrl+r', 'delete', 'Delete'),
    ]

    def __init__(self, task_db: taskdb.TaskDB, task: taskdb.Task):
        super().__init__()
        self._task_db = task_db
        self._edited_task = task

    def _creating_new_task(self) -> bool:
        return self._edited_task.id == taskdb.UNSET_TASK_ID

    def _editing_a_parent(self) -> bool:
        return bool(self._task_db.get_children(parent_id=self._edited_task.id))

    @work
    @on(Button.Pressed, '#dismiss')
    async def action_dismiss(self):
        """Close the TaskEditor.

        If the task was changed in the editor, confirm if the user wants to
        discard the changes.
        """
        updated_task = self._get_updated_task()
        logger.debug(f'action_dismiss: updated task: {updated_task.__dict__}')
        logger.debug(f'action_dismiss: edited task: {self._edited_task.__dict__}')
        logger.debug(f'action_dismiss: updated_task == edited_task: {updated_task == self._edited_task}')
        if updated_task != self._edited_task:
            if not await self.app.push_screen_wait(
                Confirm('Are you sure you want to discard the changes to the task?')
            ):
                return
        self.post_message(self.Dismiss())

    @on(Button.Pressed, '#save')
    def action_save(self):
        """Updates or creates the currently edited task."""
        updated_task = self._get_updated_task()

        if updated_task == self._edited_task:
            self.post_message(self.Dismiss())
            return

        if self._creating_new_task():
            # TODO: Maybe have to dialogs, TaskEditor and TaskCreator?
            task_id = self._task_db.add(updated_task, parent_id=updated_task.parent_id)
            message = self.Created(new=self._task_db.get(task_id))
        else:
            # TODO: This logic doesn't belong here.
            old = dataclasses.asdict(self._edited_task)
            new = dataclasses.asdict(updated_task)
            updated_fields = []
            for k in old:
                if old[k] != new[k]:
                    updated_fields.append(k)
            if 'parent_id' in updated_fields:
                self._task_db.set_parent(updated_task.id, updated_task.parent_id)
            if set(updated_fields) - {'parent_id', '_commit'}:
                self._task_db.update(updated_task)
            message = self.Changed(old=self._edited_task, new=updated_task)
        self.post_message(message)

    def _get_updated_task(self) -> taskdb.Task:
        updated_task = copy.deepcopy(self._edited_task)

        # TODO: Can I somehow bind Input.value to self._edited_task.title?
        title_input = self.query_one('#title', Input)
        updated_task.title = title_input.value
        status_select = self.query_one('#status', Select)
        updated_task.status = status_select.value  # type: ignore
        priority_select = self.query_one('#priority', Select)
        updated_task.priority = priority_select.value  # type: ignore
        parent_id_input = self.query_one('#parent_id', Input)
        updated_task.parent_id = (
                None if not parent_id_input.value else int(parent_id_input.value))  # type: ignore
        description_text_area = self.query_one('#description', TextArea)
        updated_task.description = description_text_area.text

        return updated_task

    @on(Button.Pressed, '#delete')
    def action_delete(self):
        if self._editing_a_parent():
            raise RuntimeError('Removing subtrees is not yet supported.')
        self._task_db.delete(self._edited_task.id)
        message = self.Deleted()
        self.post_message(message)

    def check_action(
        self, action: str, parameters: tuple[object, ...]
    ) -> bool | None:
        if action == 'dismiss':
            return True
        if action == 'save':
            # TODO: Validate the title is not empty.
            return True
        if action == 'delete':
            if self._creating_new_task():
                return False
            if self._editing_a_parent():
                return None  # Mark the action as disabled.
            return True

        assert False, 'unreachable'

    def compose(self) -> ComposeResult:
        with Grid():
            if not self._creating_new_task():
                yield Label('ID:')
                yield Input(str(self._edited_task.id), disabled=True)

            yield Label('Title:')
            yield Input(self._edited_task.title, id='title')

            yield Label('Status:')
            yield Select(
                    options=[(status.name, status.value) for status in taskdb.Task.Status],
                    allow_blank=False, value=self._edited_task.status, id='status')

            yield Label('Priority:')
            yield Select(
                    options=[(priority.name, priority.value) for priority in taskdb.Task.Priority],
                    allow_blank=False, value=self._edited_task.priority, id='priority')

            yield Label('Parent ID:')
            parent_id = '' if not self._edited_task.parent_id else str(self._edited_task.parent_id)
            yield Input(parent_id, id='parent_id')

        with Horizontal(id='text-container'):
            yield Label('Description:', id='dl')
            yield TextArea(language='markdown', text=self._edited_task.description,
                           id='description')

        with Horizontal(id='buttons'):
            yield Button(label='Create' if self._creating_new_task() else 'Save',
                         variant='success' if self._creating_new_task() else 'primary',
                         id='save')
            if not self._creating_new_task():
                yield Button('Delete', variant='error', id='delete',
                             disabled=self._editing_a_parent())
            yield Button('Cancel', variant='warning', id='dismiss')


class TaskEditor(Screen):

    """A screen containing the TaskEditorWidget.

    The main reason it exists is to make it easier to debug the layout in
    work_timer.ui.explorer, where yielding a Screen out of compose doesn't seem
    to work.
    """

    CSS_PATH = 'task_editor.tcss'

    Changed = TaskEditorWidget.Changed
    Created = TaskEditorWidget.Created
    Deleted = TaskEditorWidget.Deleted

    def __init__(self, task_db: taskdb.TaskDB, task: taskdb.Task):
        super().__init__()
        self._task_db = task_db
        self._edited_task = task

    @on(TaskEditorWidget.Created)
    @on(TaskEditorWidget.Changed)
    @on(TaskEditorWidget.Deleted)
    def on_mutating_event(self, msg) -> None:
        self.dismiss(msg)

    @on(TaskEditorWidget.Dismiss)
    def on_noop_event(self, unused_msg) -> None:
        self.dismiss(None)

    def compose(self) -> ComposeResult:
        yield TaskEditorWidget(self._task_db, self._edited_task)
        yield Footer()
