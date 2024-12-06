"""Tests for work_timer.taskdb."""
import contextlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from work_timer import taskdb
from work_timer.taskdb import TaskID
from work_timer.utils import fake_tasks
from work_timer.utils.testing import TestCaseMixin

# TODO: Consider refactoring this file to use .utils.fake_tasks


class TaskTest(unittest.TestCase):

    def test_repr(self):
        new_task = taskdb.Task(title='Hello!', id=TaskID(42))
        self.assertEqual(repr(new_task), '<Task#42: Hello! | new P2>')

        new_task = taskdb.Task(title='Hello one two, ' * 30, id=TaskID(42))
        self.assertEqual(
                repr(new_task),
                '<Task#42: Hello one two, Hello one two, Hello... | new P2>')


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

    def test_adding_with_invalid_parent_id_isnt_allowed(self):
        with self.assertRaises(ValueError):
            self.db.add(taskdb.Task(title='Task', parent_id=TaskID(42)))

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

    def test_update_with_invalid_parent_id_isnt_allowed(self):
        task_id = self.db.add(taskdb.Task(title='Task A'))
        task = self.db.get(task_id)

        task.parent_id = TaskID(42)
        with self.assertRaises(ValueError):
            self.db.update(task)

    def test_delete(self):
        task = taskdb.Task(title='Original Title')
        task_id = self.db.add(task)

        self.db.delete(task_id)

        with self.assertRaises(KeyError):
            self.db.get(task_id)

    def test_deleting_parents_isnt_allowed(self):
        task_a = taskdb.Task(title='Task A')
        id_a = self.db.add(task_a)
        task_b = taskdb.Task(title='Task B', parent_id=id_a)
        self.db.add(task_b)

        with self.assertRaises(ValueError):
            self.db.delete(id_a)

    def test_get_all(self):
        task_a = taskdb.Task(title='Task A')
        task_b = taskdb.Task(title='Task B')
        id_a = self.db.add(task_a)
        id_b = self.db.add(task_b)

        tasks = self.db.get_all()

        self.assertCountEqual([id_a, id_b], tasks.keys())
        self.assertCountEqual([task_a.title, task_b.title], [t.title for t in tasks.values()])

    def test_get_children(self):
        task_a = taskdb.Task(title='Task A')
        id_a = self.db.add(task_a)
        task_b = taskdb.Task(title='Task B', parent_id=id_a)
        self.db.add(task_b)
        task_c = taskdb.Task(title='Task C', parent_id=id_a)
        id_c = self.db.add(task_c)
        task_d = taskdb.Task(title='Task D', parent_id=id_c)
        self.db.add(task_d)

        children = self.db.get_children(parent_id=id_a)

        self.assertCountEqual([task_b.title, task_c.title], [t.title for t in children])


EXPECTED_DATA = {
    'data': [
        {'id': 1, 'parent_id': None, 'priority': 'P2',
         'description': '', 'status': 'new', 'title': 'Write Work Time app'},
        {'id': 2, 'parent_id': 1, 'priority': 'P2',
         'description': '', 'status': 'new', 'title': 'Write a Textual TUI'},
        {'id': 3, 'parent_id': 2, 'priority': 'P2',
         'description': '', 'status': 'new', 'title': 'Task list'},
        {'id': 4, 'parent_id': 2, 'priority': 'P2',
         'description': '', 'status': 'new', 'title': 'Task create / edit'},
        {'id': 5, 'parent_id': 2, 'priority': 'P2',
         'description': '', 'status': 'done', 'title': 'Timer'},
        {'id': 6, 'parent_id': 1, 'priority': 'P2',
         'description': '', 'status': 'new', 'title': 'Calendar integration'}],
    'schema': {
        'fields': [
            {'extDtype': 'Int64', 'name': 'id', 'type': 'integer'},
            {'extDtype': 'string', 'name': 'title', 'type': 'any'},
            {'extDtype': 'string', 'name': 'description', 'type': 'any'},
            {'extDtype': 'Int64', 'name': 'parent_id', 'type': 'integer'},
            {'constraints': {'enum': ['done', 'new']},
             'name': 'status', 'ordered': False, 'type': 'any'},
            {'extDtype': 'string', 'name': 'priority', 'type': 'any'},],
        'pandas_version': '1.4.0',
        'primaryKey': ['id']}}


