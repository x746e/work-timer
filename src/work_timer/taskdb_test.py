"""Tests for work_timer.taskdb."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from work_timer import taskdb
from work_timer.taskdb import TaskID
from work_timer.utils import fake_tasks

# TODO: Consider refactoring this file to use .utils.fake_tasks


class TaskDBTest(unittest.TestCase):

    def setUp(self):
        self.db = taskdb.TaskDB()

    def test_add_task__then_get_it__check_the_title_stays_the_same(self):
        new_task = taskdb.Task(title='Hello!')
        new_task_id = self.db.add(new_task)

        returned_task = self.db.get(new_task_id)
        self.assertEqual(new_task.title, returned_task.title)

    def test_trying_to_set_task_id_raises(self):
        with self.assertRaises(ValueError):
            self.db.add(taskdb.Task(title='I shall raise', id=TaskID(123)))

    def test_changing_returned_task_doesnt_change_the_db(self):
        new_task = taskdb.Task(title='Original Title')
        new_task_id = self.db.add(new_task)

        returned_task = self.db.get(new_task_id)
        returned_task.title = 'New Title'

        another_returned_task = self.db.get(new_task_id)
        self.assertEqual(another_returned_task.title, 'Original Title')

    def test_changing_task_after_adding_doesnt_change_the_db(self):
        new_task = taskdb.Task(title='Original Title')
        new_task_id = self.db.add(new_task)
        new_task.title = 'Changed Title'

        returned_task = self.db.get(new_task_id)
        self.assertEqual(returned_task.title, 'Original Title')

    def test_update(self):
        new_task = taskdb.Task(title='Original Title')
        new_task_id = self.db.add(new_task)
        returned_task = self.db.get(new_task_id)
        returned_task.title = 'Changed Title'
        self.db.update(returned_task)

        updated_task = self.db.get(new_task_id)
        self.assertEqual(updated_task.title, 'Changed Title')

    def test_update_missing_task_raises(self):
        new_task = taskdb.Task(title='Original Title', id=TaskID(123))
        with self.assertRaises(KeyError):
            self.db.update(new_task)

    def test_update_without_an_id_raises(self):
        new_task = taskdb.Task(title='Original Title')
        with self.assertRaises(ValueError):
            self.db.update(new_task)

    def test_delete(self):
        task = taskdb.Task(title='Original Title')
        task_id = self.db.add(task)

        self.db.delete(task_id)

        with self.assertRaises(KeyError):
            self.db.get(task_id)

    def test_get_all(self):
        task_a = taskdb.Task(title='Task A')
        task_b = taskdb.Task(title='Task B')
        id_a = self.db.add(task_a)
        id_b = self.db.add(task_b)

        tasks = self.db.get_all()

        self.assertCountEqual([id_a, id_b], tasks.keys())
        self.assertCountEqual([task_a.title, task_b.title], [t.title for t in tasks.values()])



EXPECTED_JSON = {
    'data': [
        {'id': 1, 'parent_id': None, 'status': 'new', 'title': 'Write Work Time app'},
        {'id': 2, 'parent_id': 1, 'status': 'new', 'title': 'Write a Textual TUI'},
        {'id': 3, 'parent_id': 2, 'status': 'new', 'title': 'Task list'},
        {'id': 4, 'parent_id': 2, 'status': 'new', 'title': 'Task create / edit'},
        {'id': 5, 'parent_id': 2, 'status': 'done', 'title': 'Timer'},
        {'id': 6, 'parent_id': 1, 'status': 'new', 'title': 'Calendar integration'}],
    'schema': {
        'fields': [
            {'extDtype': 'Int64', 'name': 'id', 'type': 'integer'},
            {'extDtype': 'string', 'name': 'title', 'type': 'any'},
            {'extDtype': 'Int64', 'name': 'parent_id', 'type': 'integer'},
            {'constraints': {'enum': ['done', 'new']},
             'name': 'status', 'ordered': False, 'type': 'any'}],
        'pandas_version': '1.4.0',
        'primaryKey': ['id']}}


class PersistentTaskDBTest(unittest.TestCase):

    def test_saving(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.check_call(f'git -C {d} init', shell=True)
            db = taskdb.PersistentTaskDB(repo_path=Path(d))

            fake_tasks.add_fake_tasks(db)

            f = Path(d) / 'tasks.json'
            with f.open() as f:
                data = json.load(f)
            assert data == EXPECTED_JSON

    def test_loading(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'tasks.json'
            with f.open('w') as f:
                json.dump(EXPECTED_JSON, f)

            db = taskdb.PersistentTaskDB(Path(d))

            assert list(fake_tasks.FAKE_TASKS) == fake_tasks.fake_tasks_from_db(db)


if __name__ == '__main__':
    unittest.main()
