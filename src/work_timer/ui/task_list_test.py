"""Tests for work_timer.ui.task_list."""
from unittest import mock
import unittest

from textual.app import App
from textual.widgets import Tree

from work_timer import taskdb
from work_timer.timelog import TimeLog
from work_timer.ui import ui_testing
from work_timer.ui.task_list import TaskList
from work_timer.utils import fake_tasks
from work_timer.utils.fake_tasks import FakeTask
from work_timer.utils.time import td
from work_timer.utils.typing import not_none


Status = taskdb.Task.Status


class FakeApp(App):  # pylint: disable=missing-class-docstring

    def __init__(self, task_db: taskdb.TaskDB, time_log: TimeLog = TimeLog()) -> None:
        super().__init__()
        self._task_db = task_db
        self._time_log = time_log
        self.notifier = mock.AsyncMock()
        self.calendar = mock.Mock()

    def compose(self):
        yield TaskList(self._task_db, self._time_log, work_period_duration=td('25m'),
                       break_duration=td('5m'), long_break_duration=td('20m'),
                       long_break_after=td('3h'))


class TestTaskListDisplaysTasks(unittest.IsolatedAsyncioTestCase):

    async def test_task_rendering(self):
        tasks = [
            FakeTask('task_a', kids=[
                FakeTask('task_b', kids=[
                    FakeTask('task_c'),
                ])
            ])
        ]

        app = FakeApp(fake_tasks.get_task_db(tasks))
        async with app.run_test() as pilot:
            screenshot = ui_testing.grab_screenshot(pilot.app)

        row_a, col_a = ui_testing.find('task_a', screenshot)
        row_b, col_b = ui_testing.find('task_b', screenshot)
        row_c, col_c = ui_testing.find('task_c', screenshot)
        assert row_a < row_b < row_c and col_a < col_b < col_c, (
                'Children should be rendered lower and to the right of their parents.')

    async def test_tree_nodes(self):
        tasks = [
            FakeTask('a', kids=[
                FakeTask('b', kids=[
                    FakeTask('c'),
                ])
            ])
        ]

        app = FakeApp(fake_tasks.get_task_db(tasks))
        async with app.run_test():
            tree = app.query_one(Tree)

        self.assertEqual(tasks, fake_tasks.fake_tasks_from_tree(tree))

    async def test_completed_tasks_are_not_shown(self):
        tasks = [
            FakeTask('a', kids=[
                FakeTask('b', status=Status.DONE, kids=[
                    FakeTask('c', status=Status.DONE),
                ])
            ])
        ]

        app = FakeApp(fake_tasks.get_task_db(tasks))
        async with app.run_test():
            tree = app.query_one(Tree)

        want_displayed_tasks = [
                FakeTask('a'),
        ]
        self.assertEqual(want_displayed_tasks,
                         fake_tasks.fake_tasks_from_tree(tree))

    async def test_completed_tasks_with_active_children_are_shown(self):
        tasks = [
            FakeTask('a', kids=[
                FakeTask('b', status=Status.DONE, kids=[
                    FakeTask('c', status=Status.NEW),
                ])
            ])
        ]

        app = FakeApp(fake_tasks.get_task_db(tasks))
        async with app.run_test():
            tree = app.query_one(Tree)

        self.assertEqual(tasks,
                         fake_tasks.fake_tasks_from_tree(tree))


# TODO: Consider testing using a PersistentTaskDB as well.