class TaskDBMixin(TestCaseMixin):

    """Helps creating PersistentTaskDBs and backing git repos."""

    def init_task_db(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # pylint: disable=consider-using-with
        repo_path = Path(temp_dir.name)
        taskdb.PersistentTaskDB.init_repo(repo_path)
        self.addCleanup(temp_dir.cleanup)
        return repo_path

    def task_db(self, repo_path: Path) -> taskdb.PersistentTaskDB:
        db = taskdb.PersistentTaskDB(repo_path=repo_path)
        self.addCleanup(db.close)
        return db


class PersistentTaskDBTest(unittest.TestCase, TaskDBMixin):

    def test_saving(self):
        d = self.init_task_db()
        db = self.task_db(repo_path=d)

        fake_tasks.add_fake_tasks(db)

        f = d / 'tasks.json'
        with f.open() as f:
            data = json.load(f)
        assert data == EXPECTED_DATA

    def test_loading(self):
        d = self.init_task_db()
        f = d / 'tasks.json'
        with f.open('w') as f:
            json.dump(EXPECTED_DATA, f)
        subprocess.check_call(f'git -C {d} add tasks.json', shell=True)
        subprocess.check_call(f'git -C {d} commit -a -m "Added test task data."', shell=True)

        db = self.task_db(d)

        assert list(fake_tasks.FAKE_TASKS) == fake_tasks.fake_tasks_from_db(db)

    def test_empty_db_persistence(self):
        d = self.init_task_db()
        db = self.task_db(d)

        task_id = db.add(taskdb.Task(title='The only task'))
        # Shouldn't fail:
        db.delete(task_id)
        db.close()

    def test_no_id_reuse(self):
        d = self.init_task_db()
        db = self.task_db(d)

        db.add(taskdb.Task(title='An initial task to not fail with an empty DB'))
        first_id = db.add(taskdb.Task(title='First task'))
        db.delete(first_id)
        db.close()
        # Now recreate the TaskDB, add again.
        db = taskdb.PersistentTaskDB(repo_path=Path(d))
        second_id = db.add(taskdb.Task(title='Another task'))

        self.assertNotEqual(first_id, second_id)
        db.close()


class PersistentTaskDBParallelTest(unittest.TestCase, TaskDBMixin):

    def test_parallel_writing(self):
        d = self.init_task_db()
        db_a = self.task_db(repo_path=d)
        db_b = self.task_db(repo_path=d)

        id_a = db_a.add(taskdb.Task(title='One task'))
        id_b = db_b.add(taskdb.Task(title='Another task'))

        assert id_a != id_b

    def test_reading_from_different_db(self):
        d = self.init_task_db()
        db_a = self.task_db(repo_path=d)
        db_b = self.task_db(repo_path=d)

        orig_task = taskdb.Task(title='One task')
        task_id = db_a.add(orig_task)
        read_from_b = db_b.get(task_id)

        assert orig_task.title == read_from_b.title


class PersistentTaskDBConflictTest(unittest.TestCase, TaskDBMixin):

    def test_updating_deleted_task(self):
        d = self.init_task_db()
        db = taskdb.PersistentTaskDB(repo_path=d)
        with contextlib.closing(db):
            task_id = db.add(taskdb.Task(title='One task'))
        del db

        db_a = self.task_db(repo_path=d)
        db_b = self.task_db(repo_path=d)

        task = db_a.get(task_id)
        task.title = 'Updated!'
        db_b.delete(task_id)
        with self.assertRaises(KeyError):
            db_a.update(task)

    def test_update_conflict(self):
        d = self.init_task_db()
        db = taskdb.PersistentTaskDB(repo_path=d)
        with contextlib.closing(db):
            task_id = db.add(taskdb.Task(title='One task'))
        del db
        db_a = self.task_db(repo_path=d)
        db_b = self.task_db(repo_path=d)

        task_a = db_a.get(task_id)
        task_a.title = 'Updated from db_a!'
        task_b = db_b.get(task_id)
        task_b.title = 'Updated from db_b!'

        db_a.update(task_a)
        with self.assertRaises(taskdb.UpdateConflict):
            db_b.update(task_b)

    def test_parallel_update_without_conflict(self):
        # TODO: (db, (first_task_id, second_task_id)) = self.init_task_db(with_tasks=[
        #           taskdb.Task(...), taskdb.Task(...)])
        d = self.init_task_db()
        db = taskdb.PersistentTaskDB(repo_path=d)
        with contextlib.closing(db):
            first_task_id = db.add(taskdb.Task(title='First task'))
            second_task_id = db.add(taskdb.Task(title='Second task'))
        del db
        db_a = self.task_db(repo_path=d)
        db_b = self.task_db(repo_path=d)

        first_task = db_a.get(first_task_id)
        first_task.title = 'Updated from db_a!'
        second_task = db_b.get(second_task_id)
        second_task.title = 'Updated from db_b!'

        db_a.update(first_task)
        # Shouldn't fail.
        db_b.update(second_task)

    def test_consecutive_updates_from_the_same_db(self):
        # If we don't change `Task._commit` on update, that update invalidates
        # the task, and fails on the second update.  See the task #143.
        d = self.init_task_db()
        db = taskdb.PersistentTaskDB(repo_path=d)
        with contextlib.closing(db):
            task_id = db.add(taskdb.Task(title='Update me!'))
        del db

        db = self.task_db(repo_path=d)
        task = db.get(task_id)

        # First update.
        task.title = 'Updated!'
        db.update(task)
        # Second update, shouldn't fail.
        task.title = 'Updated twice!'
        db.update(task)

    def test_creating_task_with_deleted_parent(self):
        d = self.init_task_db()
        db = taskdb.PersistentTaskDB(repo_path=d)
        with contextlib.closing(db):
            parent_id = db.add(taskdb.Task(title='Parent task'))
        del db
        db_a = self.task_db(repo_path=d)
        db_b = self.task_db(repo_path=d)

        db_a.delete(parent_id)
        with self.assertRaises(ValueError):
            db_b.add(taskdb.Task(title='Child task', parent_id=parent_id))

    def test_parallel_delete(self):
        d = self.init_task_db()
        db = taskdb.PersistentTaskDB(repo_path=d)
        with contextlib.closing(db):
            task_id = db.add(taskdb.Task(title='One task'))
        del db
        db_a = self.task_db(repo_path=d)
        db_b = self.task_db(repo_path=d)

        db_a.delete(task_id)
        with self.assertRaises(KeyError):
            db_b.delete(task_id)


if __name__ == '__main__':
    unittest.main()
