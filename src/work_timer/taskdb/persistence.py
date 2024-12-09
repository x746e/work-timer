"""A module defining a TaskDB implementation that can store its state."""
import dataclasses
import io
import json
from pathlib import Path
import subprocess

from filelock import FileLock
from loguru import logger
import pandas as pd
from watchdog.observers import Observer
from watchdog.events import FileSystemEvent, FileSystemEventHandler

from work_timer.taskdb.base import TaskDB
from work_timer.taskdb.task import Task, TaskID


class PersistentTaskDB(TaskDB):
    """A TaskDB that stores its tasks in a persistent storage.

    The current implementation uses JSON, through Pandas, in a git repo.
    Maybe an unconventional choice for a database, but has these useful
    properties (especially handy during the development):
    - The JSON format used makes it easy to examine and modify it by hand.
    - Storing it in git gives me peace of mind that I want accidentally
      lose data.

    On each mutation (add/remove/update) is serializes the whole dataset
    into a JSON, writes it to a file, and commits that change into git.
    Modern computers are fast, and with O(~100) tasks that seem to work
    just fine so far.

    There's support for having a few DB instances running concurrently.
    They are synchronized with a file lock, and they are using filesystem
    change notification to update themselves when another instance writes a
    change to disk.
    """

    def __init__(self, repo_path: Path):
        self._repo_path = repo_path.expanduser()
        self._tasks_path = self._repo_path / 'tasks.json'
        self._metadata_path = self._repo_path / 'metadata.json'
        self._commit = None
        self._file_lock = FileLock(self._repo_path / '.lock', thread_local=False)

        super().__init__()

        self._fs_observer = Observer()
        self._fs_observer.schedule(_FSEventHandler(self), str(self._repo_path))
        self._fs_observer.start()

    @staticmethod
    def init_repo(repo_path: Path):
        """Initialize a new PersistentTaskDB-backing git repo."""
        metadata_path = repo_path / 'metadata.json'
        assert not metadata_path.exists()
        subprocess.check_output(f'git -C {repo_path} init', shell=True)
        with metadata_path.open('w') as f:
            json.dump({'next_id': 1}, f)
        with (repo_path / '.gitignore').open('w') as f:
            f.write('.lock\n')
        subprocess.check_output(
                f'git -C {repo_path} add metadata.json .gitignore', shell=True)
        subprocess.check_output(
                f'git -C {repo_path} commit -m "TaskDB initialization"', shell=True)

    # Methods for concurrent update support.

    def close(self):
        self._stop_fs_observer()

    def _stop_fs_observer(self):
        self._fs_observer.stop()
        self._fs_observer.join()
        assert not self._fs_observer.is_alive()

    def _on_modified(self, event: FileSystemEvent) -> None:
        if event.src_path != str(self._tasks_path):
            return
        if event.event_type != 'modified':
            return
        if not self._repo_path.exists():
            return
        with self._lock:
            with self._file_lock:
                repo_head = self._get_repo_head()
                if not repo_head:
                    return
                if repo_head != self._commit:
                    logger.debug(f'The repo ({self._repo_path}) was modified, reloading. '
                                 f'On disk: {repo_head}, self._commit: {self._commit}.')
                    self._reload()

    def update(self, task: Task) -> None:
        """Detect possible editing conflicts when updating the `task`.

        Raises an `UpdateConflict` exception in that case.
        """
        # pylint: disable=protected-access

        def asjson(task: Task) -> str:
            return json.dumps(dataclasses.asdict(task))

        with self._lock:
            with self._file_lock:
                repo_head = self._get_repo_head()
                logger.info(f'Updating {task}. {task._commit=}, {self._commit=}, {repo_head=}')
                if repo_head != self._commit:
                    logger.debug(f'While updating {task}: the repo ({self._repo_path}) was '
                                 f'modified, but not yet reloaded: '
                                 f'on disk: {repo_head}, self._commit: {self._commit}. '
                                 'Reloding before proceeding with the update.')
                    self._reload()

                assert self._commit == repo_head, (
                        "The DB isn't updated to the latest repo version: "
                        f'{self._commit=}, {repo_head=}')
                if task._commit != self._commit:
                    # Possible conflict.
                    orig_tasks = self._load_at(task._commit)
                    orig_task = orig_tasks[task.id]
                    theirs_task = self.get(task.id)
                    logger.trace(
                            f'Maybe conflict? {orig_task=}, {theirs_task=}, '
                            f'{orig_task == theirs_task=}')
                    if orig_task != theirs_task:
                        logger.info(f'Conflict! {orig_task=} != {theirs_task=}.  Task: {asjson(task)}.')
                        # The task was updated.
                        raise UpdateConflict(orig_task, theirs_task, task)
                logger.trace('No conflict, updating.')
                super().update(task)
                new_repo_head = self._get_repo_head()
                assert new_repo_head is not None
                task._commit = new_repo_head

    def _get_repo_head(self) -> str | None:
        commit = subprocess.check_output(
                f'git -C {self._repo_path} rev-parse main', text=True, shell=True)
        return commit.strip()

    # The methods dealing with reading Tasks from a JSON-serialized Pandas
    # DataFrame, and serializing and writing them back to a file.

    def _load(self) -> tuple[dict[TaskID, Task], int]:
        if not self._metadata_path.exists():
            raise RuntimeError("The backing repo doesn't exist")

        with self._file_lock:
            self._commit = self._get_repo_head()
            assert self._commit is not None

            with self._metadata_path.open() as f:
                metadata = json.load(f)

            if not self._tasks_path.exists():
                return {}, metadata['next_id']

            tasks = self._load_at(self._commit)
            return tasks, metadata['next_id']

    def _load_at(self, commit: str) -> dict[TaskID, Task]:
        assert _is_repo_clean(self._repo_path)
        logger.debug(f'Reading the repo at {commit!r}')

        data = subprocess.check_output(
                f'git -C {self._repo_path} show {commit}:tasks.json',
                text=True, shell=True)
        df = pd.read_json(io.StringIO(data), orient='table')
        tasks = self._from_df(df, commit)
        return tasks

    def _persist(self, why: str) -> None:
        with self._file_lock:
            df = self.get_data_frame()
            df.to_json(self._tasks_path, orient='table', indent=2)
            with self._metadata_path.open('w') as f:
                json.dump({'next_id': self._next_id}, f)
            subprocess.check_output(
                    ['git', '-C', self._repo_path, 'add', self._metadata_path, self._tasks_path])
            subprocess.check_output(
                    ['git', '-C', self._repo_path, 'commit', '-m', why])

    def _from_df(self, df: pd.DataFrame, read_at_commit: str) -> dict[TaskID, Task]:
        tasks = {d['id']: Task(**d) for d in df.reset_index().to_dict(orient='records')}
        for t in tasks.values():
            t._commit = read_at_commit  # pylint: disable=protected-access
            if pd.isna(t.parent_id):  # type: ignore
                t.parent_id = None
        return tasks


def _is_repo_clean(repo_path: Path) -> bool:
    """Returns True if a git repo doesn't have any uncommited changes."""
    status = subprocess.check_output(f'git -C {repo_path} status -s', shell=True)
    return not status


class UpdateConflict(Exception):

    def __init__(self, orig_task: Task, theirs_task: Task, task: Task) -> None:
        self.orig_task = orig_task
        self.theirs_task = theirs_task
        self.task = task
        super().__init__(f'Conflict while trying to update {task}: it was '
                         f'already updated from {orig_task} to {theirs_task}.')


class _FSEventHandler(FileSystemEventHandler):

    def __init__(self, task_db: 'PersistentTaskDB') -> None:
        self._task_db = task_db

    def on_modified(self, event: FileSystemEvent) -> None:
        self._task_db._on_modified(event)  # pylint: disable=protected-access
