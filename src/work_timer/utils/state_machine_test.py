"""Tests for work_timer.utils.state_machine."""
import enum
import unittest

from work_timer.utils.state_machine import StateMachine, handler, DisallowedStateTransitionError

# pylint: disable=missing-class-docstring
# pylint: disable=multiple-statements


unittest.util._MAX_LENGTH = 2000  # type: ignore  # pylint: disable=protected-access


class InitialStateTest(unittest.TestCase):

    def test_the_first_state_is_initial_state(self):
        class Machine(StateMachine):
            class State(enum.Enum):
                RUNNING = 1
                STOPPED = 2

        m = Machine()

        self.assertEqual(m.get_state(), Machine.State.RUNNING)

    def test_setting_initial_state_on_a_class(self):
        pass

    def test_setting_initial_state_on_instance_creation(self):
        pass


class AllowedTransitionsTest(unittest.TestCase):

    class Machine(StateMachine):
        class State(enum.Enum):
            RUNNING = 1
            STOPPED = 2

        @handler(State.RUNNING, State.STOPPED)
        def noop(self): pass

    def test_allowed_transition(self):
        m = self.Machine()
        m.transition_to(m.State.STOPPED)
        self.assertEqual(m.get_state(), m.State.STOPPED)

    def test_disallowed_transition(self):
        m = self.Machine()
        m.transition_to(m.State.STOPPED)
        with self.assertRaises(DisallowedStateTransitionError):
            m.transition_to(m.State.RUNNING)

    def test_disallowed_transition_error_attributes(self):
        m = self.Machine()
        m.transition_to(m.State.STOPPED)
        try:
            m.transition_to(m.State.RUNNING)
        except DisallowedStateTransitionError as e:
            self.assertEqual(e.from_state, m.State.STOPPED)
            self.assertEqual(e.to_state, m.State.RUNNING)

    def test_transition_to_the_same_state_is_not_allowed(self):
        m = self.Machine()
        with self.assertRaises(DisallowedStateTransitionError):
            m.transition_to(m.State.RUNNING)

    def test_transitions_with_single_argument_handlers(self):
        class Machine(StateMachine):
            class State(enum.Enum):
                RUNNING = 1
                PAUSED = 2
                STOPPED = 3

            @handler(State.RUNNING, State.PAUSED)
            def on_pause(self):
                pass

            @handler(State.STOPPED)
            def on_stop(self):
                pass

        def get_at_state(state):
            m = Machine()
            if state == m.State.RUNNING:
                return m
            m.transition_to(state)
            return m

        State = Machine.State

        shouldnt_be_allowed = [
            (State.RUNNING, State.RUNNING),
            (State.PAUSED, State.PAUSED),
            (State.STOPPED, State.STOPPED),

            (State.PAUSED, State.RUNNING),
            (State.STOPPED, State.RUNNING),
            (State.STOPPED, State.PAUSED),
        ]
        for from_, to in shouldnt_be_allowed:
            m = get_at_state(from_)
            with self.assertRaises(DisallowedStateTransitionError):
                m.transition_to(to)


class TransitionHandlersTest(unittest.TestCase):

    def test_transition_handler_is_called_on_transition(self):

        handler_called = False

        class Machine(StateMachine):
            class State(enum.Enum):
                RUNNING = 1
                STOPPED = 2

            @handler(State.RUNNING, State.STOPPED)
            def running_to_stopped(self):
                nonlocal handler_called
                handler_called = True

        m = Machine()
        m.transition_to(m.State.STOPPED)

        self.assertTrue(handler_called)

    def test_handler_without_from_state(self):

        class Machine(StateMachine):

            def __init__(self):
                super().__init__()
                self.handler_called = False

            class State(enum.Enum):
                RUNNING = 1
                PAUSED = 2
                STOPPED = 3

            @handler(State.PAUSED)
            def noop(self): pass

            @handler(State.STOPPED)
            def to_stopped(self):
                self.handler_called = True

        m = Machine()
        m.transition_to(m.State.STOPPED)
        self.assertTrue(m.handler_called)

        m = Machine()
        m.transition_to(m.State.PAUSED)
        m.transition_to(m.State.STOPPED)
        self.assertTrue(m.handler_called)


if __name__ == '__main__':
    unittest.main()
