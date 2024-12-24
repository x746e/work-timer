"""Misc profiling and tracing utilities."""
import ast
from dataclasses import dataclass, field
import cProfile
import collections
import functools
import inspect
import io
import pstats
import sys
import textwrap
import threading
import time
import trace
import traceback

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

    def __exit__(self, exc_type, exc_value, tb):
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


def _resolve_call_arg(node: ast.AST, frame: FrameType) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return frame.f_locals[node.id]

    raise NotImplementedError(f"Resolving {ast.dump(node)} is not implemented {locals()}")


def _resolve_callable_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr

    raise NotImplementedError(f"Resolving {ast.dump(node)} is not implemented {locals()}")


class Trace:

    def __enter__(self):
        self.tracer = trace.Trace(count=1, trace=True)  # pylint: disable=attribute-defined-outside-init
        sys.settrace(self.tracer.globaltrace)
        return self

    def __exit__(self, exc_type, exc_value, tb):
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

    def __exit__(self, exc_type, exc_value, tb):
        self.profiler.disable()
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s).sort_stats(self.sort_by)
        ps.print_stats()
        print(s.getvalue())


def log_call(*args, **kwargs):
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

    def decorator(f):
        sig = inspect.signature(f)

        def first(iterable):
            return next(iter(iterable))

        has_self = sig.parameters and first(sig.parameters.keys()) == 'self'

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            ret = f(*args, **kwargs)

            bound_args = sig.bind(*args, **kwargs)

            is_method = False
            obj = None
            if has_self:
                obj = bound_args.arguments['self']
                meth = getattr(obj, f.__name__)
                if meth.__wrapped__ == f:
                    is_method = True

            if opts['thread_name']:
                print(f'[{threading.current_thread().name}] ', end='')

            if obj and hasattr(obj, '_clock'):
                print(f'<{obj._clock.time()}> ', end='')   # pylint: disable=protected-access

            if is_method:
                print(
                    f'{obj!r}.{f.__name__}(' +
                    ', '.join(f'{k}={v}' for k, v
                              in bound_args.arguments.items() if k != 'self') +
                    f') -> {ret}'
                )
            else:
                print(
                    f'{f.__name__}(' +
                    ', '.join(f'{k}={v}' for k, v
                              in bound_args.arguments.items()) +
                    f') -> {ret}'
                )

            if opts['bt']:
                traceback.print_stack(file=sys.stdout)

            return ret

        return wrapper

    opts = {
        'bt': False,
        'thread_name': False,
        'short_name': False,
    }

    if args:
        # Assuming it was used as bare decorator, `@log_call`.
        (f,) = args
        return decorator(f)
    else:
        # Assuming it was passed some arguments, e.g. `@log_call(bt=True)`
        opts.update(kwargs)
        return decorator

    # TODO: It's also possible to change the bytecode to have a `print` just
    #       before each return.  And probably a statement at the start caching
    #       the parameter values.  (If they are changed in the bytecode!)
    #       Not terribly useful, but fun to do :D.
    #
    #       Try making this bytecode changing version, compare the performance
    #       with the regular version above.


@dataclass
class CallRecord:
    frame_id: str
    call: str


@dataclass
class ReturnRecord:
    frame_id: str
    ret: str
    duration: float


type Record = CallRecord | ReturnRecord


class CallLogger:
    """Profiling/tracing-based logger."""

    def __init__(self, thread_filter=None):  # type: ignore[reportRedeclaration]
        self.tracers = collections.defaultdict(_Tracer)
        if not thread_filter:
            def thread_filter(unused_thread_name: str) -> bool:
                return True
        self.thread_filter = thread_filter

    def __enter__(self):
        threading.setprofile(self._trace)
        sys.setprofile(self._trace)
        return self

    def __exit__(self, exc_type, exc_value, tb):
        threading.setprofile(None)
        sys.setprofile(None)
        if len(self.tracers) == 1:
            (tracer,) = self.tracers.values()
            print(format_records(tracer.records))
            self.records  = tracer.records  # pylint: disable=attribute-defined-outside-init
            return
        for thread_name, tracer in self.tracers.items():
            if not self.thread_filter(thread_name):
                continue
            print('\n\n' + '>>' * 20 + ' ' + thread_name)
            print(format_records(tracer.records))

    def _trace(self, *args):
        self.tracers[threading.current_thread().name].trace(*args)


