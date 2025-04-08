"""Classes representing a request to run the CI on a code base."""
from abc import ABC
import argparse
from dataclasses import dataclass
import enum
from pathlib import Path
import tomllib

from typing import Self

from .config import Config
from .utils import check_output


@dataclass
class _Source(ABC):
    repo_path: Path


@dataclass
class Commit(_Source):
    commit: str


@dataclass
class Index(_Source):
    pass


@dataclass
class WorkingTree(_Source):
    pass


class UseConfigFrom(enum.StrEnum):
    WORKSPACE = enum.auto()
    REPO = enum.auto()


@dataclass
class Request:
    source: _Source
    use_config_from: UseConfigFrom
    # Only run tasks with (any of) these tasks.
    tags: frozenset[str] = frozenset()

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Self:
        if args.commit:
            source = Commit(args.repo_path, commit=args.commit)
        elif args.index:
            source = Index(args.repo_path)
        elif args.working_tree:
            source = WorkingTree(args.repo_path)
        else:
            assert False, "Can't make a UseConfigFrom out of {args!r}"
        return cls(source=source, use_config_from=args.use_config_from, tags=args.tags)


def get_config(request: Request) -> Config:
    match request.use_config_from:
        case UseConfigFrom.WORKSPACE:
            match request.source:
                case Commit(repo_path, commit):
                    config_text = check_output(
                        ['git', '-C', repo_path, 'show', f'{commit}:lci.toml'])
                case Index(repo_path):
                    config_text = check_output(
                        ['git', '-C', repo_path, 'show', ':lci.toml'])
                case WorkingTree(repo_path):
                    with open(repo_path / 'lci.toml', 'rt') as f:
                        config_text = f.read()
        case UseConfigFrom.REPO:
            with open(request.source.repo_path / 'lci.toml', 'rt') as f:
                config_text = f.read()
    return Config.from_config(tomllib.loads(config_text))  # type: ignore
