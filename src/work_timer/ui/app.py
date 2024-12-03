"""The main work_time app entry point.

Should start some kind of UI.  For now it's a Textual TUI.
"""
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Footer

from work_timer import taskdb
from work_timer import timelog
from work_timer.ui.task_list import TaskList


# TODO: Make TaskList a Screen (or wrap it in a Screen)
#       If the timer is running, a TimerStatus line/widget on the top should show the current task,
#       and the timer state.

# TODO: Keys to switch between the TaskList and Timer screens.  And task stats.

# TODO: Tasks stats:
# * Raw log of logged Periods.
# * Group by task, day, week.
# * Drop into ipython with periods dataframe?
# * Or start a Juniper notebook.


class WorkTimer(App):

    def __init__(self):
        super().__init__()
        self._task_db = taskdb.PersistentTaskDB(Path('~/tasks/'))
        self._time_log = timelog.PersistentTimeLog(Path('~/timelog.json'))

    def compose(self) -> ComposeResult:
        yield TaskList(self._task_db, self._time_log)
        yield Footer()


if __name__ == "__main__":
    app = WorkTimer()
    app.run()
