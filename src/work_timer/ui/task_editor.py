"""A widget for editing a Task."""
import copy

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Grid
from textual.message import Message
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button, Label, Input, Footer, Select, TextArea

from work_timer import taskdb


# TODO: On click / enter on the Parent input, show a dialog to select the new
#       parent.  ParentChooser widget.  That will require passing the TaskDB
#       all the way through.
class TaskEditorWidget(Widget):

    """A Task editing Widget."""

    class Changed(Message):

        __match_args__ = ('old', 'new')

        def __init__(self, old: None | taskdb.Task, new: taskdb.Task) -> None:
            super().__init__()
            self.old = old
            self.new = new

    class Deleted(Message):
        pass

    class Dismiss(Message):
        pass

    BINDINGS = [
        ('escape', 'dismiss'),
        # TODO: Make ctrl+enter work.
        # Something to do with weird teminal stuff.
        # See:
        # - https://invisible-island.net/xterm/ctlseqs/ctlseqs.html#h4-Functions-using-CSI-_-ordered-by-the-final-character-lparen-s-rparen:CSI-gt-Pp;Pv-m.1EB3
        # - https://invisible-island.net/xterm/manpage/xterm.html#VT100-Widget-Resources:modifyOtherKeys
        # - https://invisible-island.net/xterm/modified-keys.html
        # - https://github.com/tmux/tmux/issues/4136
        # - https://unix.stackexchange.com/questions/198519/tmux-option-xterm-keys-does-not-enable-controlarrows
        # - https://unix.stackexchange.com/questions/709619/zsh-bindkey-ctrl-enter-to-autosuggest-accept-using-kitty
        # - https://superuser.com/questions/1858041/how-do-i-specify-tmux-terminal-features-in-my-config-like-i-do-with-t
        #
        # ('ctrl+enter', 'save'),
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

    @on(Button.Pressed, '#dismiss')
    def action_dismiss(self):
        self.post_message(self.Dismiss())

    @on(Button.Pressed, '#save')
    def action_save(self):
        """Updates or creates the currently edited task."""
        updated_task = copy.deepcopy(self._edited_task)

        # TODO: Can I somehow bind Input.value to self._edited_task.title?
        title_input = self.query_one('#title', Input)
        updated_task.title = title_input.value
        status_select = self.query_one('#status', Select)
        updated_task.status = status_select.value  # type: ignore
        priority_select = self.query_one('#priority', Select)
        updated_task.priority = priority_select.value  # type: ignore
        description_text_area = self.query_one('#description', TextArea)
        updated_task.description = description_text_area.text

        # TODO: Replace all `query_one` by `query_exactly_one`.
        #       Add a linter check.

        if updated_task == self._edited_task:
            self.post_message(self.Dismiss())
            return

        if self._creating_new_task():
            task_id = self._task_db.add(updated_task)
            message = self.Changed(old=None, new=self._task_db.get(task_id))
        else:
            self._task_db.update(updated_task)
            message = self.Changed(old=self._edited_task, new=updated_task)
        self.post_message(message)

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
            yield Input(str(self._edited_task.parent_id))


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


# TODO: How do you restart `pdm run textual ...` when .py file changes?
# TODO: Show classes in the explorer.


class TaskEditor(Screen):

    """A screen containing the TaskEditorWidget.

    The main reason it exists is to make it easier to debug the layout in
    work_timer.ui.explorer, where yielding a Screen out of compose doesn't seem
    to work.
    """

    CSS_PATH = 'task_editor.tcss'

    Changed = TaskEditorWidget.Changed
    Deleted = TaskEditorWidget.Deleted

    def __init__(self, task_db: taskdb.TaskDB, task: taskdb.Task):
        super().__init__()
        self._task_db = task_db
        self._edited_task = task

    @on(TaskEditorWidget.Changed)
    @on(TaskEditorWidget.Deleted)
    def on_mutating_event(self, msg) -> None:
        self.dismiss(msg)

    @on(TaskEditorWidget.Dismiss)
    def on_noop_event(self, unused_msg) -> None:
        self.dismiss(None)

    # TODO: Decide on a standard way of ordering methods in Textual Widgets,
    # enforce with a linter rule.
    def compose(self) -> ComposeResult:
        yield TaskEditorWidget(self._task_db, self._edited_task)
        yield Footer()
