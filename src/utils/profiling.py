import ast
import collections
import contextlib
import inspect
import numbers
import sys
import time

from types import FrameType


class TimeFunctionCalls:

    def __init__(self, function_name: str):
        self._function_name = function_name
        self._started_calls = {}
        self.finished_calls = collections.defaultdict(list)

    def __enter__(self):
        sys.setprofile(self.trace)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        sys.setprofile(None)
        self.finished_calls = dict(self.finished_calls)

    def trace(self, frame, why, arg):

        if why not in ('call', 'return', 'c_call', 'c_return'):
            return

        def get_func_name():
            if why in ('call', 'return'):
                return frame.f_code.co_name
            elif why in ('c_call', 'c_return'):
                return arg.__name__

        func_name = get_func_name()
        if func_name != self._function_name:
            return

        def get_args():
            if why in ('call', 'return'):
                return inspect.formatargvalues(*inspect.getargvalues(frame))
            elif why in ('c_call', 'c_return'):
                lines, start_line = inspect.getsourcelines(frame)
                source_line = lines[frame.f_lineno - start_line]
                assert func_name in source_line
                parsed_line = ast.parse(source_line.strip())
                calls = [node for node in ast.walk(parsed_line) if isinstance(node, ast.Call)]
                assert len(calls) == 1, "More than one call on a line isn't yet supported.  TODO: Filter nodes by name"
                call = calls[0]
                args = [_resolve_call_arg(a, frame) for a in call.args]
                args = ', '.join(repr(a) for a in args)
                return f'({args})'

        call = f'{func_name}{get_args()}'
        frame_id = hex(id(frame))

        if why in ('call', 'c_call'):
            assert frame_id not in self._started_calls
            self._started_calls[frame_id] = (time.time(), call)
        elif why in ('return', 'c_return'):
            start_time, started_call = self._started_calls.pop(frame_id)
            assert call == started_call
            self.finished_calls[call].append(time.time() - start_time)


import unittest


class approx:

    def __init__(self, n: numbers.Real, eps=0.1):
        self.n = n
        self.eps = eps

    def __eq__(self, other: numbers.Real) -> bool:
        return abs(self.n - other) < self.eps

    def __repr__(self):
        return f'{self.__class__.__name__}({self.n})'


class TestTimeFunctionCalls(unittest.TestCase):

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


def _resolve_call_arg(node: ast.AST, frame: FrameType) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    else:
        raise NotImplementedError


class TestResovleCallArg(unittest.TestCase):
    
    def test_resolving_constant(self):
        f = inspect.currentframe()
        num = ast.parse('42').body[0].value
        self.assertEqual(_resolve_call_arg(num, f), 42)
        s = ast.parse('"42"').body[0].value
        self.assertEqual(_resolve_call_arg(s, f), "42")


if __name__ == '__main__':
    unittest.main()
