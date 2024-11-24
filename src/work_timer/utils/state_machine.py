import collections
import enum
import functools
import textwrap


# TODO: Use a metaclass.
class StateMachine:

    ALLOWED_TRANSITIONS = set()

    def __init__(self):
        self._state = next(iter(self.State))
        marked_methods = collections.defaultdict(list)
        for name, member in self.__class__.__dict__.items():
            for transition in getattr(member, '_transitions', []):
                marked_methods[transition].append(member)

        self._handlers = collections.defaultdict(list)
        for ((from_state, to_state), methods) in marked_methods.items():
            if from_state == ANY_STATE:
                for st in self.State:
                    if st == to_state:
                        continue
                    self._handlers[(st, to_state)].extend(methods)
            else:
                self._handlers[(from_state, to_state)].extend(methods)

        self.ALLOWED_TRANSITIONS = frozenset(
                self.ALLOWED_TRANSITIONS | set(self._handlers.keys()))

    def get_state(self):
        return self._state

    def transition_to(self, state, *args, **kwargs):
        from_state = self._state
        to_state = state
        if (from_state, to_state) not in self.ALLOWED_TRANSITIONS:
            raise DisallowedStateTransitionError(
                    f"Transition from {from_state} to {to_state} isn't allowed",
                    from_state=from_state, to_state=to_state)
        for handler in self._handlers[(from_state, to_state)]:
            handler(self, *args, **kwargs)
        self._state = to_state


class _AnyState:

    def __repr__(self):
        return '<ANY_STATE>'


ANY_STATE = _AnyState()


def handler(*states):

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
        handler_method._transitions = transitions
        return handler_method

    return marker


class DisallowedStateTransitionError(ValueError):

    def __init__(self, message, from_state, to_state):
        super().__init__(message)
        self.from_state = from_state
        self.to_state = to_state
