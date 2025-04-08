"""The module with a DebugPanel.

The panel is docked to the bottom of the screen on all the Screens, and intended to show useful
infomation for debugging and develompent.
"""
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label


class DebugPanel(Widget):
    """Displays debug information."""
    # pylint: disable=attribute-defined-outside-init

    DEFAULT_CSS = """
    DebugPanel {
        height: 3;
        dock: bottom;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._timer = self.app._timer  # type: ignore

    def compose(self) -> ComposeResult:
        self._timer_label = Label()
        yield self._timer_label

    def on_mount(self) -> None:
        self._tickler = self.set_interval(.5, self._tick)

    def _tick(self) -> None:
        ti = self._timer.get_info()
        self._timer_label.update(f'[b]Timer[/]: {ti}')