class _Tracer:

    records: list[Record]

    def __init__(self):
        self._calls = []
        self.records = []

    def trace(self, frame, why, arg):
        """sys.settrace-compatible function."""
        # pylint: disable=inconsistent-return-statements,too-many-locals,too-many-statements

        # tname = threading.current_thread().name
        qualname = frame.f_code.co_qualname

        if why not in ('call', 'return', 'c_call', 'c_return'):
            return

        if qualname in (
                'CallLogger.__enter__', 'CallLogger.__exit__',
                'Thread._bootstrap_inner', 'Thread._delete',
                'Thread._bootstrap', 'setprofile'):
            return
        if '__del__' in qualname:
            return

        call = ''
        looks_like_method = False
        arg_info = inspect.getargvalues(frame)
        if why in ('call', 'return'):
            # TODO: Maybe don't hardcode 'self'?
            if arg_info.args and arg_info.args[0] == 'self':
                self_arg = arg_info.locals['self']
                self_class_name = self_arg.__class__.__name__
                cls, meth = frame.f_code.co_qualname.split('.')[-2:]

                if self_class_name == cls:
                    looks_like_method = True
                    arg_info.args.pop(0)
                    call = f'{cls}.{meth}{inspect.formatargvalues(*arg_info)}'

        if not looks_like_method:
            def get_func_name():
                if why in ('call', 'return'):
                    return frame.f_code.co_name
                if why in ('c_call', 'c_return'):
                    return arg.__name__

            func_name = get_func_name()

            def get_args():
                if why in ('call', 'return'):
                    return inspect.formatargvalues(*inspect.getargvalues(frame))
                if why in ('c_call', 'c_return'):
                    # TODO: Try replacing this madness with an bytecode-based approach.
                    lines, start_line = inspect.getsourcelines(frame)
                    source_line = lines[frame.f_lineno - start_line]
                    if func_name not in source_line:
                        return '(???)'
                    try:
                        parsed_line = ast.parse(source_line.strip())
                    except (IndentationError, SyntaxError):
                        next_line = lines[frame.f_lineno - start_line + 1]
                        two_lines = textwrap.dedent(source_line + next_line)
                        parsed_line = ast.parse(two_lines)

                    calls = [node for node in ast.walk(parsed_line)
                             if isinstance(node, ast.Call)
                             and _resolve_callable_name(node.func) == func_name]
                    if len(calls) != 1:
                        return '(???)'
                    (call,) = calls
                    try:
                        args = [_resolve_call_arg(a, frame) for a in call.args]
                    except Exception:  # pylint: disable=broad-exception-caught
                        return '(???)'

                    args = ', '.join(repr(a) for a in args)
                    return f'({args})'

            call = f'{func_name}{get_args()}'

        assert call

        frame_id = hex(id(frame))

        if why in ('call', 'c_call'):
            self._calls.append((frame_id, time.time(), call))
            self.records.append(CallRecord(frame_id, call))
        elif why in ('return', 'c_return'):
            assert self._calls, f'self._calls is empty! {locals()=}'
            saved_frame_id, start_time, unused_started_call = self._calls.pop()
            assert saved_frame_id == frame_id
            # assert call == started_call, f'{call=} != {started_call=}'
            #  TODO: "call" includes args -- which are modifiable locals
            #  Maybe just assert there that the stuff before the args is the same?
            self.records.append(
                ReturnRecord(
                    frame_id,
                    ret=repr(arg) if why == 'return' else '???',
                    duration=time.time() - start_time,
                )
            )


@dataclass
class Call:
    call: str
    ret: str
    duration: float
    child_calls: list['Call'] = field(default_factory=list)


def format_records(records: list[Record]) -> str:
    return format_calls(process_records(records))


def process_records(records: list[Record]) -> list[Call]:
    """Convert a list of Records into a list of Calls."""
    started = []
    children = [[]]

    for rec in records:
        match rec:
            case CallRecord():
                started.append(rec)
                children.append([])
            case ReturnRecord():
                c = started.pop()
                kids = children.pop()
                ret = rec
                assert c.frame_id == ret.frame_id
                children[-1].append(
                    Call(
                        call=c.call,
                        ret=ret.ret,
                        duration=ret.duration,
                        child_calls=kids,
                    )
                )

    assert len(children) == 1
    return children[0]


def format_calls(calls: list[Call]) -> str:
    """Format a list of records."""

    ret = []

    def inner(calls: list[Call], lvl=0) -> None:

        def add(msg: str) -> None:
            ret.append(f'{"  " * lvl}{msg}')

        for call in calls:
            if not call.child_calls:
                add(f'{call.call} -> {call.ret}')
            else:
                add(call.call)
                inner(call.child_calls, lvl + 1)
                add(f'-> {call.ret}')

    inner(calls)

    return '\n'.join(ret)
