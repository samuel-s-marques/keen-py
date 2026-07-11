"""Proactive per-service request pacing.

``BaseModule.get_http_client()``/``request()`` already retry *after* a 429,
which is reactive -- it only backs off once a provider has already rejected
a request. Some providers (Shodan's free tier: 1 req/sec) are strict enough
that even a single burst can trip a limit worth avoiding proactively. This
is one shared, in-process pacer every module can call before its first
request per run, instead of each growing its own throttling logic.

Not a full token bucket -- a per-service minimum-interval gate is enough for
Keen's actual usage shape (one module run issuing a handful of sequential
requests to one provider), and it's trivially easy to reason about.
"""

import asyncio
import time
from typing import Any

# One asyncio.Lock + last-call timestamp per service name, shared
# process-wide so concurrent module runs hitting the same provider still
# serialize against each other rather than each pacing independently.
_locks: dict[str, asyncio.Lock] = {}
_last_call: dict[str, float] = {}

# Conservative defaults per provider, used when no `rate_limit_<service>_rps`
# preference is configured. Override via `pref set rate_limit_shodan_rps 0.5`
# (etc.) for a stricter/looser pace.
DEFAULT_RPS = {
    "shodan": 1.0,
    "censys": 2.0,
    "crtsh": 1.0,
    "hibp": 1.5,
    "malshare": 2.0,
    # archive.org's Save API throttles anonymous callers aggressively --
    # paced more conservatively than the generic 2.0 rps fallback.
    "archive_org": 0.5,
    # ipapi.co's free tier has no documented per-second limit, but its daily
    # cap (1,000/day) means a conservative pace is worth defaulting to.
    "ipapi_co": 1.0,
}


def clear_state() -> None:
    """Reset all pacing state (test helper)."""
    _locks.clear()
    _last_call.clear()


def _resolve_rps(service: str, config: Any) -> float:
    rps = DEFAULT_RPS.get(service, 2.0)
    if config is not None:
        try:
            pref = config.get_preference(f"rate_limit_{service}_rps")
            if pref:
                rps = float(pref)
        except (TypeError, ValueError):
            pass
    return rps


async def acquire(service: str, config: Any = None) -> None:
    """Block until it's safe to issue another request to ``service``.

    Enforces a minimum interval of ``1 / rps`` between requests to the same
    ``service`` name, where ``rps`` comes from the ``rate_limit_<service>_rps``
    preference (falling back to :data:`DEFAULT_RPS`). A non-positive/invalid
    rate disables pacing entirely (returns immediately) rather than dividing
    by zero.
    """
    rps = _resolve_rps(service, config)
    if rps <= 0:
        return
    min_interval = 1.0 / rps

    lock = _locks.setdefault(service, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        last = _last_call.get(service, 0.0)
        wait = min_interval - (now - last)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call[service] = time.monotonic()
