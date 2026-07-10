"""Pluggable notification dispatcher for job lifecycle events (BEYOND_MALTEGO §7.3).

Channels (Telegram, Discord, Slack, Email) are independent best-effort senders --
a broken/misconfigured channel must never raise out of ``dispatch_job_notification``
or block the run it's reporting on. Each channel's secret (bot token, webhook URL,
SMTP password) is read via ``ConfigManager.get_api_key`` (the same Fernet-encrypted
store used for module API keys), so it's unavailable until the config vault is
unlocked -- in that case the channel is silently skipped, not treated as an error.

Enable/tune via preferences:
  - ``notify_channels``: comma-separated subset of telegram,discord,slack,email (default: none)
  - ``notify_on_job_failure``: send when a job fails (default: true)
  - ``notify_on_job_complete``: send when a job completes successfully (default: false)
  - ``notify_min_duration_seconds``: always notify on completion if the job ran at
    least this long, regardless of ``notify_on_job_complete`` (default: 300)
"""

from datetime import datetime
from typing import Any


def _job_duration_seconds(job: dict) -> float:
    started = job.get("started_at")
    ended = job.get("ended_at")
    if not started or not ended:
        return 0.0
    try:
        fmt = "%Y-%m-%d %H:%M:%S"
        start_dt = datetime.strptime(str(started).split(".")[0], fmt)
        end_dt = datetime.strptime(str(ended).split(".")[0], fmt)
        return max(0.0, (end_dt - start_dt).total_seconds())
    except ValueError:
        return 0.0


def _format_message(job: dict) -> str:
    status = job.get("status", "unknown")
    duration = _job_duration_seconds(job)
    lines = [
        f"[Keen] Job {status}: {job.get('module_name')} on '{job.get('target_value')}'",
        f"Workspace: {job.get('workspace_name')}",
        f"Nodes added: {job.get('nodes_added', 0)} | Edges added: {job.get('edges_added', 0)}",
    ]
    if duration:
        lines.append(f"Duration: {duration:.0f}s")
    if job.get("error_message"):
        lines.append(f"Error: {job['error_message']}")
    return "\n".join(lines)


def _should_notify(config: Any, job: dict) -> bool:
    status = job.get("status")
    if status == "failed":
        return (config.get_preference("notify_on_job_failure") or "true") == "true"
    if status == "completed":
        if (config.get_preference("notify_on_job_complete") or "false") == "true":
            return True
        try:
            min_duration = float(
                config.get_preference("notify_min_duration_seconds") or "300"
            )
        except (TypeError, ValueError):
            min_duration = 300.0
        return _job_duration_seconds(job) >= min_duration
    return False


async def _send_telegram(config: Any, message: str) -> None:
    import httpx

    token = config.get_api_key("telegram_bot_token")
    chat_id = config.get_preference("telegram_chat_id")
    if not token or not chat_id:
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
        )


async def _send_discord(config: Any, message: str) -> None:
    import httpx

    webhook_url = config.get_api_key("discord_webhook_url")
    if not webhook_url:
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(webhook_url, json={"content": message})


async def _send_slack(config: Any, message: str) -> None:
    import httpx

    webhook_url = config.get_api_key("slack_webhook_url")
    if not webhook_url:
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(webhook_url, json={"text": message})


def _send_email_sync(config: Any, message: str) -> None:
    import smtplib
    from email.message import EmailMessage

    host = config.get_preference("smtp_host")
    to_addr = config.get_preference("smtp_to")
    from_addr = config.get_preference("smtp_from") or to_addr
    if not host or not to_addr:
        return

    port = 587
    try:
        port = int(config.get_preference("smtp_port") or "587")
    except (TypeError, ValueError):
        pass

    username = config.get_api_key("smtp_username")
    password = config.get_api_key("smtp_password")

    msg = EmailMessage()
    msg["Subject"] = message.splitlines()[0] if message else "Keen job notification"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(message)

    with smtplib.SMTP(host, port, timeout=10.0) as smtp:
        smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(msg)


