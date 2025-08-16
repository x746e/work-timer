"""Tests for work_timer.planning."""
import datetime
from pathlib import Path
import tempfile
from unittest import TestCase

from typing import no_type_check

from work_timer.taskdb import TaskID
from work_timer.planning import Day, Plan, PlanDB, PlannedWorkItem, format_period
from work_timer.utils.testing import approx
from work_timer.utils.time import td
from work_timer.utils.typing import not_none


class TestPlanProportions(TestCase):

    def test_first_item_is_set_to_1(self):
        plan = Plan(PLAN.period)

        plan.add(TaskID(42))

        assert not_none(plan.get(TaskID(42))).proportion == 1

    def test_next_items_scales_proportions_down_if_all_proportions_are_equal(self):
        plan = Plan(PLAN.period)

        plan.add(TaskID(42))
        plan.add(TaskID(24))

        assert not_none(plan.get(TaskID(42))).proportion == .5
        assert not_none(plan.get(TaskID(24))).proportion == .5

    def test_three_scaled_items(self):
        plan = Plan(PLAN.period)

        plan.add(TaskID(42))
        plan.add(TaskID(24))
        plan.add(TaskID(44))

        assert not_none(plan.get(TaskID(42))).proportion == approx(.333)
        assert not_none(plan.get(TaskID(24))).proportion == approx(.333)
        assert not_none(plan.get(TaskID(44))).proportion == approx(.333)

    def test_if_proportions_are_not_equal_next_item_is_set_to_zero(self):
        plan = Plan(PLAN.period, total_hours=6)

        plan.add(TaskID(42))
        plan.add(TaskID(24))
        plan.inc(TaskID(42))
        plan.add(TaskID(101))

        assert not_none(plan.get(TaskID(101))).proportion == 0

    def test_removing_item_scales_proportions(self):
        plan = Plan(PLAN.period)

        plan.add(TaskID(42))
        plan.add(TaskID(24))
        plan.add(TaskID(44))
        plan.remove(TaskID(24))

        assert not_none(plan.get(TaskID(42))).proportion == .5
        assert not_none(plan.get(TaskID(44))).proportion == .5

    def test_increasing_by_time(self):
        plan = Plan(PLAN.period, total_hours=6)

        plan.add(TaskID(42))
        plan.add(TaskID(24))
        # At this point both should be allocated 3h
        plan.inc(TaskID(42), by=td('30m'))

        assert not_none(plan.get(TaskID(42))).proportion == approx(3.5 / 6)
        assert not_none(plan.get(TaskID(24))).proportion == approx(2.5 / 6)


SERIALIZED_PLAN = '''\
{
  "period": {
    "day": "2020-01-02"
  },
  "total_hours": 5.5,
  "items": [
    {
      "task_id": 1,
      "proportion": 0.6
    },
    {
      "task_id": 2,
      "proportion": 0.4
    }
  ]
}'''

PLAN = Plan(period=Day(datetime.date(2020, 1, 2)),
            total_hours=5.5,
            items=[PlannedWorkItem(task_id=TaskID(1), proportion=.6),
                   PlannedWorkItem(task_id=TaskID(2), proportion=.4)])


class TestPlanSerialization(TestCase):

    def test_to_json(self):
        assert PLAN.to_json() == SERIALIZED_PLAN

    def test_from_json(self):
        got_plan = Plan.from_json(SERIALIZED_PLAN)

        assert got_plan == PLAN


class PlanDBMixin:

    """Helps creating PlanDB and backing git repos."""

    @no_type_check
    def init_plan_db(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # pylint: disable=consider-using-with
        repo_path = Path(temp_dir.name)
        PlanDB.init_repo(repo_path)
        self.addCleanup(temp_dir.cleanup)
        return repo_path

    def plan_db(self, repo_path: Path) -> PlanDB:
        db = PlanDB(repo_path=repo_path)
        return db


class TestPlanDB(TestCase, PlanDBMixin):

    def test_saving(self):
        repo_path = self.init_plan_db()
        db = self.plan_db(repo_path)

        db.add(PLAN)

        with open(repo_path / f'{format_period(PLAN.period)}.json', 'rt', encoding='utf-8') as f:
            persistent_plan = f.read()
        assert persistent_plan == SERIALIZED_PLAN

    def test_loading(self):
        repo_path = self.init_plan_db()

        with open(repo_path / '2020-01-02.json', 'wt', encoding='utf-8') as f:
            f.write(SERIALIZED_PLAN)

        db = self.plan_db(repo_path)
        assert db.get(Day(datetime.date(2020, 1, 2))) == PLAN
