/*
 * Integrations settings: Telegram/Discord/Slack/Email notification channels.
 *
 * Channel secrets (bot token, webhook URLs, SMTP credentials) are stored via
 * the same encrypted API-key store as module keys -- but with fixed, lowercase
 * service names the backend (src/utils/notifications.py) looks up exactly,
 * unlike the generic "Add API Key" field elsewhere in Settings which
 * uppercases whatever the user types. Never route these through that field.
 */
import { showSnackbar } from "./notifications.js";

const CHANNEL_KEYS = ['telegram', 'discord', 'slack', 'email'];

export async function fetchIntegrationSettings() {
    try {
        const res = await KeenAPI.get(`/config/preferences`);
        if (res.ok) {
            const prefs = await res.json();
            const enabled = (prefs.notify_channels || '').split(',').map(c => c.trim()).filter(Boolean);

            setChecked('integration-enable-telegram', enabled.includes('telegram'));
            setChecked('integration-enable-discord', enabled.includes('discord'));
            setChecked('integration-enable-slack', enabled.includes('slack'));
            setChecked('integration-enable-email', enabled.includes('email'));

            setValue('integration-telegram-chat-id', prefs.telegram_chat_id || '');
            setValue('integration-smtp-host', prefs.smtp_host || '');
            setValue('integration-smtp-port', prefs.smtp_port || '587');
            setValue('integration-smtp-from', prefs.smtp_from || '');
            setValue('integration-smtp-to', prefs.smtp_to || '');

            setChecked('integration-notify-on-failure', (prefs.notify_on_job_failure || 'true') === 'true');
            setChecked('integration-notify-on-complete', (prefs.notify_on_job_complete || 'false') === 'true');
            setValue('integration-min-duration', prefs.notify_min_duration_seconds || '300');
        }

        if (KeenStore.isConfigUnlocked) {
            const keysRes = await KeenAPI.get(`/config/keys`);
            if (keysRes.ok) {
                const keys = await keysRes.json();
                const byService = {};
                keys.forEach(k => { byService[k.service] = k.api_key; });

                setValue('integration-telegram-token', byService['telegram_bot_token'] || '');
                setValue('integration-discord-webhook', byService['discord_webhook_url'] || '');
                setValue('integration-slack-webhook', byService['slack_webhook_url'] || '');
                setValue('integration-smtp-username', byService['smtp_username'] || '');
                setValue('integration-smtp-password', byService['smtp_password'] || '');
            }
        }
    } catch (e) {
        console.error('Failed to load integration settings', e);
    }
}

function setChecked(id, checked) {
    const el = document.getElementById(id);
    if (el) el.checked = checked;
}

function setValue(id, value) {
    const el = document.getElementById(id);
    if (el && document.activeElement !== el) el.value = value;
}

function getValue(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
}

function isChecked(id) {
    const el = document.getElementById(id);
    return el ? el.checked : false;
}

async function saveApiKeyIfPresent(service, value) {
    if (!value) return;
    await KeenAPI.post(`/config/keys`, { service, api_key: value });
}

export async function saveIntegrationSettings() {
    const channels = CHANNEL_KEYS.filter(c => isChecked(`integration-enable-${c}`));

    const preferences = {
        notify_channels: channels.join(','),
        telegram_chat_id: getValue('integration-telegram-chat-id'),
        smtp_host: getValue('integration-smtp-host'),
        smtp_port: getValue('integration-smtp-port'),
        smtp_from: getValue('integration-smtp-from'),
        smtp_to: getValue('integration-smtp-to'),
        notify_on_job_failure: String(isChecked('integration-notify-on-failure')),
        notify_on_job_complete: String(isChecked('integration-notify-on-complete')),
        notify_min_duration_seconds: getValue('integration-min-duration') || '300',
    };

    try {
        await KeenAPI.post(`/config/preferences`, preferences);

        if (KeenStore.isConfigUnlocked) {
            await Promise.all([
                saveApiKeyIfPresent('telegram_bot_token', getValue('integration-telegram-token')),
                saveApiKeyIfPresent('discord_webhook_url', getValue('integration-discord-webhook')),
                saveApiKeyIfPresent('slack_webhook_url', getValue('integration-slack-webhook')),
                saveApiKeyIfPresent('smtp_username', getValue('integration-smtp-username')),
                saveApiKeyIfPresent('smtp_password', getValue('integration-smtp-password')),
            ]);
            showSnackbar('Integrations', 'Settings saved.', 'success', 3000);
        } else if (channels.some(c => c === 'telegram' || c === 'discord' || c === 'slack' || c === 'email')) {
            showSnackbar(
                'Integrations',
                'Preferences saved, but secrets (tokens/webhooks/passwords) need the key manager unlocked to be stored.',
                'warning',
                6000
            );
        } else {
            showSnackbar('Integrations', 'Settings saved.', 'success', 3000);
        }
    } catch (e) {
        showSnackbar('Integrations', 'Failed to save integration settings.', 'error', 5000);
    }
}

export async function testIntegrations() {
    const resultsEl = document.getElementById('integration-test-results');
    if (resultsEl) resultsEl.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.8rem;">Sending test notification...</div>';

    try {
        const res = await KeenAPI.post(`/notifications/test`);
        const data = await res.json();
        if (!res.ok || !data.success) {
            showSnackbar('Integrations', 'Failed to run test.', 'error', 4000);
            if (resultsEl) resultsEl.innerHTML = '';
            return;
        }

        const results = data.results || {};
        const channels = Object.keys(results);
        if (!channels.length) {
            if (resultsEl) {
                resultsEl.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.8rem;">No channels enabled -- check a channel above and save first.</div>';
            }
            return;
        }

        if (resultsEl) {
            resultsEl.innerHTML = channels.map(channel => {
                const r = results[channel];
                const cls = r.ok ? 'ok' : 'error';
                const icon = r.ok ? 'fa-check' : 'fa-xmark';
                const detail = r.ok ? 'Sent successfully' : (r.error || 'Failed');
                return `<div class="integration-test-result ${cls}">
                    <span><i class="fa-solid ${icon}"></i> ${channel}</span>
                    <span>${detail}</span>
                </div>`;
            }).join('');
        }
    } catch (e) {
        showSnackbar('Integrations', 'Failed to run test. Network error.', 'error', 5000);
        if (resultsEl) resultsEl.innerHTML = '';
    }
}

export function initIntegrationsListeners() {
    const saveBtn = document.getElementById('btn-save-integrations');
    if (saveBtn) saveBtn.addEventListener('click', saveIntegrationSettings);

    const testBtn = document.getElementById('btn-test-integrations');
    if (testBtn) testBtn.addEventListener('click', testIntegrations);
}
