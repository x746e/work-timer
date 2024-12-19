"""Tests for work_timer.utils.testing."""
from threading import Thread, Lock

from work_timer.utils.testing import FakeClock


class TestFakeClock:

    def test_it(self):
        clock = FakeClock()

        f1_called = False

        def f1():
            clock.sleep(42)
            nonlocal f1_called
            f1_called = True

        t = Thread(target=f1)
        t.start()

        clock.advance('42s')
        clock.stop()

        t.join()

        assert f1_called

    def test_many_sleepers(self):
        clock = FakeClock()

        lock = Lock()
        called = set()

        def make_sleeper(idx: int) -> Thread:

            def sleeper():
                clock.sleep(idx * 100)
                with lock:
                    called.add(idx)

            return Thread(target=sleeper)

        sleepers = [make_sleeper(idx) for idx in range(100)]
        for t in sleepers:
            t.start()

        clock.advance(f'{100 * 100}s')

        for t in sleepers:
            t.join()

        assert called == set(range(100))

    def test_called_in_order(self):
        clock = FakeClock()

        lock = Lock()
        called_when = {}

        def make_sleeper(idx: int) -> Thread:

            def sleeper():
                how_long = idx * 100
                clock.sleep(how_long)
                now = clock.time()
                with lock:
                    assert all(called_earlier_idx < idx
                               for called_earlier_idx in called_when)
                    assert idx not in called_when
                    for called_earlier_idx in called_when:  # pylint: disable=consider-using-dict-items
                        if called_earlier_idx > idx:
                            raise AssertionError(
                                    f"Sleeper #{called_earlier_idx} shouldn't be called before #{idx}")
                        if called_when[called_earlier_idx] > how_long:
                            raise AssertionError(
                                    f"Sleeper #{called_earlier_idx} was called after #{idx} "
                                    f"at {called_when[called_earlier_idx]}.  {now=}, {how_long=}.")
                    tmp = [v < how_long for v in called_when.values()]
                    assert all(tmp), called_when  # Should be equivalent to the for loop above.
                    called_when[idx] = now

            return Thread(target=sleeper)

        sleepers = [make_sleeper(idx) for idx in range(10)]
        for t in sleepers:
            t.start()

        clock.advance(f'{100 * 100}s')

        for t in sleepers:
            t.join()

        assert set(called_when) == set(range(10))

    def test_called_in_order_(self):
        clock = FakeClock()

        lock = Lock()
        called_when = {}

        def make_sleeper(idx: int) -> Thread:

            def sleeper():
                how_long = idx * 100
                clock.sleep(how_long)
                now = clock.time()
                with lock:
                    called_when[idx] = now

            return Thread(target=sleeper)

        sleepers = [make_sleeper(idx) for idx in range(100)]
        for t in sleepers:
            t.start()

        clock.advance(f'{100 * 100}s')

        for t in sleepers:
            t.join()

        assert set(called_when) == set(range(100))
        call_times = [call_time for idx, call_time in sorted(called_when.items())]
        assert call_times == sorted(call_times)

    def test_called_on_time(self):
        clock = FakeClock()

        lock = Lock()
        called_when = {}

        def make_sleeper(idx: int) -> Thread:

            def sleeper():
                how_long = idx * 100
                clock.sleep(how_long)
                now = clock.time()
                with lock:
                    called_when[idx] = now

            return Thread(target=sleeper)

        sleepers = [make_sleeper(idx) for idx in range(100)]
        for t in sleepers:
            t.start()

        clock.advance(f'{100 * 100}s')

        for t in sleepers:
            t.join()

        assert set(called_when) == set(range(100))
        assert all(call_time == idx * 100
                   for idx, call_time in called_when.items())

    def test_advances_without_callers_as_well(self):
        clock = FakeClock()

        clock.advance('42s')

        assert clock.time() == 42
