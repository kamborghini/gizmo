"""Work that runs after the request that asked for it.

A route that has answered may still owe a slow follow-up: an email, a label
on Gmail, a release of the orders it just printed. `spawn(coro)` schedules it
on the running loop and holds a reference until it is done, because a bare
`asyncio.create_task` can be collected before it ever runs. With no loop (a
script, a test outside one) it answers False and closes the coroutine, so the
caller can do the work inline instead of leaving it unawaited.

On the floor: it imports nothing from the app. Until stage 6 of the 14 October
audit it lived in copilot.py and kept its tasks in the CRM's own set.
"""
import asyncio

_tasks: set = set()


def spawn(coro) -> bool:
    """Run a coroutine after this request; False when there is no loop."""
    try:
        t = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        coro.close()
        return False
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return True
