"""Time-related utilities."""
from datetime import timedelta
import re


def td(s: str | timedelta) -> timedelta:
    """𝑇ime 𝐷elta.

    Currently can parse "<int>(s|m|h)", like "10h" or "15m" or "3s".

    >>> td('5m')
    datetime.timedelta(seconds=300)
    >>> td('1h')
    datetime.timedelta(seconds=3600)
    >>> td('1h5m10s')
    datetime.timedelta(seconds=3910)

    >>> td(timedelta(seconds=36000))
    datetime.timedelta(seconds=36000)
    """
    if isinstance(s, timedelta):
        return s

    m = re.match(r'((?P<hours>\d+)h)?'
                 r'((?P<minutes>\d+)m)?'
                 r'((?P<seconds>\d+)s)?$', s)
    if not m:
        raise ValueError(f"Can't parse {s!r}")

    groupdict = m.groupdict(default=0)
    hours = int(groupdict['hours'])
    minutes = int(groupdict['minutes'])
    seconds = int(groupdict['seconds'])
    return timedelta(seconds=((int(hours) * 60) + int(minutes)) * 60 + int(seconds))
