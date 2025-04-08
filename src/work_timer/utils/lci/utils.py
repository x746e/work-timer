"""Misc helper code."""
from contextlib import contextmanager
import fcntl
import functools
import os
from pathlib import Path
import re
import shlex
import subprocess
import threading


def run(cmd, **kwargs) -> subprocess.CompletedProcess:
    cmd = [str(arg) for arg in cmd]
    print(f'Running {shlex.join(cmd)}')
    return subprocess.run(cmd, **kwargs)  # type: ignore  # pylint: disable=subprocess-run-check


def check_output(cmd, **kwargs) -> subprocess.CompletedProcess:
    kwargs = {
        'text': True,
    } | kwargs
    cmd = [str(arg) for arg in cmd]
    print(f'Running {shlex.join(cmd)}')
    return subprocess.check_output(cmd, **kwargs)  # type: ignore  # pylint: disable=subprocess-run-check


def popen(cmd, **kwargs) -> subprocess.Popen:
    cmd = [str(arg) for arg in cmd]
    print(f'Running {shlex.join(cmd)}')
    return subprocess.Popen(cmd, **kwargs)  # type: ignore


def get_environ(unset=()):  # pylint: disable=dangerous-default-value
    env = {}
    for name, val in os.environ.items():
        if any(re.match(pat, name) for pat in unset):
            continue
        env[name] = val
    return env


@contextmanager
def chdir(directory: Path):
    cwd = Path.cwd()
    os.chdir(directory)
    try:
        yield
    finally:
        os.chdir(cwd)


class PipeReader(threading.Thread):
    """An object that can be passed to Popen's stdout/stderr.

    Pretends to be a file that can be written to.  Reads the output in a thread, makes it available via
    `getvalue()`.
    """

    # I know, I should've just used subprocess.PIPEs, but doing it this way is more fun.
    # (Especially if you count debugging deablocked threads as fun!)

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._read_end, self._write_end = os.pipe()
        fcntl.fcntl(self._read_end, fcntl.F_SETPIPE_SZ, _get_pipe_max_size())
        self._data = []
        self.start()

    def fileno(self):
        return self._write_end

    def run(self) -> None:
        try:
            while data := os.read(self._read_end, _get_pipe_max_size()):
                self._data.append(data)
        finally:
            os.close(self._read_end)

    def getvalue(self) -> str:
        self.close()
        return ''.join(data.decode('utf-8') for data in self._data)

    def read(self) -> str:
        return self.getvalue()

    def close(self) -> None:
        if self.is_alive():
            os.close(self._write_end)
            self.join()


@functools.cache
def _get_pipe_max_size():
    return int(open('/proc/sys/fs/pipe-max-size', 'rb').read().strip())
