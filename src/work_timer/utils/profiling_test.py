"""Tests for work_timer.utils.profiling."""
import ast
from datetime import datetime
import inspect
from pprint import pprint
import threading
import time
import typing
import unittest
from unittest.mock import ANY

from work_timer.utils import profiling
from work_timer.utils.profiling import (
        CallLogger, CallRecord, ReturnRecord, format_records, Call,
        process_records, TimeFunctionCalls)


class _approx:  # pylint: disable=invalid-name
    """Equals appoximately to its `n` argument.

    Useful for rough comparisons inside unittests.
    """

    def __init__(self, n, eps):
        self.n = n
        self.eps = eps

    def __eq__(self, other) -> bool:
        return abs(self.n - other) < self.eps

    def __repr__(self):
        return f'{self.__class__.__name__}({self.n})'


def approx[T: (int, float)](n: T, eps=0.1) -> T:
    return typing.cast(T, _approx(n, eps))


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


class LogCallTest:

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

    def can_be_called(self):
        """
        >>> from work_timer.utils.profiling import log_call
        >>> @log_call()
        ... def foo():
        ...     pass
        ...
        >>> foo()
        foo() -> None
        """


class TestRecords(unittest.TestCase):

    def test_the_simplest_call(self):
        def bar():
            return None

        with CallLogger() as c:
            bar()

        assert c.records == [
            CallRecord(frame_id=ANY, call='bar()', dt=ANY),
            ReturnRecord(frame_id=ANY, ret='None', dt=ANY),
        ]

    def test_two_calls(self):
        def foo(a):
            return bar(a + 1) + 1

        def bar(b):
            return b * 2

        with CallLogger() as c:
            foo(1)

        assert c.records == [
            CallRecord(
                frame_id=ANY,
                call='foo(a=1)',
                dt=ANY,
            ),
            CallRecord(
                frame_id=ANY,
                call='bar(b=2)',
                dt=ANY,
            ),
            ReturnRecord(
                frame_id=ANY,
                ret='4',
                dt=ANY,
            ),
            ReturnRecord(
                frame_id=ANY,
                ret='5',
                dt=ANY,
            ),
        ]


class TestProcessRecords(unittest.TestCase):

    def test_process_records(self):
        records = [
            CallRecord(
                frame_id='0x1',
                call='foo(a=1)',
                dt=datetime.fromtimestamp(1),
            ),
            CallRecord(
                frame_id='0x2',
                call='bar(b=2)',
                dt=datetime.fromtimestamp(2),
            ),
            ReturnRecord(
                frame_id='0x2',
                ret='4',
                dt=datetime.fromtimestamp(3),
            ),
            ReturnRecord(
                frame_id='0x1',
                ret='5',
                dt=datetime.fromtimestamp(4),
            ),
        ]

        got_calls = process_records(records)

        want_calls = [
            Call(
                call='foo(a=1)',
                ret='5',
                start=datetime.fromtimestamp(1),
                end=datetime.fromtimestamp(4),
                child_calls=[
                    Call(
                        call='bar(b=2)',
                        ret='4',
                        start=datetime.fromtimestamp(2),
                        end=datetime.fromtimestamp(3),
                    ),
                ],
            ),
        ]
        assert got_calls == want_calls


class TestRendering(unittest.TestCase):

    def test_basic_rendering(self):
        """
        >>> def foo(a):
        ...     return bar(a + 1) + 1
        >>> def bar(b):
        ...     return b * 2
        >>> with CallLogger() as c:
        ...    _ = foo(1)
        foo(a=1)
          bar(b=2) -> 4
        -> 5
        """

    def test_format_records(self):
        assert format_records([
            CallRecord(
                frame_id='0x1',
                call='foo(a=1)',
                dt=datetime.now(),
            ),
            CallRecord(
                frame_id='0x2',
                call='bar(b=2)',
                dt=datetime.now(),
            ),
            ReturnRecord(
                frame_id='0x2',
                ret='4',
                dt=datetime.now(),
            ),
            ReturnRecord(
                frame_id='0x1',
                ret='5',
                dt=datetime.now(),
            ),
        ]) == """\
foo(a=1)
  bar(b=2) -> 4
-> 5"""


class BasicCallLoggerTest(unittest.TestCase):

    def test_three_calls(self):
        """
        >>> def bar(i):
        ...     return i
        ...
        >>> def foo(i):
        ...     if not i:
        ...         return 0
        ...     return foo(i - 1) + bar(i)
        ...
        >>> def outer():
        ...     return foo(2)
        ...
        >>> with CallLogger() as c:
        ...    outer()
        ...    bar(2)
        ...    foo(1)
        3
        2
        1
        outer()
          foo(i=2)
            foo(i=1)
              foo(i=0) -> 0
              bar(i=1) -> 1
            -> 1
            bar(i=2) -> 2
          -> 3
        -> 3
        bar(i=2) -> 2
        foo(i=1)
          foo(i=0) -> 0
          bar(i=1) -> 1
        -> 1
        """


class TestTrickyCalls(unittest.TestCase):

    def test_tracing_re_match_doesnt_raise(self):
        import re  # pylint: disable=import-outside-toplevel

        with CallLogger():
            re.match('foo', 'bar')

    def test_weakref_set_doesnt_raise(self):
        from weakref import WeakSet  # pylint: disable=import-outside-toplevel

        class Foo: ...
        foo = Foo()

        with CallLogger() as cl:
            s = WeakSet()
            s.add(foo)
        pprint(cl.records)


class TestMethods(unittest.TestCase):

    def test_method_calls(self):
        """
        >>> class Cls:
        ...     def __init__(self): ...
        >>> with CallLogger() as c:
        ...   _ = Cls()
        Cls.__init__() -> None
        """

    def test_thread_start(self):
        def target():
            pass

        def starter():
            t = threading.Thread(target=target, name='T1')
            t.start()
            time.sleep(.1)

        def call_filter(c: Call) -> bool:
            if c.call == 'starter()':
                return True
            if c.call == 'target()':
                return True
            if (c.call.startswith('Thread.__init__') or
                    c.call.startswith('Thread.start') or
                    c.call.startswith('Thread.run')):
                return True
            return False

        def thread_filter(thread_name: str) -> bool:
            return thread_name in ('MainThread', 'T1')

        with CallLogger(thread_filter=thread_filter, call_filter=call_filter):
            starter()

    def test_c_func_inside_a_method(self):

        def target():
            pass

        class Foo:
            def __init__(self):
                hasattr(target, 'foo')

        with CallLogger() as c:
            Foo()

        pprint(c.records)

    # def test_built_in_function__build_class__(self):
    #     with CallLogger() as c:
    #         class Foo:
    #             def __init__(self):
    #                 pass



if __name__ == '__main__':
    import doctest
    doctest.testmod()
