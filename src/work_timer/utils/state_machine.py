"""State machine abstraction."""
import collections


# TODO: Use a metaclass.
class StateMachine:

    """State machine abstraction.

    To use, define an `State` enum, and state transition handlers like this:

        class Machine(StateMachine):
            class State(enum.Enum):
                RUNNING = 1
                STOPPED = 2

            @handler(State.RUNNING, State.STOPPED)
            def _run_to_stopped(self):
                print('Stopping the machine')

        m = Machine()
        m.transition_to(Machine.State.STOPPED)

    """

    def __init__(self):
        self._state = next(iter(self.State))  # type: ignore  # pylint: disable=no-member
        marked_methods = collections.defaultdict(list)
        for member in self.__class__.__dict__.values():
            for transition in getattr(member, '_transitions', []):
                marked_methods[transition].append(member)

        self._handlers = collections.defaultdict(list)
        for ((from_state, to_state), methods) in marked_methods.items():
            if from_state == ANY_STATE:
                for st in self.State:  # type: ignore  # pylint: disable=no-member
                    if st == to_state:
                        continue
                    self._handlers[(st, to_state)].extend(methods)
            else:
                self._handlers[(from_state, to_state)].extend(methods)

    def get_state(self):
        return self._state

    def transition_to(self, state, *args, **kwargs):
        from_state = self._state
        to_state = state
        if (from_state, to_state) not in self._handlers:
            raise DisallowedStateTransitionError(
                    f"Transition from {from_state} to {to_state} isn't allowed",
                    from_state=from_state, to_state=to_state)
        for h in self._handlers[(from_state, to_state)]:
            h(self, *args, **kwargs)
        self._state = to_state


class _AnyState:
    # pylint: disable=too-few-public-methods

    def __repr__(self):
        return '<ANY_STATE>'


ANY_STATE = _AnyState()


def handler(*states):
    """Mark a method as a state transition handler.

    Can be either used with woth from- and to-states:

        @handler(State.RUNNING, State.STOPPED)
        def from_running_to_stopped(self): ...

    Or with just one state, in which case it will be a handler to all the
    transitions to that state, regardless of the previous state:

        @handler(State.STOPPED)
        def from_any_to_stopped(self): ...
    """

    if len(states) == 2:
        from_, to = states
    elif len(states) == 1:
        from_ = ANY_STATE
        to = states[0]
    else:
        raise TypeError(f'`handler` takes one or two states, got: {states!r}')

    def marker(handler_method):
        transitions = getattr(handler_method, '_transitions', [])
        transitions.append((from_, to))
        handler_method._transitions = transitions  # pylint: disable=protected-access
        return handler_method

    return marker


class DisallowedStateTransitionError(ValueError):

    def __init__(self, message, from_state, to_state):
        super().__init__(message)
        self.from_state = from_state
        self.to_state = to_state
