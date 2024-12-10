"""Tests for work_timer.taskdb.persistence."""
import contextlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from work_timer import taskdb
from work_timer.taskdb import Task
from work_timer.utils import fake_tasks
from work_timer.utils.testing import UnittestTestCaseMixin


EXPECTED_DATA = {
    'data': [
        {
            'child_ids': [1],
            'description': '',
            'id': -10,
            'priority': 'P2',
            'status': 'new',
            'title': 'Root task',
        },
        {
            'child_ids': [
                2,
                6,
            ],
            'description': '',
            'id': 1,
            'priority': 'P2',
            'status': 'new',
            'title': 'Write Work Time app',
        },
        {
            'child_ids': [
                3,
                4,
                5,
            ],
            'description': '',
            'id': 2,
            'priority': 'P2',
            'status': 'new',
            'title': 'Write a Textual TUI',
        },
        {
            'child_ids': [],
            'description': '',
            'id': 3,
            'priority': 'P2',
            'status': 'new',
            'title': 'Task list',
        },
        {
            'child_ids': [],
            'description': '',
            'id': 4,
            'priority': 'P2',
            'status': 'new',
            'title': 'Task create / edit',
        },
        {
            'child_ids': [],
            'description': '',
            'id': 5,
            'priority': 'P2',
            'status': 'done',
            'title': 'Timer',
        },
        {
            'child_ids': [],
            'description': '',
            'id': 6,
            'priority': 'P2',
            'status': 'new',
            'title': 'Calendar integration',
        },
    ],
    'schema': {
        'fields': [
            {
                'extDtype': 'Int64',
                'name': 'id',
                'type': 'integer',
            },
            {
                'extDtype': 'string',
                'name': 'title',
                'type': 'any',
            },
            {
                'extDtype': 'string',
                'name': 'description',
                'type': 'any',
            },
            {
                'constraints': {
                    'enum': [
                        'new',
                        'done',
                    ],
                },
                'name': 'status',
                'ordered': False,
                'type': 'any',
            },
            {
                'constraints': {
                    'enum': [
                        'P0',
                        'P1',
                        'P2',
                    ],
                },
                'name': 'priority',
                'ordered': True,
                'type': 'any',
            },
            {
                'name': 'child_ids',
                'type': 'string',
            },
        ],
        'pandas_version': '1.4.0',
        'primaryKey': [
            'id',
        ],
    },
}


class TaskDBMixin(UnittestTestCaseMixin):

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


class SimplePersistentTaskDBTest(unittest.TestCase, TaskDBMixin):
    # Added while debugging PersistentTaskDBTest, which was adding
    # quite a few tasks and failing with a weird conflict.

    def test_saving_one_task(self):
        d = self.init_task_db()
        db = self.task_db(repo_path=d)

        db.add(Task('Task A'))

    def test_saving_two_tasks(self):
        d = self.init_task_db()
        db = self.task_db(repo_path=d)

        db.add(Task('Task A'))
        db.add(Task('Task B'))

    def test_adding_a_child(self):
        d = self.init_task_db()
        db = self.task_db(repo_path=d)

        id_a = db.add(Task('Task A'))
        db.add(Task('Task B', parent_id=id_a))

    def test_adding_two_children(self):
        d = self.init_task_db()
        db = self.task_db(repo_path=d)

        id_a = db.add(Task('Task A'))
        db.add(Task('Task B', parent_id=id_a))
        # This need to update Task A, which was already updated when Task B was added.
        db.add(Task('Task C', parent_id=id_a))


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

    def test_child_ids_are_set_after_loading(self):
        d = self.init_task_db()

        with contextlib.closing(self.task_db(repo_path=d)) as db:
            id_a = db.add(Task('Task A'))
            id_b = db.add(Task('Task B', parent_id=id_a))
            id_c = db.add(Task('Task C', parent_id=id_a))
        del db

        db = self.task_db(repo_path=d)
        task_a = db.get(id_a)
        assert set(task_a.child_ids) == {id_b, id_c}

    def test_parent_id_is_set_after_loading(self):
        d = self.init_task_db()

        with contextlib.closing(self.task_db(repo_path=d)) as db:
            id_a = db.add(Task('Task A'))
            id_b = db.add(Task('Task B', parent_id=id_a))
            id_c = db.add(Task('Task C', parent_id=id_a))
        del db

        db = self.task_db(repo_path=d)
        task_b = db.get(id_b)
        assert task_b.parent_id == id_a
        task_c = db.get(id_c)
        assert task_c.parent_id == id_a


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
