"""Misc profiling and tracing utilities."""
import ast
import cProfile
import collections
import functools
import inspect
import io
import pstats
import sys
import time
import trace

from types import FrameType


# Random idea: how do I know when, say, my naive approach to task persistence --
# just write down the whole thing to tasks.json on disk -- becomes too slow?
#
# An obvious answer: I'll see that the interface getting slugish.
# But that can be a bit hard to notice.
#
# I'm thinking about something like: have some profiling going on in the
# background at all times.  Have some general metrics..  Event loop latency, is
# there such a thing?
#
# Taking a step back: for performance (regression) testing, which it is, we need:
# (1) Define a performance metric to track  (2) Collect data about it
# (3) Report about the regressions.
#
#
# ## Defining the metrics
#
# Can we have just collect most/many calls?  For the TaskDB example the metric
# can be "time it takes to run TaskDB.add".  The method can either be
# explicitly marked, or the profiler can do it somehow automatically.  A few options:
# - Do a background random sampling.
# - Just sample everything.
# - With either random or everything sampling, determine the too fast to sample functions.
#
# Let's try to collect everything, and if it's too expensive, consider the alternatives.
#
# While here I can also go and fix the USDT call/return probes in cpython.
#
#
# ## Collecting
#
# A few ideas about collection:
# - Explicitly mark the profiled functions with decorators.
# - sys.setprofile.
# - USDT probes.
# - Some ebpf hackery.  I know you can get all the info from python somehow.  It is there,
#   you can explore it with gdb (though probably with a bunch of python code running inside gdb).
#   Can you do it without unreasonable effort?
#   Most likely it's better to use some code on the cpython side -- like USDT probes.
#
# The data will have to be stored somewhere in some kind of database.
#
# ## Reporting
#
# A cron-job to look for regressions and send emails?


class TimeFunctionCalls:

    """A context manager for timing function invocations.

    Times the invocations of `function_name` inside the context, and stores the
    map of `<func>(<args>) -> [list of times]` at `self.finished_calls`.
    """

    def __init__(self, function_name: str):
        self._function_name = function_name
        self._started_calls = {}
        self.finished_calls = collections.defaultdict(list)

    def __enter__(self):
        sys.setprofile(self._trace)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        sys.setprofile(None)
        self.finished_calls = dict(self.finished_calls)

    def _trace(self, frame, why, arg):
        # pylint: disable=inconsistent-return-statements

        if why not in ('call', 'return', 'c_call', 'c_return'):
            return

        def get_func_name():
            if why in ('call', 'return'):
                return frame.f_code.co_name
            if why in ('c_call', 'c_return'):
                return arg.__name__

        func_name = get_func_name()
        if func_name != self._function_name:
            return

        def get_args():
            if why in ('call', 'return'):
                return inspect.formatargvalues(*inspect.getargvalues(frame))
            if why in ('c_call', 'c_return'):
                lines, start_line = inspect.getsourcelines(frame)
                source_line = lines[frame.f_lineno - start_line]
                assert func_name in source_line
                parsed_line = ast.parse(source_line.strip())
                calls = [node for node in ast.walk(parsed_line) if isinstance(node, ast.Call)]
                assert len(calls) == 1, (
                        "More than one call on a line isn't yet supported.  "
                        "TODO: Filter nodes by name")
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


def _resolve_call_arg(node: ast.AST, unused_frame: FrameType) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    raise NotImplementedError


class Trace:

    def __enter__(self):
        self.tracer = trace.Trace(count=1, trace=True)  # pylint: disable=attribute-defined-outside-init
        sys.settrace(self.tracer.globaltrace)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        sys.settrace(None)
        self.tracer.results().write_results(show_missing=True, summary=True)


class ProfileContextManager:
    """Profile the code inside the context."""

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


