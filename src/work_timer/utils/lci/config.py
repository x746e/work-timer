"""Classes representing the (per-repo) lci.toml config."""
from dataclasses import dataclass, field

from typing import Self


@dataclass
class Env:
    unset: list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, env_cfg) -> Self:
        return cls(**env_cfg)

    def __add__(self, other: Self) -> Self:
        return self.__class__(
            unset=self.unset + other.unset,
        )


@dataclass
class Task:
    name: str
    command: str
    env: Env
    tags: frozenset[str] = frozenset()
    # Show the output even when the task didn't fail.
    show_output: bool = False
    # Only show the output matching this regex.
    output_filter: str = ''

    @classmethod
    def from_config(cls, name, task_cfg) -> Self:
        return cls(
            name=name,
            command=task_cfg.pop('command'),
            tags=frozenset(task_cfg.pop('tags', frozenset())),
            env=Env.from_config(task_cfg.pop('env', {})),
            **task_cfg,
        )


@dataclass
class Config:
    common_env: Env
    tasks: list[Task]

    @classmethod
    def from_config(cls, cfg) -> Self:
        return cls(
            common_env=Env.from_config(cfg.get('common', {}).get('env', {})),
            tasks=[Task.from_config(name, task_cfg)
                   for name, task_cfg in cfg.get('task', {}).items()],
        )
