"""Helper methods for testing Textual UIs."""
import io
from collections import namedtuple

from rich.console import Console
from textual.app import App


def grab_screenshot(app: App) -> str:
    """Returns a string with a snapshot of the TUI."""
    console = Console(
        file=io.StringIO(),
        record=True,
    )
    screen_render = app.screen._compositor.render_update(full=True)  # pylint: disable=protected-access
    console.print(screen_render)
    return console.export_text()


def display_screen(app: App) -> None:
    """Outputs the current screen of the `app` ot stdout."""
    console = Console()
    screen_render = app.screen._compositor.render_update(full=True)  # pylint: disable=protected-access
    console.print(screen_render)


FoundAt = namedtuple('Where', 'row col')

def find(s: str, screenshot: str) -> FoundAt:
    """Returns (row, col) of `s` inside of `screenshot`."""
    for nrow, line in enumerate(screenshot.splitlines()):
        if s in line:
            return FoundAt(row=nrow, col=line.find(s))
    raise LookupError
