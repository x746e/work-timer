"""Migrate the TaskDB from v2 to v3.

v3 adds a root task, parent to all top-level tasks.
"""
# pylint: disable=duplicate-code
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd


type Metadata = dict
type Tasks = dict[int, dict]


def migrate_1_to_2(repo_path: Path) -> None:
    metadata, tasks = _read(repo_path)
    metadata, tasks = _transform(metadata, tasks)
    _write(repo_path, metadata, tasks)


def _read(repo_path: Path) -> tuple[Metadata, Tasks]:
    metadata_path = repo_path / 'metadata.json'
    tasks_path = repo_path / 'tasks.json'
    with metadata_path.open() as f:
        metadata = json.load(f)
    assert metadata['version'] == 2

    df = pd.read_json(tasks_path, orient='table')
    tasks = {d['id']: d for d in df.reset_index().to_dict(orient='records')}

    return metadata, tasks


def _transform(metadata: Metadata, tasks: Tasks) -> tuple[Metadata, Tasks]:
    metadata['version'] = 3

    all_ids = {t['id'] for t in tasks.values()}

    someones_kids = sum([t['child_ids'] for t in tasks.values()], [])
    orphans = all_ids - set(someones_kids)
    root = {
        'id': -10,
        'title': 'Root task',
        'description': '',
        'status': 'new',
        'priority': 'P2',
        'child_ids': list(orphans),
    }

    return metadata, {-10: root} | tasks


def _write(repo_path: Path, metadata: Metadata, tasks: Tasks) -> None:
    metadata_path = repo_path / 'metadata.json'
    tasks_path = repo_path / 'tasks.json'

    with metadata_path.open('w') as f:
        json.dump(metadata, f)

    df = pd.DataFrame(tasks.values())
    df = df.convert_dtypes()
    df = df.set_index('id')
    df.status = df.status.astype('category')

    df.to_json(tasks_path, orient='table', indent=2)

    print('Migration completed.  Please check the diff below and commit manually.')
    subprocess.check_call(['git', '-C', repo_path, 'diff'])


if __name__ == '__main__':
    migrate_1_to_2(Path(sys.argv[1]))
