"""Tests for work_timer.ui.task_editor."""
from enum import Enum

import pytest

from textual import work
from textual.app import App

from work_timer import taskdb
from work_timer.ui.task_editor import TaskEditor
from work_timer.utils import fake_tasks
from work_timer.utils.typing import not_none


class FakeApp(App):
    # pylint: disable=missing-class-docstring

    def __init__(self, task_db: taskdb.TaskDB, task: taskdb.Task) -> None:
        super().__init__()
        self._task_db = task_db
        self._current_task = task

    @work
    async def on_mount(self) -> None:
        editor = TaskEditor(self._task_db, self._current_task)
        self.editor_msg = await self.app.push_screen_wait(editor)  # pylint: disable=attribute-defined-outside-init


async def test_closes_on_esc_and_returns_none():
    app = FakeApp(fake_tasks.get_task_db(), taskdb.Task(''))
    async with app.run_test() as pilot:

        await pilot.press('escape')

        assert not isinstance(app.screen, TaskEditor)
        assert app.editor_msg is None


@pytest.mark.slow
class TestCreationMode:
    """The case when we pass a Task without an id set into the editor."""

    async def test_creates_new_task(self):
        db = fake_tasks.get_task_db()
        app = FakeApp(db, taskdb.Task(''))
        async with app.run_test() as pilot:

            await pilot.press(*list('Hello!'))
            await pilot.press('ctrl+s')

            assert isinstance(app.editor_msg, TaskEditor.Created), (
                    "Should return TaskEditor.Created when creating tasks")
            assert matches_db_version(db, app.editor_msg.new), (
                "The task in the message should match the one in the DB.")
            assert app.editor_msg.new.title == 'Hello!', "The title should be as expected"

    async def test_empty_titles_are_not_allowed(self):
        pass  # TODO


@pytest.mark.slow
class TestUpdates:

    async def test_returns_none_when_the_task_was_not_changed(self):
        db = fake_tasks.get_task_db()
        task = next(iter(db.get_all().values()))
        app = FakeApp(db, task)
        async with app.run_test() as pilot:

            await pilot.press('ctrl+s')

            assert app.editor_msg is None

    async def test_updating_a_task(self):
        db = fake_tasks.get_task_db()
        task = next(iter(db.get_all().values()))
        app = FakeApp(db, task)
        async with app.run_test() as pilot:

            await pilot.press(*list('!!!'))
            await pilot.press('ctrl+s')

            assert app.editor_msg.old == task
            assert app.editor_msg.new.title == f'{task.title}!!!'
            assert matches_db_version(db, app.editor_msg.new), (
                "The task in the message should match the one in the DB.")

    async def test_updating_task_status_doesnt_lose_str_enums(self):
        db = fake_tasks.get_task_db()
        task = next(iter(db.get_all().values()))
        app = FakeApp(db, task)
        async with app.run_test() as pilot:
            # Focus on the status Input.
            await pilot.press('tab')
            assert not_none(app.focused).id == 'status', (
                    'Expected the id=status Input to be focused')
            # Select some other status.
            await pilot.press('down')
            await pilot.press('down')
            await pilot.press('enter')
            # Save.
            await pilot.press('ctrl+s')

            assert app.editor_msg.new.status != app.editor_msg.old.status
            assert isinstance(app.editor_msg.new.status, Enum)
            assert matches_db_version(db, app.editor_msg.new), (
                "The task in the message should match the one in the DB.")


def matches_db_version(db: taskdb.TaskDB, task: taskdb.Task) -> bool:
    return db.get(task.id) == task


def main():
    db = fake_tasks.get_task_db()
    task = next(iter(db.get_all().values()))
    FakeApp(db, task).run()


if __name__ == '__main__':
    main()
