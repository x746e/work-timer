"""Tests for work_timer.utils.profiling."""
import ast
import inspect
import time
import typing
import unittest

from work_timer.utils import profiling
from work_timer.utils.profiling import TimeFunctionCalls


class approx:  # pylint: disable=invalid-name
    """Equals appoximately to its `n` argument.

    Useful for rough comparisons inside unittests.
    """

    def __init__(self, n, eps=0.1):
        self.n = n
        self.eps = eps

    def __eq__(self, other) -> bool:
        return abs(self.n - other) < self.eps

    def __repr__(self):
        return f'{self.__class__.__name__}({self.n})'


class TestTimeFunctionCalls(unittest.TestCase):
    # pylint: disable=disallowed-name

    def test_the_simplest_call(self):
        def bar():
            pass

        with TimeFunctionCalls('bar') as t:
            bar()

        self.assertEqual(
                t.finished_calls, {
                    'bar()': [approx(0)],
                }
        )

    def test_more_complex_calls(self):
        def bar():
            pass

        def foo(i):
            if i > 0:
                foo(i - 1)
            bar()

        def outer():
            foo(2)

        with TimeFunctionCalls('foo') as t:
            outer()
            bar()
            foo(1)

        self.assertEqual(
                t.finished_calls, {
                    'foo(i=0)': [approx(0), approx(0)],
                    'foo(i=1)': [approx(0), approx(0)],
                    'foo(i=2)': [approx(0)],
                }
        )

    def test_c_calls(self):
        with TimeFunctionCalls('sleep') as t:
            time.sleep(0)
            time.sleep(0.001)
        self.assertEqual(
                t.finished_calls, {
                    'sleep(0)': [approx(0)],
                    'sleep(0.001)': [approx(0)],
                }
        )



class TestResovleCallArg(unittest.TestCase):

    @typing.no_type_check
    def test_resolving_constant(self):
        # pylint: disable=protected-access
        f = inspect.currentframe()
        num = ast.parse('42').body[0].value
        self.assertEqual(profiling._resolve_call_arg(num, f), 42)
        s = ast.parse('"42"').body[0].value
        self.assertEqual(profiling._resolve_call_arg(s, f), "42")


class LogCallTests:

    def type_error_is_preserved(self):
        """
        >>> from work_timer.utils.profiling import log_call
        >>> @log_call
        ... def f_with_two_args(a, b):
        ...     pass
        ...
        >>> f_with_two_args(1, 2, 3)
        Traceback (most recent call last):
            ...
        TypeError: f_with_two_args() takes 2 positional arguments but 3 were given
        """


if __name__ == '__main__':
    unittest.main()
