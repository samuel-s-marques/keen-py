# Notifications

Keen can alert you when a [job](jobs.md) -- a module run, Magic Chain, or playbook -- finishes, without you having to watch the terminal or the Web UI. Notifications are dispatched over Telegram, Discord, Slack, and email.

Sending a notification is always best-effort: a misconfigured or unreachable channel is logged and skipped, it never fails the run it's reporting on.

## Enabling channels

Channel secrets (bot tokens, webhook URLs, SMTP credentials) are stored the same encrypted way as module API keys, via [`api_keys set`](api_keys_management.md) -- they require the key manager to be unlocked to be read back.

```
keen > api_keys set telegram_bot_token <your-bot-token>
keen > api_keys set discord_webhook_url <your-discord-webhook-url>
keen > api_keys set slack_webhook_url <your-slack-webhook-url>
keen > api_keys set smtp_username <your-smtp-username>
keen > api_keys set smtp_password <your-smtp-password>
```

Non-secret settings (chat IDs, SMTP host/port/addresses) and the list of enabled channels are ordinary preferences:

```
keen > pref set notify_channels "telegram,discord"
keen > pref set telegram_chat_id <your-chat-id>
keen > pref set smtp_host smtp.example.com
keen > pref set smtp_port 587
keen > pref set smtp_from keen@example.com
keen > pref set smtp_to you@example.com
```

`notify_channels` is a comma-separated subset of `telegram`, `discord`, `slack`, `email`. It defaults to empty -- notifications are off until you opt in.

## When you get notified

Two more preferences control *which* job outcomes trigger a notification:

- `notify_on_job_failure` (default `true`): notify whenever a job fails.
- `notify_on_job_complete` (default `false`): notify on every successful completion, not just failures.
- `notify_min_duration_seconds` (default `300`): even with `notify_on_job_complete` left `false`, a successful job that ran at least this long still notifies -- so a quick WHOIS lookup stays silent, but a 20-minute subdomain sweep still lets you know it's done.

```
keen > pref set notify_on_job_failure true
keen > pref set notify_on_job_complete false
keen > pref set notify_min_duration_seconds 600
```

## What a notification looks like

```
[Keen] Job completed: discovery/subdomain_enum on 'example.com'
Workspace: John Doe
Nodes added: 42 | Edges added: 41
Duration: 612s
```

A failed job includes the error message instead:

```
[Keen] Job failed: discovery/subdomain_enum on 'example.com'
Workspace: John Doe
Nodes added: 0 | Edges added: 0
Error: Connection timed out
```
