"""A widget for editing a Task."""
import copy

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Label, Input, Footer, Select

from work_timer import taskdb


# TODO: On click / enter on the Parent input, show a dialog to select the new
#       parent.  ParentChooser widget.  That will require passing the TaskDB
#       all the way through.
class TaskEditor(Screen):

    """A Task editing Widget."""

    class Changed(Message):

        def __init__(self, old: None | taskdb.Task, new: taskdb.Task) -> None:
            super().__init__()
            self.old = old
            self.new = new

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
    ]

    def __init__(self, task_db: taskdb.TaskDB, task: taskdb.Task):
        super().__init__()
        self._task_db = task_db
        self._edited_task = task

    def _creating_new_task(self) -> bool:
        return self._edited_task.id == taskdb.UNSET_TASK_ID

    def action_save(self):
        """Updates or creates the currently edited task."""
        updated_task = copy.deepcopy(self._edited_task)

        # TODO: Can I somehow bind Input.value to self._edited_task.title?
        title_input = self.query_one('#title', Input)
        updated_task.title = title_input.value
        status_select = self.query_one('#status', Select)
        updated_task.status = status_select.value  # type: ignore

        if updated_task == self._edited_task:
            self.dismiss(None)
            return

        if self._creating_new_task():
            task_id = self._task_db.add(updated_task)
            message = self.Changed(old=None, new=self._task_db.get(task_id))
        else:
            self._task_db.update(updated_task)
            message = self.Changed(old=self._edited_task, new=updated_task)
        self.post_message(message)
        self.dismiss(message)

    def compose(self) -> ComposeResult:
        if not self._creating_new_task():
            with Horizontal():
                yield Label('ID:')
                yield Input(str(self._edited_task.id), disabled=True)
        with Horizontal():
            yield Label('Title:')
            yield Input(self._edited_task.title, id='title')
        with Horizontal():
            yield Label('Status:')
            yield Select(
                    options=[(status.name, status.value) for status in taskdb.Task.Status],
                    allow_blank=False, id='status')
        with Horizontal():
            yield Label('Parent ID:')
            yield Input(str(self._edited_task.parent_id))
        yield Button('Create' if self._creating_new_task() else 'Save')
        yield Button('Cancel')
        yield Footer()