class TestTaskManipulations(unittest.IsolatedAsyncioTestCase):

    # IDEA: tests prerequisites / priorities:
    # - don't run other tests if, e.g. this focus test fails.
    # - @prio(0)
    # @prereq

    async def test_app_starts_with_tree_root_focused(self):
        initial_tasks = [
            FakeTask('task_a', kids=[
                FakeTask('task_b', kids=[
                    FakeTask('task_c'),
                ])
            ])
        ]
        task_db = fake_tasks.get_task_db(initial_tasks)
        app = FakeApp(task_db)

        async with app.run_test():

            tree = app.query_one(Tree)
            self.assertTrue(tree.has_focus, 'The app should start with the Tree.')
            assert tree.cursor_node is not None, 'The app should start with the Tree root focused.'
            self.assertTrue(tree.cursor_node.is_root, 'The app should start with the Tree root focused.')

    async def test_moving_focus(self):
        initial_tasks = [
            FakeTask('task_a', kids=[
                FakeTask('task_b', kids=[
                    FakeTask('task_c'),
                ])
            ])
        ]
        task_db = fake_tasks.get_task_db(initial_tasks)
        app = FakeApp(task_db)

        async with app.run_test() as pilot:
            await pilot.press('down')
            await pilot.press('down')

            tree = app.query_one(Tree)
            node = not_none(tree.cursor_node)
            self.assertEqual(not_none(node.data).title, 'task_b')

    async def test_marking_done(self):
        initial_tasks = [
            FakeTask('task_a', kids=[
                FakeTask('task_b', kids=[
                    FakeTask('task_c'),
                    FakeTask('task_d'),
                ])
            ])
        ]
        task_db = fake_tasks.get_task_db(initial_tasks)
        app = FakeApp(task_db)

        async with app.run_test() as pilot:
            await pilot.press('down')
            await pilot.press('down')
            await pilot.press('down')
            tree = app.query_one(Tree)
            node = not_none(tree.cursor_node)
            self.assertEqual(not_none(node.data).title, 'task_c')
            node = not_none(tree.cursor_node)
            await pilot.press('m')

        want_db_tasks = [
            FakeTask('task_a', kids=[
                FakeTask('task_b', kids=[
                    FakeTask('task_c', status=Status.DONE),
                    FakeTask('task_d'),
                ])
            ])
        ]
        got_db_tasks = fake_tasks.fake_tasks_from_db(task_db)
        assert want_db_tasks == got_db_tasks
        want_ui_tasks = [
            FakeTask('task_a', kids=[
                FakeTask('task_b', kids=[
                    # task_c shouldn't be shown.
                    FakeTask('task_d'),
                ])
            ])
        ]
        got_ui_tasks = fake_tasks.fake_tasks_from_tree(tree)
        assert want_ui_tasks == got_ui_tasks

    async def test_task_edit(self):
        initial_tasks = [
            FakeTask('task_a', kids=[
                FakeTask('task_b', kids=[
                    FakeTask('task_c'),
                    FakeTask('task_d'),
                ])
            ])
        ]
        task_db = fake_tasks.get_task_db(initial_tasks)
        app = FakeApp(task_db)

        async with app.run_test() as pilot:
            await pilot.press('down')
            await pilot.press('down')
            await pilot.press('down')
            tree = app.query_one(Tree)
            self.assertEqual(not_none(not_none(tree.cursor_node).data).title, 'task_c')
            await pilot.press('e')
            # We should be in the TaskEdit now, focused on the title.
            await pilot.press(*list('!!!'))
            await pilot.press('ctrl+s')

        want_tasks = [
            FakeTask('task_a', kids=[
                FakeTask('task_b', kids=[
                    # task_c should have it's title updated.
                    FakeTask('task_c!!!'),
                    FakeTask('task_d'),
                ])
            ])
        ]
        got_db_tasks = fake_tasks.fake_tasks_from_db(task_db)
        self.assertEqual(want_tasks, got_db_tasks)
        got_ui_tasks = fake_tasks.fake_tasks_from_tree(tree)
        self.assertEqual(want_tasks, got_ui_tasks)

    async def test_task_delete(self):
        initial_tasks = [
            FakeTask('task_a', kids=[
                FakeTask('task_b', kids=[
                    FakeTask('task_c'),
                    FakeTask('task_d'),
                ])
            ])
        ]
        task_db = fake_tasks.get_task_db(initial_tasks)
        app = FakeApp(task_db)

        async with app.run_test() as pilot:
            await pilot.press('down')
            await pilot.press('down')
            await pilot.press('down')
            tree = app.query_one(Tree)
            self.assertEqual(not_none(not_none(tree.cursor_node).data).title, 'task_c')
            await pilot.press('e')
            # We should be in the TaskEdit now.
            await pilot.press('ctrl+r')

        want_tasks = [
            FakeTask('task_a', kids=[
                FakeTask('task_b', kids=[
                    # task_c should be deleted now.
                    FakeTask('task_d'),
                ])
            ])
        ]
        got_db_tasks = fake_tasks.fake_tasks_from_db(task_db)
        self.assertEqual(want_tasks, got_db_tasks)
        got_ui_tasks = fake_tasks.fake_tasks_from_tree(tree)
        self.assertEqual(want_tasks, got_ui_tasks)

    async def test_task_subtree_deletion_isnt_supported(self):
        initial_tasks = [
            FakeTask('task_a', kids=[
                FakeTask('task_b', kids=[
                    FakeTask('task_c'),
                    FakeTask('task_d'),
                ])
            ])
        ]
        task_db = fake_tasks.get_task_db(initial_tasks)
        app = FakeApp(task_db)

        async with app.run_test() as pilot:
            await pilot.press('down')
            await pilot.press('down')
            tree = app.query_one(Tree)
            self.assertEqual(not_none(not_none(tree.cursor_node).data).title, 'task_b')
            await pilot.press('e')
            # We should be in the TaskEdit now.
            await pilot.press('ctrl+r')

        # Nothing should change
        got_db_tasks = fake_tasks.fake_tasks_from_db(task_db)
        self.assertEqual(initial_tasks, got_db_tasks)
        got_ui_tasks = fake_tasks.fake_tasks_from_tree(tree)
        self.assertEqual(initial_tasks, got_ui_tasks)

    async def test_increasing_priority(self):
        # Also tests two changes to the same object, that was failing with
        # TaskDB.
        initial_tasks = [
            FakeTask('task_a'),
            FakeTask('task_b'),
        ]
        task_db = fake_tasks.get_task_db(initial_tasks)
        app = FakeApp(task_db)

        async with app.run_test() as pilot:
            await pilot.press('down')
            await pilot.press('down')
            tree = app.query_one(Tree)
            self.assertEqual(not_none(not_none(tree.cursor_node).data).title, 'task_b')
            await pilot.press('+')
            await pilot.press('+')

        want_tasks = [
            FakeTask('task_a'),
            FakeTask('task_b', priority=taskdb.Task.Priority.P0),
        ]
        got_ui_tasks = fake_tasks.fake_tasks_from_tree(tree)
        self.assertEqual(want_tasks, got_ui_tasks)
        got_db_tasks = fake_tasks.fake_tasks_from_db(task_db)
        self.assertEqual(want_tasks, got_db_tasks)


