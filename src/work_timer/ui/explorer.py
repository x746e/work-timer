"""An app to experiment with Textual widgets.

Potentially can grow into "Textual Dev Tools", similar to the ones found in web
browsers.
"""
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Sequence

from textual import events
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, ProgressBar, Tree, Footer
from textual.widgets import tree as tree_widget

from work_timer.config import get_test_config
from work_timer.timer import Timer
from work_timer.ui.task_editor import TaskEditorWidget
from work_timer.ui.timer_widget import TimerWidget
from work_timer.utils import fake_tasks

# Make all the linters to shut up about unused symbols.
_ = Horizontal
_ = Vertical
_ = Container
_ = ProgressBar

# Dev tools ideas:
# - Dom tree browser.
# - Style attribute changer.
# - Remote console.

# https://github.com/davep/textual-query-sandbox

# Tabs: Elements, Console, etc.

# Remote debugging:
# - ipdb/rpdb/etc.  How exactly is it done?
# - Options:
#   - Have a Textual input for the current command.
#   - Use, say, ipdb to manage the terminal, pass the terminal events to and from.

# How do I automatically install the inspector into an app?

# Two options:
# * Without the framework support, we will need to monkey-patch the app to:
#   (1) Send us all the mouse events.
#   (2) Add the widgets on the bottom.
#         - Though, better to not mess with the layout, and have the inspector in another
#           terminal.
#   (3) Visually highlight the widgets.  That may be the hardest with regular widgets.
#         - Patch into rendering machinery?
# * With the framework support highlighting the widgets will be much cleaner.

# Therefore:
# 1. Find where it renders the widgets.
#    That's probably will be done the easiest with a screenshot making test.
# 2. See if I can plug in somewhere to render the "selected" widget differently.