async def _send_email(config: Any, message: str) -> None:
    import asyncio

    await asyncio.to_thread(_send_email_sync, config, message)


_SENDERS = {
    "telegram": _send_telegram,
    "discord": _send_discord,
    "slack": _send_slack,
    "email": _send_email,
}


async def dispatch_job_notification(config: Any, job: dict) -> None:
    """Notify configured channels about a job's completion/failure, if warranted.

    Best-effort throughout: a misconfigured or unreachable channel is logged
    and skipped, never raised -- this must never be the reason a run "fails".
    """
    if not _should_notify(config, job):
        return

    channels_pref = config.get_preference("notify_channels") or ""
    channels = [c.strip().lower() for c in channels_pref.split(",") if c.strip()]
    if not channels:
        return

    message = _format_message(job)

    for channel in channels:
        sender = _SENDERS.get(channel)
        if not sender:
            continue
        try:
            await sender(config, message)
        except Exception:
            from loguru import logger

            logger.bind(module="notifications").warning(
                f"Failed to send job notification via '{channel}'"
            )


def _channel_missing_config(channel: str, config: Any) -> str | None:
    """Return a human-readable reason ``channel`` can't send yet, or None if it's ready.

    The senders themselves silently no-op on missing config (so a real job
    completion never raises just because a channel isn't set up) -- that's
    the wrong behavior for a connectivity test, where silence would look
    identical to success. This duplicates each sender's own presence check
    so the test can tell "not configured" apart from "configured but failed".
    """
    if channel == "telegram":
        if not config.get_api_key("telegram_bot_token"):
            return "Missing telegram_bot_token API key"
        if not config.get_preference("telegram_chat_id"):
            return "Missing telegram_chat_id preference"
    elif channel == "discord":
        if not config.get_api_key("discord_webhook_url"):
            return "Missing discord_webhook_url API key"
    elif channel == "slack":
        if not config.get_api_key("slack_webhook_url"):
            return "Missing slack_webhook_url API key"
    elif channel == "email":
        if not config.get_preference("smtp_host") or not config.get_preference(
            "smtp_to"
        ):
            return "Missing smtp_host/smtp_to preference"
    return None


async def notify_job_completion(config: Any, workspace: Any, job_id: str) -> None:
    """Best-effort: look up ``job_id`` and dispatch a completion notification.

    The one shared call every job-terminating call site should use (CLI
    ``run``, magic/playbook execution via ``run_module_on_target``, and the
    web ``_stream_run`` endpoint) instead of each duplicating the
    lookup-then-dispatch pattern -- and each guarding it with its own
    try/except. Never raises: a broken notification channel must not break
    the run whose completion it's reporting on.
    """
    try:
        job = workspace.get_job(job_id) if workspace else None
        if job:
            await dispatch_job_notification(config, job)
    except Exception:
        pass


async def send_test_notification(config: Any) -> dict:
    """Send a synthetic test message to every configured channel, bypassing
    the ``_should_notify`` gate (a failure/duration check makes no sense for
    an on-demand connectivity test). Returns ``{channel: {"ok": bool, "error": str|None}}``
    for each channel in ``notify_channels`` so the caller (the Web UI's
    "Send Test" button) can report exactly which ones are misconfigured.
    """
    channels_pref = config.get_preference("notify_channels") or ""
    channels = [c.strip().lower() for c in channels_pref.split(",") if c.strip()]

    message = "[Keen] This is a test notification from your Integrations settings."
    results: dict = {}
    for channel in channels:
        sender = _SENDERS.get(channel)
        if not sender:
            results[channel] = {"ok": False, "error": "Unknown channel"}
            continue
        missing = _channel_missing_config(channel, config)
        if missing:
            results[channel] = {"ok": False, "error": missing}
            continue
        try:
            await sender(config, message)
            results[channel] = {"ok": True, "error": None}
        except Exception as e:
            results[channel] = {"ok": False, "error": str(e)}
    return results
