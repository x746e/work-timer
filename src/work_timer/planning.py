"""Planning support.

Data-structures for selecting a subset of tasks intended to be done in a given
day/week/etc, together with a planned proportion of the time the user intends
to spend on the tasks.

Used by the UI code in ui/planning.py.

Also contains means to save and restore the plans.
"""
import copy
import dataclasses
from dataclasses import dataclass
import datetime
import json
from pathlib import Path
import subprocess

from typing import Sequence

import pandas as pd

from work_timer.taskdb import TaskID
from work_timer.utils.time import td


class Plan:

    """Defines a set of Tasks intended to be done during the Plan.period.

    Also specifies the planned amout of working hours the user will be able to
    spend during the `period` -- `total_hours`.

    Each of the `PlannedItems` has a proportion of time it should be allocated
    from the `total_hours`.
    """

    period: 'PlannedPeriod'
    total_hours: float
    _items: dict[TaskID, 'PlannedWorkItem']

    # TODO: Make `total_hours` a timedelta.
    def __init__(self, period: 'PlannedPeriod', total_hours: float = 0,
                 items: Sequence['PlannedWorkItem'] = ()) -> None:
        self.period = period
        self.total_hours = total_hours
        self._items = {item.task_id: item for item in items}

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}'
            '('
            f'period={self.period}, '
            f'total_hours={self.total_hours}, '
            f'items={sorted(self._items.values())}'
            ')'
        )

    def __eq__(self, other) -> bool:
        return type(self) is type(other) and self.__dict__ == other.__dict__

    def add(self, task_id: TaskID) -> None:
        if not self._items:
            self._items[task_id] = PlannedWorkItem(task_id, proportion=1)
        elif self._all_proportions_are_equal():
            self._items[task_id] = PlannedWorkItem(
                    task_id, proportion=next(iter(self._items.values())).proportion)
            self._scale_proportions()
        else:
            self._items[task_id] = PlannedWorkItem(task_id, proportion=0)

    def remove(self, task_id: TaskID) -> None:
        del self._items[task_id]
        self._scale_proportions()

    def _all_proportions_are_equal(self) -> bool:
        if not self._items:
            return True
        items = list(self._items.values())
        return all(items[0].proportion == item.proportion for item in items[1:])

    def _scale_proportions(self) -> None:
        if not self._items:
            return
        total = sum(item.proportion for item in self._items.values())
        if total == 1:
            return
        # total * scaling_factor == 1, so:
        scaling_factor = 1 / total
        for item in self._items.values():
            item.proportion *= scaling_factor
        self._check_proportions()

    def _check_proportions(self):
        total = sum(item.proportion for item in self._items.values())
        assert total == 1

    def inc(self, task_id: TaskID, by: datetime.timedelta = td('30m')) -> None:
        """Increment the time planned for `task_id` by `by` timedelta.

        Proportionally decreases the time of all other tasks in the Plan.
        """
        item = self._items[task_id]
        assert 0 <= item.proportion <= 1
        if item.proportion == 0:
            # TODO TODO TODO: Not sure why.
            return
        if item.proportion == 1:
            # Can't increase any more, already takes all the time.
            return
        current_time = self.total_hours * item.proportion
        increased_time = current_time + by / td('1h')
        item.proportion = increased_proportion = increased_time / self.total_hours

        all_others_proportion_before = sum(item.proportion for item in self._items.values()
                                           if item.task_id != task_id)
        all_others_proportion_now = 1 - increased_proportion
        scaling_factor = all_others_proportion_now / all_others_proportion_before
        for item in self._items.values():
            if item.task_id == task_id:
                continue
            item.proportion *= scaling_factor
        self._check_proportions()

    def dec(self, task_id: TaskID, by: datetime.timedelta = td('30m')) -> None:
        self.inc(task_id, -by)

    def get(self, task_id: TaskID) -> 'PlannedWorkItem | None':
        return self._items.get(task_id)

    def has(self, task_id: TaskID) -> bool:
        return task_id in self._items

    def get_data_frame(self) -> pd.DataFrame:
        total_time = datetime.timedelta(hours=self.total_hours)
        def inner():
            for item in self._items.values():
                yield {'task_id': item.task_id,
                       'planned': total_time * item.proportion}
        return pd.DataFrame(inner()).set_index('task_id')

    def to_json(self) -> str:
        d = {}
        if isinstance(self.period, Day):
            d['period'] = {'day': self.period.day.isoformat()}
        else:
            raise NotImplementedError
        d['total_hours'] = self.total_hours
        d['items'] = [dataclasses.asdict(item) for item in sorted(self._items.values())]

        return json.dumps(d, indent=2)

    @classmethod
    def from_json(cls, s: str) -> 'Plan':
        """Convert a JSON string into a `Plan` object."""

        def parse_date(dstr: str) -> datetime.date:
            return datetime.datetime.strptime(dstr, '%Y-%m-%d').date()

        d = json.loads(s)
        if 'day' in d['period']:
            period = Day(parse_date(d['period']['day']))
        else:
            raise NotImplementedError

        items = [PlannedWorkItem(**item) for item in d['items']]

        return cls(period=period, total_hours=d['total_hours'], items=items)


type PlannedPeriod = 'Day | Week'


@dataclass(order=True, frozen=True)
class Day:
    day: datetime.date

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(day=<{self.day.isoformat()}>)'


@dataclass(order=True)
class Week:
    # `from_` and `to` can define a subset of a calendar week #week_num.
    from_: datetime.date
    to: datetime.date
    week_num: int

    def __hash__(self):
        return hash(self.week_num)


def format_period(period: PlannedPeriod) -> str:
    match period:
        case Day():
            return f'{period.day.isoformat()}'
        case Week():
            raise NotImplementedError


@dataclass(order=True)
class PlannedWorkItem:
    task_id: TaskID
    proportion: float = 0.


class PlanDB:

    """Saves / restores `Plan`s.

    This implementation is using persistent on-disk git repo.
    """

    def __init__(self, repo_path: Path) -> None:
        self._repo_path = repo_path.expanduser()
        self._plans: dict[PlannedPeriod, Plan] = {}
        for plan in self._load():
            self._plans[plan.period] = plan

    @classmethod
    def init_repo(cls, repo_path: Path) -> None:
        assert not (repo_path / '.git').exists()
        subprocess.check_output(f'git -C {repo_path} init', shell=True)

    def add(self, plan: Plan) -> None:
        assert plan.period not in self._plans
        self._save(plan)

    def update(self, plan: Plan) -> None:
        assert plan.period in self._plans
        if self._plans[plan.period] == plan:
            return
        self._save(plan)

    def _save(self, plan: Plan) -> None:
        # Write to disk.
        fname = f'{format_period(plan.period)}.json'
        plan_file = self._repo_path / fname
        with open(plan_file, 'wt', encoding='utf-8') as f:
            f.write(plan.to_json())
        # Commit.
        subprocess.check_output(f'git -C {self._repo_path} add {plan_file}', shell=True)
        subprocess.check_output(f'git -C {self._repo_path} commit -m "Saving {plan}"',
                                shell=True)

    def get(self, period: PlannedPeriod) -> Plan:
        return self._plans[period]

    def get_all(self) -> dict[PlannedPeriod, Plan]:
        return copy.deepcopy(self._plans)

    def _load(self):
        def all_files():
            for root, dirs, files in self._repo_path.walk():
                dirs[:] = [d for d in dirs if d.endswith('.git')]
                yield from [root / f for f in files if f.endswith('.json')]

        for path in all_files():
            with path.open('rt') as f:
                yield Plan.from_json(f.read())
