import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils import rate_limiter


class FakeConfig:
    def __init__(self, preferences=None):
        self._preferences = preferences or {}

    def get_preference(self, key):
        return self._preferences.get(key)


@pytest.fixture(autouse=True)
def _reset_state():
    rate_limiter.clear_state()
    yield
    rate_limiter.clear_state()


@pytest.mark.asyncio
async def test_first_call_does_not_wait():
    start = time.monotonic()
    await rate_limiter.acquire("shodan", FakeConfig())
    assert time.monotonic() - start < 0.1


@pytest.mark.asyncio
async def test_second_call_waits_for_min_interval():
    config = FakeConfig(preferences={"rate_limit_shodan_rps": "10"})  # 0.1s interval
    await rate_limiter.acquire("shodan", config)
    start = time.monotonic()
    await rate_limiter.acquire("shodan", config)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.09


@pytest.mark.asyncio
async def test_different_services_do_not_block_each_other():
    config = FakeConfig(preferences={"rate_limit_shodan_rps": "1"})  # 1s interval
    await rate_limiter.acquire("shodan", config)
    start = time.monotonic()
    await rate_limiter.acquire("censys", config)
    assert time.monotonic() - start < 0.1


@pytest.mark.asyncio
async def test_unconfigured_service_falls_back_to_default_rps():
    # No preference set -- should use DEFAULT_RPS, not raise or hang.
    await rate_limiter.acquire("malshare", FakeConfig())


@pytest.mark.asyncio
async def test_none_config_uses_defaults():
    await rate_limiter.acquire("shodan", None)


@pytest.mark.asyncio
async def test_zero_or_invalid_rps_disables_pacing():
    config = FakeConfig(preferences={"rate_limit_shodan_rps": "0"})
    await rate_limiter.acquire("shodan", config)
    start = time.monotonic()
    await rate_limiter.acquire("shodan", config)
    assert time.monotonic() - start < 0.1
