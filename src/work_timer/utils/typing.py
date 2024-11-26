"""Type-hinting helpers."""


def not_none[T](obj: T | None) -> T:
    """Assert the `obj` is not None.

    Can be used inline to silence type-checkers complains about possible None-ness.
    """
    assert obj is not None
    return obj