class Playground(Widget):
    """A playground for Textual widgets."""

    DEFAULT_CSS = """\
    Playground {
        height: 2fr;
    }
    """

    class WidgetSelected(Message):
        def __init__(self, widget: Widget) -> None:
            super().__init__()
            self.widget = widget

    def __init__(self):
        super().__init__()
        self._current_widget = None
        self._saved_outline = None

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Selects the pointed to widget."""
        if self._current_widget and self._current_widget != event.widget:
            self._deselect()

        if not event.widget:
            return

        if self._current_widget == event.widget:
            return

        self._select(event.widget)

    def _select(self, w: Widget) -> None:
        self._current_widget = w
        self._saved_outline = deepcopy(self._current_widget.styles.outline)
        self._current_widget.styles.outline = ('ascii', 'yellow')
        self.post_message(Playground.WidgetSelected(w))

    def _deselect(self) -> None:
        assert self._current_widget is not None
        self._current_widget.styles.outline = deepcopy(self._saved_outline)
        self._saved_outline = None
        self._current_widget = None

    def select(self, widget: Widget) -> None:
        for w in self.query():
            if w == widget:
                # found!
                if self._current_widget:
                    self._deselect()
                self._select(w)
                return
        assert False, f"{widget} is not found in the Playground"

    def compose(self) -> ComposeResult:
        with Vertical(id='playground'):
            yield get_timer()
            # yield get_task_editor()
            # yield from get_random_widgets()


def get_timer():
    config = get_test_config()
    task = list(config.task_db.get_all().values())[0]
    timer = Timer(config)
    timer.start(task.id)
    return TimerWidget(timer, config.task_db)


def get_task_editor():
    db = fake_tasks.get_task_db()
    task = list(db.get_all().values())[0]
    return TaskEditorWidget(db, task)


def get_random_widgets():
    """Yields a few random widgets to play with in the playground."""
    widgets = [Static(f"Static #{n}", id=f'static-{n}') for n in range(8)]
    widgets[0].styles.margin = 3
    widgets[1].styles.padding = 2
    widgets[3].styles.width = 30
    widgets[3].styles.height = 10
    pb = ProgressBar()
    pb.update(total=100, progress=42)
    # with Container(id='tcon'):
    yield ProgressBar()
    with Container(id='con-0-1-2-3'):
        yield from widgets[:4]
    with Container(id='con-4'):
        yield pb
    with Container(id='con-5-6-7'):
        yield from widgets[5:8]


class DOMTree(Widget):
    """DOMTree"""

    DEFAULT_CSS = """\
    DOMTree {
        margin-top: 1;
        width: 1fr;
        border: panel cornflowerblue 60%;
        padding: 1;
    }
    """

    _widget_to_node_id: dict[int, tree_widget.NodeID]

    @dataclass
    class _TreeNodeData:
        widget: Widget

    class WidgetSelected(Message):
        def __init__(self, widget: Widget) -> None:
            super().__init__()
            self.widget = widget

    def compose(self) -> ComposeResult:
        self.border_title = 'DOMTree'
        yield self._make_tree()

    def select(self, widget: Widget) -> None:
        tree = self.query_exactly_one(Tree)
        if id(widget) not in self._widget_to_node_id:
            return
        tree_node_id = self._widget_to_node_id[id(widget)]
        tree_node = tree.get_node_by_id(tree_node_id)
        with tree.prevent(Tree.NodeSelected, Tree.NodeHighlighted):
            tree.select_node(tree_node)

    @on(Tree.NodeSelected)
    @on(Tree.NodeHighlighted)
    def on_tree_node_selected_or_highlighted(
            self, event: Tree.NodeSelected | Tree.NodeHighlighted) -> None:
        # For our purpuses NodeHighlighted and Selected are the same.
        assert event.node.data is not None
        self.post_message(DOMTree.WidgetSelected(event.node.data.widget))

    def _make_tree(self) -> Tree:
        playground = self.app.query_exactly_one('#playground')
        tree = Tree(str(playground), data=DOMTree._TreeNodeData(playground))

        self._widget_to_node_id = {}

        def add(parent_node: tree_widget.TreeNode, child_widgets: Sequence[Widget]) -> None:
            for child in child_widgets:
                node = parent_node.add(wrepr(child),
                                       data=DOMTree._TreeNodeData(child),
                                       allow_expand=bool(len(child.children)))
                self._widget_to_node_id[id(child)] = node.id
                add(node, child.children)

        add(tree.root, playground.children)

        tree.root.expand_all()
        tree.auto_expand = False

        return tree


def wrepr(widget: Widget) -> str:
    r = f'{widget.__class__.__name__}('
    attrs = []
    if widget.id:
        attrs += [f'id={widget.id}']
    if widget.classes:
        attrs += [f'classes="{" ".join(widget.classes)}"']
    r += ', '.join(attrs)
    r += ')'
    return r


class StyleExplorer(Widget):
    """A widget to show CSS of a selected widget"""

    DEFAULT_CSS = """\
    StyleExplorer {
        margin-top: 1;
        width: 1fr;
        border: panel cornflowerblue 60%;
        padding: 1;
    }
    """

    def __init__(self):
        super().__init__()
        self._widget = None

    async def select(self, widget: Widget) -> None:
        self._widget = widget
        await self.recompose()

    def compose(self) -> ComposeResult:
        self.border_title = 'StyleExplorer'

        def only_interesting(css: str) -> str:
            return '\n'.join(
                line
                for line in css.splitlines()
                if not re.match(r'^(link-|scrollbar-|outline)', line)
            )

        with Horizontal():
            yield Static('' if not self._widget else only_interesting(self._widget.styles.css))


class ExplorerApp(App):
    """An app for exploring Textual UI."""

    CSS_PATH = 'explorer.tcss'

    BINDINGS = [
        ('r', 'redraw', 'Redraw'),
    ]

    def compose(self) -> ComposeResult:
        yield Playground()
        with Horizontal():
            yield DOMTree()
            yield StyleExplorer()
        yield Footer()

    async def on_domtree_widget_selected(self, event: DOMTree.WidgetSelected) -> None:
        self.query_exactly_one(Playground).select(event.widget)
        await self.query_exactly_one(StyleExplorer).select(event.widget)

    async def on_playground_widget_selected(self, event: Playground.WidgetSelected) -> None:
        self.query_exactly_one(DOMTree).select(event.widget)
        await self.query_exactly_one(StyleExplorer).select(event.widget)

    async def on_ready(self) -> None:
        await self.action_redraw()

    async def action_redraw(self) -> None:
        await self.query_exactly_one(DOMTree).recompose()


if __name__ == '__main__':
    ExplorerApp().run()
