# Asyncio and Coroutines

Source: https://docs.python.org/3/library/asyncio-task.html

## Calling a coroutine function does not run it

A function defined with `async def` is a coroutine function. Calling it returns a coroutine object; the body does not execute until the coroutine is awaited or scheduled on an event loop. The asyncio documentation notes that simply calling a coroutine will not schedule it to be executed.

## Symptoms of a missing await

```
TypeError: 'coroutine' object is not subscriptable
AttributeError: 'coroutine' object has no attribute 'json'
RuntimeWarning: coroutine 'fetch_user' was never awaited
```

The `RuntimeWarning` is emitted when a coroutine object is garbage-collected without ever being awaited. It is a strong signal that an `await` is missing or that a coroutine function was called from synchronous code.

## Fixes

Inside an `async def` function, await the call:

```python
async def main():
    user = await fetch_user(1)
    print(user["name"])
```

At the top level of a program, start the event loop with `asyncio.run()`, which creates a new loop, runs the coroutine to completion and closes the loop:

```python
import asyncio

asyncio.run(main())
```

To run several coroutines concurrently, use `asyncio.gather()` or an `asyncio.TaskGroup` (Python 3.11+):

```python
async def main():
    async with asyncio.TaskGroup() as tg:
        a = tg.create_task(fetch_user(1))
        b = tg.create_task(fetch_user(2))
    print(a.result(), b.result())
```

## "asyncio.run() cannot be called from a running event loop"

```
RuntimeError: asyncio.run() cannot be called from a running event loop
```

This occurs when `asyncio.run()` is called while a loop is already running, which is common in Jupyter notebooks and inside frameworks such as FastAPI. In those environments, use `await` directly in an async context instead of starting a new loop.

## Blocking calls inside coroutines

Calling blocking functions such as `time.sleep()` or synchronous HTTP clients inside a coroutine blocks the entire event loop. Use `await asyncio.sleep()` and async-aware libraries, or offload blocking work with `await asyncio.to_thread(func, *args)`.
