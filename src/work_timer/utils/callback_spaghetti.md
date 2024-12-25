TODO: Rename into callback-spaghetti tracing.

Let's trace what this code will do:

```python
1.  timer = Timer(self.config, clock=self.clock)

2.  timer.start(self.task.id)
3.  self.clock.advance('25m')  # one work period
4.  self.clock.advance('20m')  # one break
```

# 1.

```
0: Timer.__init__
     _Bugger.__init__
        _Bugger.timer_is_not_ticking
        _Bugger._schedule_bugging
            _scheduler.enter(..., action=self._bug)
            Thread.start
                                                                 scheduler.run
   Timer.start                                                     FakeClock.time()
     SingleTaskTimer.__init__                                      FakeClock.sleep()
       STT._when_timer_starts_ticking
       STT._schedule_period_end
         _scheduler.enter(..., action=self._on_period_end)
         Thread.start                                                                   scheduler.run
       STT._on_sub_period_start_callback                                                  FakeClock.time()
         Timer._on_sub_period_start                                                       FakeClock.sleep()
           _Bugger.timer_is_ticking
             _Bugger._cancel_bugging
               scheduler.cancel

25: ...
```

How do I generate such a listing programmatically?

## Toy Example

Let's start with a toy example.

```
def bar(i):
  return i

def foo(i):
  if not i:
    return 0
  return foo(i - 1) + bar(i)

def outer():
  return foo(2)

outer()
bar(2)
foo(1)
```

That should generate:

```
outer()
  foo(2)
    foo(1)
      foo(0) -> 0
      bar(1) -> 1
    -> 1
    bar(2) -> 2
  -> 3
-> 3
bar(2) -> 2
foo(1)
  foo(0) -> 0
  bar(1) -> 1
-> 1
```

### With a Thread

```
def starter():
  thread = Thread(target=target)
  thread.start()
  thread.join()

def target():
  return 1

starter()
```

```
starter()
  Thread.__init__(target=target)
  Thread.start()
                                      target() -> 1
  Thread.join()
-> None
```


## High-Level Design

### Records / storage

What data do I collect (and store)?  I want to collect a lot, and then filter it out at the output
phase.

I imagine I can have something like:

```
@dataclass
class Call:
  id: CallID
  parent: CallID
  thread: ThreadID
  start: datetime
  end: datetime
  func: Func  # Maybe just name.  Maybe (class, method).  Probably should have file/module.
  args: Args  # deepcopy of (args, kwargs).  Or a string.
  ret: object
```

### Filtering
### Rendering
### Interface

A TUI will be handy, to be able to adapt filtering, fold/unfold the calls, etc.

Initially, though, it will just programmatically configured class.