class TestTimer(unittest.IsolatedAsyncioTestCase):

    async def test_it_logs(self):
        # Make a TaskDB, as usual.
        tasks = [FakeTask('task_a')]
        task_db = fake_tasks.get_task_db(tasks)
        # And a TimeLog instance.
        time_log = TimeLog()
        app = FakeApp(task_db, time_log)

        async with app.run_test() as pilot:
            # Navigate to the task.
            await pilot.press('down')
            tree = app.query_one(Tree)
            self.assertEqual(not_none(not_none(tree.cursor_node).data).title, 'task_a')
            # Go to the Timer view.
            await pilot.press('s')
            # Start the period.
            await pilot.press('space')
            # Stop the period.
            await pilot.press('S')

        # Check there's a entry in the TimeLog.
        self.assertEqual(len(time_log.get_periods()), 1)


# def prereq(meth):
#     # TODO:
#     # if this method fails, get the class out of it (how?), mark all other methods as failed as well.
#     # I may also need to hack TestLoader.sortTestMethodsUsing to get the prereq method to run first.
#     # Or just replace it's name with `test_0_prereq` or something.
#     # Or it can check it's ordering, and warn the user if it won't be run
#     # first, and instruct to rename it to run first.
#     pass


def run_test_app():
    app = FakeApp(fake_tasks.get_task_db())
    app.run()


if __name__ == '__main__':
    run_test_app()
    # unittest.main()
