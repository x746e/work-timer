"""Migrate the TaskDB from v3 to v4.

v4 adds an internal "break" task.
"""
# pylint: disable=duplicate-code
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd


type Metadata = dict
type Tasks = dict[int, dict]


def migrate_3_to_4(repo_path: Path) -> None:
    metadata, tasks = _read(repo_path)
    metadata, tasks = _transform(metadata, tasks)
    _write(repo_path, metadata, tasks)


def _read(repo_path: Path) -> tuple[Metadata, Tasks]:
    metadata_path = repo_path / 'metadata.json'
    tasks_path = repo_path / 'tasks.json'
    with metadata_path.open() as f:
        metadata = json.load(f)
    assert metadata['version'] == 3

    df = pd.read_json(tasks_path, orient='table')
    tasks = {d['id']: d for d in df.reset_index().to_dict(orient='records')}

    return metadata, tasks


def _transform(metadata: Metadata, tasks: Tasks) -> tuple[Metadata, Tasks]:
    metadata['version'] = 4

    break_id = -2
    assert break_id not in tasks
    break_ = {
        'id': break_id,
        'title': 'Not really a task -- a break!',
        'description': '',
        'status': 'new',
        'priority': 'P0',
        'type': 'REGULAR',
        'child_ids': [],
    }

    return metadata, {break_id: break_} | tasks


def _write(repo_path: Path, metadata: Metadata, tasks: Tasks) -> None:
    metadata_path = repo_path / 'metadata.json'
    tasks_path = repo_path / 'tasks.json'

    with metadata_path.open('w') as f:
        json.dump(metadata, f)

    df = pd.DataFrame(tasks.values())
    df = df.convert_dtypes()
    df = df.set_index('id')
    df.status = pd.Categorical(df.status, categories=['new', 'done'])
    df.priority = pd.Categorical(df.priority, categories=['P0', 'P1', 'P2', 'P3'], ordered=True)
    df.type = pd.Categorical(df.type, categories=[
        'REGULAR', 'BUG', 'PROJECT', 'MOONSHOT', 'EPIC', 'WORKFLOW',
        'REFACTORING', 'IMPROVEMENT', 'IDEA', 'FEATURE'])

    df.to_json(tasks_path, orient='table', indent=2)

    print('Migration completed.  Please check the diff below and commit manually.')
    subprocess.check_call(['git', '-C', repo_path, 'diff'])


if __name__ == '__main__':
    migrate_3_to_4(Path(sys.argv[1]))
