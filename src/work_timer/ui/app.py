"""The main work_time app entry point.

Should start some kind of UI.  For now it's a Textual TUI.
"""
from datetime import datetime
import os
import sys

import nest_asyncio
from loguru import logger
import platformdirs

from textual.app import App, ComposeResult
from textual.logging import TextualHandler
from textual.widgets import Footer

from work_timer.config import get_config_from_args, Config
from work_timer.timer import Timer
from work_timer.ui.task_list import TaskList
from work_timer.utils.scheduler import Scheduler


class WorkTimerApp(App):

    """The main Textual App."""

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._timer = Timer(self._config, scheduler=Scheduler())

    def compose(self) -> ComposeResult:
        yield TaskList(self._config, self._timer)
        yield Footer()


def main():
    """The app entrypoint."""
    nest_asyncio.apply()
    logger.remove()
    log_dir = platformdirs.user_state_path('work_timer')
    process_name = os.path.basename(sys.argv[0])
    pid = os.getpid()
    now = datetime.now().replace(microsecond=0).isoformat()
    logger.add(log_dir / f'{process_name}-{pid}-{now}.log')
    logger.add(TextualHandler(), format="{message}")

    config = get_config_from_args()

    app = WorkTimerApp(config)
    app.run()


if __name__ == "__main__":
    main()
