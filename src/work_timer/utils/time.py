"""Time-related utilities."""
from datetime import timedelta
import re


def td(s: str | timedelta) -> timedelta:
    """𝑇ime 𝐷elta.

    Currently can parse "<int>(s|m|h)", like "10h" or "15m" or "3s".
    For example:

    >>> td('5m')
    datetime.timedelta(seconds=300)
    >>> td('1h')
    datetime.timedelta(seconds=3600)
    >>> td('1h5m10s')
    datetime.timedelta(seconds=3910)

    It also returns `timedelta` as is:

    >>> td(timedelta(seconds=36000))
    datetime.timedelta(seconds=36000)
    """
    if isinstance(s, timedelta):
        return s

    m = re.match(r'((?P<days>\d+)d)?'
                 r'((?P<hours>\d+)h)?'
                 r'((?P<minutes>\d+)m)?'
                 r'((?P<seconds>\d+)s)?$', s)
    if not m:
        raise ValueError(f"Can't parse {s!r}")

    groupdict = m.groupdict(default=0)
    days = int(groupdict['days'])
    hours = int(groupdict['hours'])
    minutes = int(groupdict['minutes'])
    seconds = int(groupdict['seconds'])
    return timedelta(
        seconds=(((int(days) * 24 + int(hours)) * 60) + int(minutes)) * 60 + int(seconds)
    )


def humanize_td(delta: timedelta) -> str:
    """Convert timedelta into a compact string.

    A reverse operation to `td` above.

    >>> humanize_td(td('5m'))
    '5m'
    >>> humanize_td(td('5d5h5m5s'))
    '5d5h5m5s'
    >>> humanize_td(timedelta(hours=5, microseconds=42))
    '5h42μs'
    """
    microseconds = delta.microseconds
    seconds = int(delta.total_seconds())
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    parts = []
    if days:
        parts.append(f'{days}d')
    if hours:
        parts.append(f'{hours}h')
    if minutes:
        parts.append(f'{minutes}m')
    if seconds:
        parts.append(f'{seconds}s')
    if microseconds:
        parts.append(f'{microseconds}μs')
    return ''.join(parts)