def log_call(f):
    """Print the invocations of `f`.

    >>> @log_call
    ... def foo(a, b=0):
    ...     return a + b
    ...
    >>> foo(42)
    foo(a=42) -> 42
    42
    >>> foo(10, b=20)
    foo(a=10, b=20) -> 30
    30

    Method support:

    >>> class Foo:
    ...     def __repr__(self):
    ...        return 'Foo()'
    ...     @log_call
    ...     def bar(self, a):
    ...         return a + 1
    ...
    >>> foo = Foo()
    >>> foo.bar(1)
    Foo().bar(a=1) -> 2
    2
    """

    sig = inspect.signature(f)

    def first(iterable):
        return next(iter(iterable))

    has_self = sig.parameters and first(sig.parameters.keys()) == 'self'

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        bound_args = sig.bind(*args, **kwargs)
        ret = f(*args, **kwargs)

        is_method = False
        obj = None
        if has_self:
            obj = bound_args.arguments['self']
            meth = getattr(obj, f.__name__)
            if meth.__wrapped__ == f:
                is_method = True

        if is_method:
            print(
                f'{obj!r}.{f.__name__}(' +
                ', '.join(f'{k}={v}' for k, v in bound_args.arguments.items() if k != 'self') +
                f') -> {ret}'
            )
        else:
            print(
                f'{f.__name__}(' +
                ', '.join(f'{k}={v}' for k, v in bound_args.arguments.items()) +
                f') -> {ret}'
            )

        return ret

    return wrapper

    # TODO: It's also possible to change the bytecode to have a `print` just
    #       before each return.  And probably a statement at the start caching
    #       the parameter values.  (If they are changed in the bytecode!)
    #       Not terribly useful, but fun to do :D.
    #
    #       Try making this bytecode changing version, compare the performance
    #       with the regular version above.



class CallLogger:
    """Profiling/tracing-based logger."""

    # - How will that work with async/await?
    # - How will that work with multithreahing?


    def __init__(self):
        self._started_calls = {}
        # self.finished_calls = collections.defaultdict(list)

    def __enter__(self):
        sys.setprofile(self._trace)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        sys.setprofile(None)
        # self.finished_calls = dict(self.finished_calls)

    def _trace(self, frame, why, arg):
        # pylint: disable=inconsistent-return-statements

        pass

        # if why not in ('call', 'return', 'c_call', 'c_return'):
        #     return
        #
        # def get_func_name():
        #     if why in ('call', 'return'):
        #         return frame.f_code.co_name
        #     if why in ('c_call', 'c_return'):
        #         return arg.__name__
        #
        # func_name = get_func_name()
        # if func_name != self._function_name:
        #     return
        #
        # def get_args():
        #     if why in ('call', 'return'):
        #         return inspect.formatargvalues(*inspect.getargvalues(frame))
        #     if why in ('c_call', 'c_return'):
        #         lines, start_line = inspect.getsourcelines(frame)
        #         source_line = lines[frame.f_lineno - start_line]
        #         assert func_name in source_line
        #         parsed_line = ast.parse(source_line.strip())
        #         calls = [node for node in ast.walk(parsed_line) if isinstance(node, ast.Call)]
        #         assert len(calls) == 1, (
        #                 "More than one call on a line isn't yet supported.  "
        #                 "TODO: Filter nodes by name")
        #         call = calls[0]
        #         args = [_resolve_call_arg(a, frame) for a in call.args]
        #         args = ', '.join(repr(a) for a in args)
        #         return f'({args})'
        #
        # call = f'{func_name}{get_args()}'
        # frame_id = hex(id(frame))
        #
        # if why in ('call', 'c_call'):
        #     assert frame_id not in self._started_calls
        #     self._started_calls[frame_id] = (time.time(), call)
        # elif why in ('return', 'c_return'):
        #     start_time, started_call = self._started_calls.pop(frame_id)
        #     assert call == started_call
        #     self.finished_calls[call].append(time.time() - start_time)



def main():

    def inc(a):
        return a + 1

    def inc_n_tripple(b):
        return inc(b) * 3

    inc_n_tripple(2)
    # -> Call('inc_n_tripple', {'b': 2}, thread=...)
    # -> Call('inc', {'a': 2}, thread=..., parent=...)
    # -> Return('inc',


if __name__ == '__main__':
    main()
    # import doctest
    # doctest.testmod()
