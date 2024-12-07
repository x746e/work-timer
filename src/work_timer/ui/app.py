"""The main work_time app entry point.

Should start some kind of UI.  For now it's a Textual TUI.
"""
from datetime import datetime
import os
import sys

from loguru import logger
import platformdirs

from textual.app import App, ComposeResult
from textual.logging import TextualHandler
from textual.widgets import Footer

from work_timer.config import get_config_from_args, Config
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


class WorkTimerApp(App):

    """The main Textual App."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

    def compose(self) -> ComposeResult:
        yield TaskList(self._config)
        yield Footer()


def main():
    """The app entrypoint."""
    logger.remove()
    log_dir = platformdirs.user_state_path('wtx')
    process_name = os.path.basename(sys.argv[0])
    pid = os.getpid()
    now = datetime.now().replace(microsecond=0).isoformat()
    # TODO: Log rotation.
    logger.add(log_dir / f'{process_name}-{pid}-{now}.log')
    logger.add(TextualHandler(), format="{message}")

    config = get_config_from_args()

    app = WorkTimerApp(config)
    app.run()


if __name__ == "__main__":
    main()
