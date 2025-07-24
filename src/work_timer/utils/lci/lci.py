"""A simplistic local CI."""
# PYTHON_ARGCOMPLETE_OK
import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

from typing import Iterable, Self

import argcomplete
import rich
from rich import progress
from xdg_base_dirs import xdg_cache_home

from . import argutils
from . import config
from . import request
from .utils import run, popen, chdir, PipeReader, get_environ


def main() -> None:
    """The entrypoint to the CLI interface."""
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(required=True)

    run_parser = subparsers.add_parser('run')
    setup_run(run_parser)

    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    args.func(args)


def setup_run(parser: argparse.ArgumentParser) -> None:
    """Set up the argument parser for the `lci run` subcommand."""
    # What code to test.
    parser.add_argument('--repo-path', type=argutils.path, required=True)
    source_type = parser.add_mutually_exclusive_group(required=True)
    source_type.add_argument('--commit',
                             help='The commit to run tasks on.  Useful for post-commit hooks')
    source_type.add_argument('--index', action='store_true',
                             help='Run the tasks on the current index.  Useful for pre-commit hooks.')
    source_type.add_argument('--working-tree', action='store_true',
                             help='Run the tasks on the current working tree, both index and '
                                  "modified files.  Doesn't copy ignore or untracked files though.  "
                                  'Useful for interactive usage.')

    # What tasks to run.
    parser.add_argument('--tags', type=argutils.comma_separated_set, default=frozenset(['default']),
                        metavar='[tag1[,tag2[,...]]]', help='Only run tasks with (any of) these tags.')
    parser.add_argument('--use-config-from', default=request.UseConfigFrom.WORKSPACE,
                        choices=request.UseConfigFrom, type=request.UseConfigFrom)

    # Other settings.
    parser.add_argument('--workspaces-parent', type=argutils.path, default=_get_workspaces_parent())
    parser.add_argument('--in-place', action='store_true',
                        help="Don't copy the code anywhere, don't create a new .venv, just run in this "
                             'repo.')

    # Development options.
    parser.add_argument('--pdb', action='store_true')
    parser.add_argument('--skip-cleanup-workspace-on-failure', action='store_true',
                        help="Don't cleanup the workspace on failure.")

    parser.set_defaults(func=run_command)


def run_command(args: argparse.Namespace) -> None:
    if args.pdb:
        breakpoint()  # pylint: disable=forgotten-debug-statement

    options = Options.from_args(args)
    req = request.Request.from_args(args)
    if args.in_place:
        process_in_place_request(options, req)
    else:
        process_request(options, req)


def _get_workspaces_parent() -> Path:
    d = xdg_cache_home() / 'lci' / 'workspaces'
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Options:
    workspaces_parent: Path
    in_place: bool
    skip_cleanup_workspace_on_failure: bool = False

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Self:
        return cls(workspaces_parent=args.workspaces_parent, in_place=args.in_place,
                   skip_cleanup_workspace_on_failure=args.skip_cleanup_workspace_on_failure)


@dataclass
class _ProcessingState:
    """An object to store state about processing a request."""
    options: Options
    request: request.Request
    config: config.Config
    workspace: Path
    checkout_output: str = ''
    prepare_output: str = ''


def process_request(options: Options, req: request.Request) -> None:
    state = None
    try:
        state = _checkout(options, req)
        _prepare(state)
        _run_tasks(state)
        # _publish_result(state)
    except LciFailed:
        _cleanup(options, state)
        sys.exit(1)


def process_in_place_request(options: Options, req: request.Request) -> None:
    assert isinstance(req.source, request.WorkingTree)
    state = None
    try:
        state = _ProcessingState(
            options = options,
            request = req,
            config = request.get_config(req),
            workspace = req.source.repo_path,
        )
        _run_tasks(state)
    except LciFailed:
        sys.exit(1)


def _checkout(options: Options, req: request.Request) -> _ProcessingState:
    workspace_prefix = f'lci_{req.source.repo_path.name}_'
    workspace = Path(tempfile.mkdtemp(prefix=workspace_prefix, dir=options.workspaces_parent))
    state = _ProcessingState(
        options = options,
        request = req,
        config = request.get_config(req),
        workspace = workspace,
    )

    pipe_reader = PipeReader()
    processses = []
    match req.source:
        case request.Commit(repo_path, commit):
            git = popen(['git', '-C', repo_path, 'archive', commit],
                        stdout=subprocess.PIPE, stderr=pipe_reader)
            tar = popen(['tar', '-x', '-C', state.workspace],
                        stdin=git.stdout, stdout=pipe_reader, stderr=pipe_reader)
            processses.extend([git, tar])
        case request.Index(repo_path):
            with chdir(repo_path):
                git = popen(['git', 'checkout-index', '-a', '--prefix', f'{workspace}/'],
                            stdout=pipe_reader, stderr=pipe_reader)
            processses.extend([git])
        case request.WorkingTree(repo_path):
            git = popen(['git', '-C', repo_path, 'ls-files', '-z'],
                        stdout=subprocess.PIPE, stderr=pipe_reader)
            rsync = popen(['rsync', '-a', '--files-from=-', '--from0', repo_path, state.workspace],
                          stdin=git.stdout, stdout=pipe_reader, stderr=pipe_reader)
            processses.extend([git, rsync])

    for p in processses:
        p.wait()
    if failed := [p for p in processses if p.returncode != EXIT_CODE_SUCCESS]:
        for p in failed:
            rich.print(f'[red]{shlex.join(p.args)} failed with return code {p.returncode}.')
        print(pipe_reader.getvalue())
        raise LciFailed()

    state.checkout_output = pipe_reader.getvalue()
    return state


