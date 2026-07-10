import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils import notifications


class FakeConfig:
    """Minimal stand-in for ConfigManager's preference/api-key surface."""

    def __init__(self, preferences=None, api_keys=None):
        self._preferences = preferences or {}
        self._api_keys = api_keys or {}

    def get_preference(self, key):
        return self._preferences.get(key)

    def get_api_key(self, service):
        return self._api_keys.get(service)


BASE_JOB = {
    "job_id": "abc123",
    "workspace_name": "case1",
    "module_name": "discovery/whois",
    "target_value": "example.com",
    "status": "completed",
    "nodes_added": 2,
    "edges_added": 1,
    "started_at": "2026-01-01 10:00:00",
    "ended_at": "2026-01-01 10:00:05",
    "error_message": None,
}


def test_should_notify_on_failure_by_default():
    config = FakeConfig()
    job = {**BASE_JOB, "status": "failed"}
    assert notifications._should_notify(config, job) is True


def test_should_not_notify_on_failure_when_disabled():
    config = FakeConfig(preferences={"notify_on_job_failure": "false"})
    job = {**BASE_JOB, "status": "failed"}
    assert notifications._should_notify(config, job) is False


def test_should_not_notify_on_quick_completion_by_default():
    config = FakeConfig()
    job = {**BASE_JOB, "status": "completed"}  # 5s duration, below the 300s default
    assert notifications._should_notify(config, job) is False


def test_should_notify_on_completion_when_explicitly_enabled():
    config = FakeConfig(preferences={"notify_on_job_complete": "true"})
    job = {**BASE_JOB, "status": "completed"}
    assert notifications._should_notify(config, job) is True


def test_should_notify_on_long_running_completion_even_if_not_explicitly_enabled():
    config = FakeConfig(preferences={"notify_min_duration_seconds": "1"})
    job = {
        **BASE_JOB,
        "status": "completed",
        "started_at": "2026-01-01 10:00:00",
        "ended_at": "2026-01-01 10:10:00",  # 600s
    }
    assert notifications._should_notify(config, job) is True


def test_should_not_notify_on_pending_or_running_status():
    config = FakeConfig()
    assert notifications._should_notify(config, {**BASE_JOB, "status": "running"}) is False
    assert notifications._should_notify(config, {**BASE_JOB, "status": "pending"}) is False


def test_format_message_includes_key_fields():
    message = notifications._format_message({**BASE_JOB, "status": "failed", "error_message": "boom"})
    assert "discovery/whois" in message
    assert "example.com" in message
    assert "failed" in message
    assert "boom" in message


@pytest.mark.asyncio
async def test_dispatch_skips_when_no_channels_configured():
    config = FakeConfig(preferences={"notify_channels": ""})
    calls = []
    notifications._SENDERS["telegram"] = lambda cfg, msg: calls.append("telegram")
    try:
        await notifications.dispatch_job_notification(config, {**BASE_JOB, "status": "failed"})
        assert calls == []
    finally:
        notifications._SENDERS["telegram"] = notifications._send_telegram


@pytest.mark.asyncio
async def test_dispatch_calls_each_configured_channel_and_survives_one_failure():
    config = FakeConfig(preferences={"notify_channels": "telegram,discord"})
    calls = []

    async def ok_sender(cfg, msg):
        calls.append("discord")

    async def failing_sender(cfg, msg):
        raise RuntimeError("network down")

    original_telegram = notifications._SENDERS["telegram"]
    original_discord = notifications._SENDERS["discord"]
    notifications._SENDERS["telegram"] = failing_sender
    notifications._SENDERS["discord"] = ok_sender
    try:
        await notifications.dispatch_job_notification(config, {**BASE_JOB, "status": "failed"})
        # The failing telegram sender must not prevent discord from firing.
        assert calls == ["discord"]
    finally:
        notifications._SENDERS["telegram"] = original_telegram
        notifications._SENDERS["discord"] = original_discord


@pytest.mark.asyncio
async def test_send_telegram_noop_without_token_or_chat_id():
    config = FakeConfig()  # no telegram_bot_token api key, no telegram_chat_id pref
    # Should return silently rather than attempting an HTTP call.
    await notifications._send_telegram(config, "hello")


@pytest.mark.asyncio
async def test_send_discord_noop_without_webhook():
    config = FakeConfig()
    await notifications._send_discord(config, "hello")


class FakeWorkspace:
    def __init__(self, job=None):
        self._job = job

    def get_job(self, job_id):
        return self._job if self._job and self._job.get("job_id") == job_id else None


@pytest.mark.asyncio
async def test_notify_job_completion_dispatches_for_known_job(monkeypatch):
    config = FakeConfig(preferences={"notify_channels": "discord"})
    workspace = FakeWorkspace({**BASE_JOB, "status": "failed"})
    dispatched = []

    async def fake_dispatch(cfg, job):
        dispatched.append(job["job_id"])

    monkeypatch.setattr(notifications, "dispatch_job_notification", fake_dispatch)
    await notifications.notify_job_completion(config, workspace, "abc123")
    assert dispatched == ["abc123"]


@pytest.mark.asyncio
async def test_notify_job_completion_is_noop_for_unknown_job():
    config = FakeConfig(preferences={"notify_channels": "discord"})
    workspace = FakeWorkspace(job=None)
    # Must not raise even though the job lookup returns nothing.
    await notifications.notify_job_completion(config, workspace, "does-not-exist")


@pytest.mark.asyncio
async def test_notify_job_completion_swallows_dispatch_errors(monkeypatch):
    config = FakeConfig(preferences={"notify_channels": "discord"})
    workspace = FakeWorkspace({**BASE_JOB, "status": "failed"})

    async def broken_dispatch(cfg, job):
        raise RuntimeError("boom")

    monkeypatch.setattr(notifications, "dispatch_job_notification", broken_dispatch)
    # Must not raise -- a broken notification channel can't break the run.
    await notifications.notify_job_completion(config, workspace, "abc123")


@pytest.mark.asyncio
async def test_notify_job_completion_is_noop_without_workspace():
    config = FakeConfig()
    await notifications.notify_job_completion(config, None, "abc123")
