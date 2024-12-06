"""A facility for the Timer to log the time periods."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from work_timer import taskdb


class TimeLog:
    """Stores the periods, provides reporting."""

    def __init__(self):
        self._periods = self._load()

    def add_period(self, task_id: taskdb.TaskID, start: datetime,
                   duration: timedelta):
        self._periods.append(
                Period(task_id=task_id, start=start, duration=duration))
        self._persist()

    def get_periods(self) -> list['Period']:
        return self._periods

    def get_data_frame(self) -> pd.DataFrame:
        """Returns a DataFrame with the work periods."""
        df = pd.DataFrame(self.get_periods())
        return df

    # Methods for overriding in subclasses.

    def _load(self) -> list['Period']:
        return []

    def _persist(self) -> None:
        pass


@dataclass
class Period:
    task_id: taskdb.TaskID
    start: datetime
    duration: timedelta


class PersistentTimeLog(TimeLog):

    """An implementation of TimeLog that persists the records in a JSON file."""

    def __init__(self, path: Path):
        self._path = path.expanduser()
        super().__init__()

    def _load(self) -> list[Period]:
        if not self._path.exists():
            return []
        df = pd.read_json(self._path, orient='table')
        df = df.astype({'duration': 'timedelta64[ns]'})
        return self._from_df(df)

    def _persist(self) -> None:
        df = self.get_data_frame()
        # It was failing while tring to read timedeltas,
        # so let's just convert to int.
        df.astype({'duration': 'int'}).to_json(self._path, orient='table', indent=2)

    def _from_df(self, df: pd.DataFrame) -> list[Period]:
        return [Period(**p) for p in df.to_dict(orient='records')]
