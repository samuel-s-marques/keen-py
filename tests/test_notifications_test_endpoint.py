import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils import notifications


class FakeConfig:
    def __init__(self, preferences=None, api_keys=None):
        self._preferences = preferences or {}
        self._api_keys = api_keys or {}

    def get_preference(self, key):
        return self._preferences.get(key)

    def get_api_key(self, service):
        return self._api_keys.get(service)


def test_channel_missing_config_detects_absent_telegram_secrets():
    config = FakeConfig()
    assert notifications._channel_missing_config("telegram", config) is not None


def test_channel_missing_config_passes_when_fully_configured():
    config = FakeConfig(
        preferences={"telegram_chat_id": "12345"},
        api_keys={"telegram_bot_token": "abc"},
    )
    assert notifications._channel_missing_config("telegram", config) is None


def test_channel_missing_config_for_email_checks_host_and_to():
    config = FakeConfig(preferences={"smtp_host": "smtp.example.com"})
    assert notifications._channel_missing_config("email", config) is not None

    config2 = FakeConfig(
        preferences={"smtp_host": "smtp.example.com", "smtp_to": "you@example.com"}
    )
    assert notifications._channel_missing_config("email", config2) is None


async def _ok_sender(cfg, msg):
    pass


async def _failing_sender(cfg, msg):
    raise RuntimeError("connection refused")


def test_send_test_notification_reports_per_channel_status(monkeypatch):
    import asyncio

    config = FakeConfig(
        preferences={"notify_channels": "telegram,discord,slack"},
        api_keys={"telegram_bot_token": "abc", "discord_webhook_url": "https://discord/x"},
    )

    monkeypatch.setitem(notifications._SENDERS, "telegram", _failing_sender)
    monkeypatch.setitem(notifications._SENDERS, "discord", _ok_sender)
    try:
        results = asyncio.run(notifications.send_test_notification(config))
    finally:
        pass

    # telegram: configured (chat_id missing though -> not_configured path)
    assert results["telegram"]["ok"] is False
    assert "telegram_chat_id" in results["telegram"]["error"]

    # discord: fully configured and sender succeeds
    assert results["discord"]["ok"] is True
    assert results["discord"]["error"] is None

    # slack: not configured at all
    assert results["slack"]["ok"] is False
    assert results["slack"]["error"] is not None


def test_send_test_notification_reports_sender_exception(monkeypatch):
    import asyncio

    config = FakeConfig(
        preferences={"notify_channels": "discord"},
        api_keys={"discord_webhook_url": "https://discord/x"},
    )
    monkeypatch.setitem(notifications._SENDERS, "discord", _failing_sender)

    results = asyncio.run(notifications.send_test_notification(config))
    assert results["discord"]["ok"] is False
    assert "connection refused" in results["discord"]["error"]