def _prepare(state: _ProcessingState) -> None:
    pipe_reader = PipeReader()
    with chdir(state.workspace):
        try:
            run(['uv', 'sync'], stdout=pipe_reader, stderr=pipe_reader)
        except subprocess.CalledProcessError as e:
            rich.print(f'[red bold]{e}[/]')
            print(pipe_reader.getvalue())
            raise LciFailed() from e
    state.prepare_output = pipe_reader.getvalue()


class LciFailed(Exception):
    """An exception used to exit the program in case of failure."""


EXIT_CODE_SUCCESS = 0


def _run_tasks(state: _ProcessingState) -> None:
    with chdir(state.workspace):
        task_handles: list[RunningTaskHandle] = []
        for task in _get_tasks(state):
            try:
                task_handles.append(_start_task(state, task))
            except Exception as e:
                rich.print(f'[bold red]Failed to start {shlex.join(task.command)}[/]: {e}')
                raise LciFailed() from e

    def terminate_all():
        for handle in task_handles:
            if handle.is_running():
                handle.popen.terminate()

    def get_output(handle: RunningTaskHandle, filter_output=True) -> str:
        output = handle.pipe.getvalue()
        if filter_output and handle.task.output_filter:
            output = '\n'.join(line for line in output.splitlines()
                               if re.search(handle.task.output_filter, line))
        return output.strip()

    with progress.Progress(
        progress.SpinnerColumn(),
        progress.TextColumn("[progress.description]{task.description}"),
        progress.BarColumn(),
        progress.TaskProgressColumn(),
        progress.TimeRemainingColumn(),
        progress.TimeElapsedColumn(),
    ) as p:
        for handle in task_handles:
            handle.progress_task_id = p.add_task(handle.task.name, total=None)

        def log(s):
            p.log(s)

        while any(not h.is_processed for h in task_handles):
            for handle in task_handles:
                time.sleep(.1)
                if handle.is_running():
                    continue
                if handle.is_processed:
                    continue

                assert handle.progress_task_id is not None
                p.update(handle.progress_task_id, total=1, completed=1)

                elapsed = time.perf_counter() - handle.start_time

                ret = handle.popen.poll()
                if ret == EXIT_CODE_SUCCESS:
                    if handle.task.show_output and (output := get_output(handle)):
                        log(f'[green][b]{handle.task.name}[/b] done![/] (in {elapsed:.2f}s)')
                        log(output)
                else:
                    terminate_all()
                    log(f'[red][b]{handle.task.name}[/b] failed![/] (in {elapsed:.2f}s)')
                    log(get_output(handle, filter_output=False))
                    raise LciFailed()
                handle.is_processed = True


@dataclass
class RunningTaskHandle:
    task: config.Task
    popen: subprocess.Popen
    start_time: float
    pipe: PipeReader
    progress_task_id: progress.TaskID | None = None
    is_processed: bool = False

    def is_running(self) -> bool:
        return self.popen.poll() is None


def _start_task(state: _ProcessingState, task: config.Task) -> RunningTaskHandle:
    pipe_reader = PipeReader()
    env = get_environ(unset=(state.config.common_env + task.env).unset)
    handle = RunningTaskHandle(
        task = task,
        popen = popen([task.command], shell=True, stdout=pipe_reader, stderr=pipe_reader,
                      env=env),
        pipe = pipe_reader,
        start_time = time.perf_counter(),
    )
    return handle


def _get_tasks(state: _ProcessingState) -> Iterable[config.Task]:
    for task in state.config.tasks:
        if state.request.tags:
            if not state.request.tags & task.tags:
                continue
        yield task


def _cleanup(options: Options, state: _ProcessingState | None) -> None:
    if options.skip_cleanup_workspace_on_failure:
        return
    if not state:
        return
    assert state.workspace != state.request.source.repo_path
    assert not (state.workspace / '.git').exists()
    shutil.rmtree(state.workspace)


if __name__ == '__main__':
    main()
