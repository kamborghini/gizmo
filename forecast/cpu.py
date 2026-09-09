"""How much CPU this process may actually use, and telling the maths libraries.

A container reports the HOST's core count through `os.cpu_count()`, but the
scheduler only lets it run for its cgroup quota. LightGBM's `num_threads=0`
means "one thread per core reported", so on a Railway container that is
allowed half a core it starts dozens of threads that spend their lives
contending for it. A fit that costs 14 seconds on eight real cores, and 23 on
one, took 2318 seconds that way: the work is not the problem, the threads are.

Nothing here is a tuning knob. It is the difference between using the CPU you
have and thrashing the CPU you do not.
"""
from __future__ import annotations

import os

_ENV_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")


def _quota(root: str = "/sys/fs/cgroup") -> float | None:
    """CPUs from the cgroup quota, or None when there is no quota.

    `root` exists so the parsing can be tested against real cgroup files
    rather than trusted; nothing passes it in production."""
    try:                                            # cgroup v2
        with open(root + "/cpu.max", encoding="utf-8") as fh:
            quota, period = fh.read().split()[:2]
        if quota != "max" and float(period) > 0:
            return float(quota) / float(period)
    except (OSError, ValueError, IndexError):
        pass
    try:                                            # cgroup v1
        with open(root + "/cpu/cpu.cfs_quota_us", encoding="utf-8") as fh:
            quota = float(fh.read().strip())
        with open(root + "/cpu/cpu.cfs_period_us", encoding="utf-8") as fh:
            period = float(fh.read().strip())
        if quota > 0 and period > 0:
            return quota / period
    except (OSError, ValueError):
        pass
    return None


# What to do when there is no quota to read. A container limited by CPU WEIGHT
# rather than quota has nothing in cpu.max, and affinity still shows every host
# core, so trusting the core count would oversubscribe exactly as before.
#
# The measurements say cap it, and cap it low. At the real training size one
# fit costs 13.7s on eight cores and 22.8s on one: the whole span of "too few
# threads" is under two times. Oversubscription cost a hundred times. Guessing
# low is nearly free and guessing high is ruinous, so the fallback guesses low.
FALLBACK_MAX = 4


def cpu_budget() -> int:
    """Threads worth starting: never more than the quota, never fewer than one.

    A quota is rounded DOWN and floored at 1, because half a core running one
    thread beats half a core running eight. With no quota, affinity is the next
    best reading, capped at FALLBACK_MAX. `FORECAST_THREADS` overrides the lot
    for a machine whose operator knows better."""
    env = os.environ.get("FORECAST_THREADS", "").strip()
    if env.isdigit() and int(env) > 0:
        return int(env)
    q = _quota()
    if q is not None:
        return max(1, int(q))
    try:
        seen = len(os.sched_getaffinity(0))
    except AttributeError:                          # not Linux
        seen = os.cpu_count() or 1
    return max(1, min(seen, FALLBACK_MAX))


def apply_thread_limits() -> int:
    """Pin every maths library to the budget. MUST run before numpy, OpenBLAS
    or LightGBM are imported: each reads its variable once, when it loads."""
    n = cpu_budget()
    for var in _ENV_VARS:
        os.environ.setdefault(var, str(n))
    return n
