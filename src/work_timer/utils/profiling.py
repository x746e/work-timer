import ast
import cProfile
import collections
import inspect
import io
import pstats
import sys
import time
import trace

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


def _resolve_call_arg(node: ast.AST, frame: FrameType) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    else:
        raise NotImplementedError


class Trace:

    def __enter__(self):
        self.tracer = trace.Trace(count=1, trace=True)
        sys.settrace(self.tracer.globaltrace)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        sys.settrace(None)
        self.tracer.results().write_results(show_missing=True, summary=True)


class ProfileContextManager:
    def __init__(self, sort_by='tottime'):
        self.profiler = cProfile.Profile()
        self.sort_by = sort_by

    def __enter__(self):
        self.profiler.enable()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.profiler.disable()
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s).sort_stats(self.sort_by)
        ps.print_stats()
        print(s.getvalue())
