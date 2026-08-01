"""Tests for the wtctl CLI."""
import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta

from work_timer import wtctl
from work_timer import taskdb
from work_timer.taskdb import PersistentTaskDB
from work_timer.timelog import PersistentTimeLog
from work_timer.utils.fake_tasks import add_fake_tasks


class WtctlTest(unittest.TestCase):
    def setUp(self):
        # Create temp dirs for the DBs
        self.taskdb_dir = tempfile.TemporaryDirectory()
        self.timelog_file = tempfile.NamedTemporaryFile(suffix='.json')

        # Initialize Git repo for TaskDB
        repo_path = Path(self.taskdb_dir.name)

        import subprocess
        subprocess.check_call(['git', 'init', '-b', 'main', repo_path])
        with (repo_path / '.gitignore').open('w') as f:
            f.write('.lock\n')
        subprocess.check_call(['git', '-C', repo_path, 'add', '.gitignore'])

        # Initialize DBs
        self.task_db = PersistentTaskDB(repo_path, _initializing=True)
        # Manually do the first persist to simulate init_repo but on 'main' branch
        self.task_db._persist(why='TaskDB initialization')

        add_fake_tasks(self.task_db)  # Populate with the standard test tree

        # Pandas requires a valid empty JSON table structure if the file exists
        with open(self.timelog_file.name, 'w') as f:
            json.dump({"schema": {"fields": [{"name": "index", "type": "integer"}, {"name": "task_id", "type": "integer"}, {"name": "start", "type": "datetime"}, {"name": "duration", "type": "integer"}], "primaryKey": ["index"]}, "data": []}, f)

        self.time_log = PersistentTimeLog(Path(self.timelog_file.name))
        # Add a couple of fake time logs for today
        now = datetime.now()
        self.time_log.add_period(task_id=2, start=now - timedelta(hours=2), duration=timedelta(hours=1))
        self.time_log.add_period(task_id=3, start=now - timedelta(minutes=30), duration=timedelta(minutes=30))

        # We need to manually set a task to 'done' for testing strikethrough
        task = self.task_db.get(2)
        task.status = taskdb.Task.Status.DONE
        self.task_db.update(task)

    def tearDown(self):
        self.taskdb_dir.cleanup()
        self.timelog_file.close()

    def test_add_task(self):
        args = argparse.Namespace(
            taskdb=self.taskdb_dir.name,
            title="My New Task",
            parent=1,
            desc="A cool description",
            priority=taskdb.Task.Priority.P1
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            wtctl.add_task(args)

        output = stdout.getvalue()
        self.assertIn("Success: Created Task", output)
        self.assertIn("My New Task", output)

        # Verify in DB
        # Re-initialize DB object to ensure we read from disk
        db = PersistentTaskDB(Path(self.taskdb_dir.name))
        children = db.get_children(1)
        self.assertTrue(any(c.title == "My New Task" for c in children))

    def test_edit_task_metadata(self):
        args = argparse.Namespace(
            taskdb=self.taskdb_dir.name,
            task_id=2,
            status=taskdb.Task.Status.NEW,
            priority=taskdb.Task.Priority.P0,
            parent=None,
            title="Updated Title",
            desc="Updated desc",
            message=None
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            wtctl.edit_task(args)

        db = PersistentTaskDB(Path(self.taskdb_dir.name))
        task = db.get(2)
        self.assertEqual(task.title, "Updated Title")
        self.assertEqual(task.description, "Updated desc")
        self.assertEqual(task.priority, taskdb.Task.Priority.P0)
        self.assertEqual(task.status, taskdb.Task.Status.NEW)

    def test_edit_task_reparent(self):
        # Reparent task 3 (Task list) from 2 to 1
        args = argparse.Namespace(
            taskdb=self.taskdb_dir.name,
            task_id=3,
            status=None,
            priority=None,
            parent=1,
            title=None,
            desc=None,
            message=None
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            wtctl.edit_task(args)

        db = PersistentTaskDB(Path(self.taskdb_dir.name))
        task = db.get(3)
        self.assertEqual(task.parent_id, 1)
        self.assertIn(3, db.get(1).child_ids)

    def test_show_task(self):
        args = argparse.Namespace(
            taskdb=self.taskdb_dir.name,
            task_id=2
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            wtctl.show_task(args)

        output = stdout.getvalue()
        self.assertIn("# [2]", output)
        self.assertIn("**Status:** done", output)
        self.assertIn("**Parent:** [1]", output)

    def test_list_tasks(self):
        args = argparse.Namespace(
            taskdb=self.taskdb_dir.name,
            parent=-10,
            depth=10,
            status=None
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            wtctl.list_tasks(args)

        output = stdout.getvalue()
        self.assertIn("- ~~[2]", output) # Should be crossed out because it's done
        self.assertIn("- [3]", output)   # Child of 2

    def test_list_tasks_depth_limit(self):
        args = argparse.Namespace(
            taskdb=self.taskdb_dir.name,
            parent=-10,
            depth=0, # Only show root
            status=None
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            wtctl.list_tasks(args)

        output = stdout.getvalue()
        self.assertIn("- [-10] Root task", output)
        self.assertIn("- ... (has", output) # Should indicate hidden children
        self.assertNotIn("[2]", output)     # Level 1 should be hidden

    def test_timelog_today(self):
        args = argparse.Namespace(
            taskdb=self.taskdb_dir.name,
            timelog=self.timelog_file.name,
            today=True,
            weekly=False,
            since=None,
            until=None
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            wtctl.show_timelog(args)

        output = stdout.getvalue()
        self.assertIn("| 2 |", output) # Task ID 2
        self.assertIn("| 3 |", output) # Task ID 3
        self.assertIn("1h30m", output) # Total time
