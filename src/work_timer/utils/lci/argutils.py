"""Argparse helpers."""
from pathlib import Path


def comma_separated_set(arg: str) -> frozenset:
    return frozenset(arg.split(','))


def path(arg: str) -> Path:
    return Path(arg).expanduser().absolute()
