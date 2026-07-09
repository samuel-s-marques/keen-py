/*
 * Config settings (API keys, preferences, AI) + AI thinking-partner suggestions
 * and server status monitoring.
 */
import {
    apiKeysList,
    moduleSelect,
    moduleForm,
    prefExtractionMode,
    prefMagicEnabled,
    prefMagicMaxDepth,
    prefMagicInteractive,
    prefMagicExcludeModules,
    prefAiEnabled,
    prefAiProvider,
    prefAiModel,
    prefAiBaseUrl,
    prefAiApiKey,
    suggestionsList,
    statusIndicator,
    statusText,
} from "./dom.js";
import { fetchProxies } from "./proxies.js";
import { showSnackbar } from "./notifications.js";

export async function fetchApiKeys() {
    if (!KeenStore.isConfigUnlocked) return;
    const res = await KeenAPI.get(`/config/keys`);
    if (res.ok) {
        const keys = await res.json();
        KeenStore.configKeys = {};
        apiKeysList.innerHTML = keys.length ? '' : 'No keys configured.';
        keys.forEach(k => {
            KeenStore.configKeys[k.service] = k.api_key;
            const div = document.createElement('div');
            div.style.marginBottom = '8px';
            div.style.display = 'flex';
            div.style.justifyContent = 'space-between';
            div.style.alignItems = 'center';
            div.innerHTML = `
                <div><strong>${k.service}</strong>: <span style="font-family:var(--font-mono)">${k.api_key.substring(0, 4)}...</span></div>
                <button class="icon-btn" style="color:var(--text-secondary); padding: 4px;" title="Edit">
                    <i class="fa-solid fa-pen"></i>
                </button>
            `;
            const editBtn = div.querySelector('button');
            editBtn.onclick = () => {
                document.getElementById('input-api-service').value = k.service;
                document.getElementById('input-api-key').value = k.api_key;
            };
            apiKeysList.appendChild(div);
        });
        // Re-render form if a module is selected to auto-inject keys
        if (moduleSelect.value) {
            moduleSelect.dispatchEvent(new Event('change'));
        }
    }
    // Also fetch preferences
    fetchPreferences();
}

export async function fetchPreferences() {
    const res = await KeenAPI.get(`/config/preferences`);
    if (res.ok) {
        const prefs = await res.json();
        if (prefs.extraction_mode) {
            prefExtractionMode.value = prefs.extraction_mode;
        }
        if (prefMagicEnabled) {
            prefMagicEnabled.checked = prefs.magic_enabled === 'true';
        }
        if (prefMagicMaxDepth) {
            prefMagicMaxDepth.value = prefs.magic_max_depth || '2';
        }
        if (prefMagicInteractive) {
            prefMagicInteractive.checked = prefs.magic_interactive === 'true';
        }
        if (prefMagicExcludeModules) {
            prefMagicExcludeModules.value = prefs.magic_exclude_modules || '';
        }

        // Load Proxy settings into the UI
        const proxyEnabled = prefs.proxy_enabled === 'true';
        const proxyMode = prefs.proxy_rotation_mode || 'round-robin';

        const toggleProxyRouting = document.getElementById('toggle-proxy-routing');
        const selectProxyRotation = document.getElementById('select-proxy-rotation');
        const proxyStatusVal = document.getElementById('proxy-status-val');
        const proxyModeVal = document.getElementById('proxy-mode-val');

        if (toggleProxyRouting) {
            toggleProxyRouting.checked = proxyEnabled;
        }
        if (selectProxyRotation) {
            selectProxyRotation.value = proxyMode;
        }
        if (proxyStatusVal) {
            proxyStatusVal.textContent = proxyEnabled ? 'Enabled' : 'Disabled';
            proxyStatusVal.style.color = proxyEnabled ? 'var(--success)' : 'var(--error)';
        }
        if (proxyModeVal) {
            proxyModeVal.textContent = proxyMode;
        }

        // Also reload the proxy table contents
        fetchProxies();
    }
}

export async function loadAISettings() {
    try {
        const res = await KeenAPI.get(`/config/preferences`);
        if (res.ok) {
            const prefs = await res.json();
            if (prefAiEnabled) prefAiEnabled.checked = prefs.llm_thinking_partner_enabled === 'true';
            if (prefAiProvider) {
                prefAiProvider.value = prefs.llm_provider || 'openai';
                prefAiProvider.dispatchEvent(new Event('change'));
            }
            if (prefAiModel) prefAiModel.value = prefs.llm_model || 'gpt-4o';
            if (prefAiBaseUrl) prefAiBaseUrl.value = prefs.llm_base_url || '';

            const prefAiExportEnabled = document.getElementById('pref-ai-export-enabled');
            if (prefAiExportEnabled) {
                prefAiExportEnabled.checked = prefs.llm_export_suggestions_enabled === 'true';
            }

            const prefAiExportAnalysisEnabled = document.getElementById('pref-ai-export-analysis-enabled');
            if (prefAiExportAnalysisEnabled) {
                prefAiExportAnalysisEnabled.checked = prefs.llm_export_analysis_enabled === 'true';
            }
        }

        // Load API key if config is unlocked
        if (KeenStore.isConfigUnlocked && prefAiProvider && prefAiApiKey) {
            const provider = prefAiProvider.value.toLowerCase();
            const keysRes = await KeenAPI.get(`/config/keys`);
            if (keysRes.ok) {
                const keys = await keysRes.json();
                const matchingKey = keys.find(k => k.service.toLowerCase() === provider);
                if (matchingKey) {
                    prefAiApiKey.value = matchingKey.api_key;
                } else {
                    prefAiApiKey.value = '';
                }
            }
        }
    } catch (err) {
        console.error('Failed to load AI settings', err);
    }
}

export async function pollAISuggestionsStatus(workspaceName) {
    if (!workspaceName) return;

    if (KeenStore.aiPollingInterval) {
        clearInterval(KeenStore.aiPollingInterval);
        KeenStore.aiPollingInterval = null;
    }

    const pulseDot = document.getElementById('partner-tab-pulse');
    const logsContainer = document.getElementById('partner-logs-container');
    const logsBody = document.getElementById('partner-logs-body');

    let consecutiveErrors = 0;

    const checkStatus = async () => {
        if (KeenStore.activeWorkspace !== workspaceName) {
            if (KeenStore.aiPollingInterval) {
                clearInterval(KeenStore.aiPollingInterval);
                KeenStore.aiPollingInterval = null;
            }
            if (pulseDot) pulseDot.classList.add('hidden');
            return;
        }

        try {
            const res = await KeenAPI.get(`/workspaces/${workspaceName}/suggestions/status`);
            if (res.ok) {
                consecutiveErrors = 0;
                const statusData = await res.json();

                if (statusData.is_generating) {
                    if (pulseDot) pulseDot.classList.remove('hidden');
                    if (logsContainer) logsContainer.style.display = 'flex';
                }

                if (logsBody && statusData.logs) {
                    logsBody.innerHTML = statusData.logs.map(line => {
                        let typeClass = '';
                        const lower = line.toLowerCase();
                        if (lower.includes('error')) typeClass = 'error';
                        else if (lower.includes('warn')) typeClass = 'warning';
                        else if (lower.includes('complete') || lower.includes('success')) typeClass = 'success';
                        return `<div class="log-line ${typeClass}">${line}</div>`;
                    }).join('');
                    logsBody.scrollTop = logsBody.scrollHeight;
                }

                if (!statusData.is_generating) {
                    if (KeenStore.aiPollingInterval) {
                        clearInterval(KeenStore.aiPollingInterval);
                        KeenStore.aiPollingInterval = null;
                    }
                    if (pulseDot) pulseDot.classList.add('hidden');

                    loadSuggestions();

                    setTimeout(() => {
                        if (!KeenStore.aiPollingInterval && logsContainer && KeenStore.activeWorkspace === workspaceName) {
                            logsContainer.style.display = 'none';
                        }
                    }, 5000);
                }
            } else {
                consecutiveErrors++;
            }
        } catch (err) {
            console.error('Error polling AI status', err);
            consecutiveErrors++;
        }

        if (consecutiveErrors > 5) {
            if (KeenStore.aiPollingInterval) {
                clearInterval(KeenStore.aiPollingInterval);
                KeenStore.aiPollingInterval = null;
            }
            if (pulseDot) pulseDot.classList.add('hidden');
        }
    };

    await checkStatus();

    if (KeenStore.aiPollingInterval === null) {
        KeenStore.aiPollingInterval = setInterval(checkStatus, 1500);
    }
}

export async function loadSuggestions() {
    if (!KeenStore.activeWorkspace || !suggestionsList) return;

    try {
        const res = await KeenAPI.get(`/workspaces/${KeenStore.activeWorkspace}/suggestions`);
        if (res.ok) {
            const data = await res.json();
            let suggestions = [];
            let latestAnalysis = null;
            if (Array.isArray(data)) {
                suggestions = data;
            } else if (data && typeof data === 'object') {
                suggestions = data.suggestions || [];
                latestAnalysis = data.latest_analysis;
            }

            const analysisContainer = document.getElementById('analysis-summary-container');
            const analysisBody = document.getElementById('analysis-summary-body');
            const analysisModalBody = document.getElementById('analysis-modal-body');
            if (analysisContainer && analysisBody) {
                if (latestAnalysis && latestAnalysis.analysis_text) {
                    const mdHtml = (typeof marked !== 'undefined')
                        ? marked.parse(latestAnalysis.analysis_text)
                        : `<pre>${latestAnalysis.analysis_text}</pre>`;
                    analysisBody.classList.add('md-prose');
                    analysisBody.innerHTML = mdHtml;
                    if (analysisModalBody) analysisModalBody.innerHTML = mdHtml;
                    analysisContainer.style.display = 'block';
                } else {
                    analysisBody.innerHTML = '';
                    if (analysisModalBody) analysisModalBody.innerHTML = '';
                    analysisContainer.style.display = 'none';
                }
            }

            renderSuggestions(suggestions);
        }
    } catch (err) {
        console.error('Failed to load suggestions', err);
    }
}

export function renderSuggestions(suggestions) {
    if (!suggestionsList) return;
    suggestionsList.innerHTML = '';

    // Filter out dismissed suggestions, only show pending/accepted/rejected
    const activeSuggestions = suggestions.filter(s => s.status !== 'dismissed');

    if (activeSuggestions.length === 0) {
        suggestionsList.innerHTML = `
            <div style="color: var(--text-secondary); text-align: center; margin-top: 20px;">
                No suggestions yet. Click "Analyze" or run modules to generate insights.
            </div>
        `;
        return;
    }

    activeSuggestions.forEach(s => {
        const card = document.createElement('div');
        card.className = `suggestion-card ${s.status}`;
        card.dataset.id = s.id;

        // Gather context badges
        let badgesHtml = '';
        if (s.context_nodes && s.context_nodes.length) {
            s.context_nodes.forEach(nodeVal => {
                let displayVal = nodeVal;
                if (nodeVal && typeof nodeVal === 'object') {
                    displayVal = nodeVal.value || nodeVal.id || nodeVal.label || JSON.stringify(nodeVal);
                }
                badgesHtml += `<span class="suggestion-badge node-context"><i class="fa-solid fa-circle-nodes"></i> ${displayVal}</span>`;
            });
        }
        if (s.pivot_type === 'run_module' && s.module_name) {
            badgesHtml += `<span class="suggestion-badge pivot-action"><i class="fa-solid fa-bolt"></i> ${s.module_name.split('/').pop()}</span>`;
        } else if (s.pivot_type) {
            badgesHtml += `<span class="suggestion-badge pivot-action"><i class="fa-solid fa-magnifying-glass"></i> ${s.pivot_type}</span>`;
        }

        let actionsHtml = '';
        if (s.status === 'pending') {
            actionsHtml = `
                <div class="suggestion-actions">
                    <button class="suggestion-btn dismiss-btn" title="Dismiss"><i class="fa-solid fa-eye-slash"></i> Dismiss</button>
                    <button class="suggestion-btn feedback-btn" title="Add Feedback Details"><i class="fa-solid fa-comment"></i> Feedback</button>
                    ${s.pivot_type === 'run_module' ? `<button class="suggestion-btn accept-btn" title="Accept and Pivot"><i class="fa-solid fa-circle-play"></i> Pivot</button>` : ''}
                </div>
            `;
        } else {
            actionsHtml = `
                <div style="font-size:0.72rem; color:var(--text-secondary); text-align:right; margin-top:6px; font-style:italic;">
                    Status: ${(s.status || 'pending').toUpperCase()} ${s.feedback ? `(${s.feedback})` : ''}
                </div>
            `;
        }

        card.innerHTML = `
            <div class="suggestion-text">${s.suggestion_text}</div>
            <div class="suggestion-meta">${badgesHtml}</div>
            ${actionsHtml}
            <div class="feedback-container" style="display: none;">
                <textarea class="feedback-textarea" placeholder="Why accept or reject? (e.g., 'Sherlock is perfect here')"></textarea>
                <div style="display: flex; justify-content: flex-end; gap: 6px;">
                    <button class="suggestion-btn reject-submit" style="color: var(--error); border-color: rgba(255,23,68,0.3);"><i class="fa-solid fa-thumbs-down"></i> Reject</button>
                    <button class="suggestion-btn accept-submit" style="color: var(--success); border-color: rgba(0,230,118,0.3);"><i class="fa-solid fa-thumbs-up"></i> Accept</button>
                </div>
            </div>
        `;

        // Bind card button actions
        const pivotBtn = card.querySelector('.accept-btn');
        const dismissBtn = card.querySelector('.dismiss-btn');
        const feedbackToggleBtn = card.querySelector('.feedback-btn');
        const feedbackContainer = card.querySelector('.feedback-container');
        const textarea = card.querySelector('.feedback-textarea');

        if (pivotBtn) {
            pivotBtn.onclick = () => {
                const modName = s.module_name;
                const options = s.module_options || {};

                if (modName && KeenStore.modulesData[modName]) {
                    // Switch tab to Runner
                    const runnerTab = document.querySelector('.right-tab[data-target="tab-module-runner"]');
                    if (runnerTab) runnerTab.click();

                    // Select module
                    moduleSelect.value = modName;
                    moduleSelect.dispatchEvent(new Event('change'));

                    // Pre-fill options
                    setTimeout(() => {
                        for (const [optKey, optVal] of Object.entries(options)) {
                            const input = moduleForm.querySelector(`[name="${optKey}"]`);
                            if (input) {
                                input.value = optVal;
                                input.style.borderColor = 'var(--accent-cyan)';
                                input.style.boxShadow = '0 0 8px rgba(0, 240, 255, 0.2)';
                            }
                        }
                    }, 100);

                    submitFeedback(s.id, 'accepted', 'Pivoted to suggested module');
                }
            };
        }

        if (dismissBtn) {
            dismissBtn.onclick = () => {
                submitFeedback(s.id, 'dismissed', '');
            };
        }

        if (feedbackToggleBtn && feedbackContainer) {
            feedbackToggleBtn.onclick = () => {
                const isHidden = feedbackContainer.style.display === 'none';
                feedbackContainer.style.display = isHidden ? 'flex' : 'none';
            };
        }

        const acceptSubmit = card.querySelector('.accept-submit');
        const rejectSubmit = card.querySelector('.reject-submit');

        if (acceptSubmit && textarea) {
            acceptSubmit.onclick = () => {
                submitFeedback(s.id, 'accepted', textarea.value.trim());
            };
        }

        if (rejectSubmit && textarea) {
            rejectSubmit.onclick = () => {
                submitFeedback(s.id, 'rejected', textarea.value.trim());
            };
        }

        suggestionsList.appendChild(card);
    });
}

export async function submitFeedback(suggestionId, status, feedbackText) {
    if (!KeenStore.activeWorkspace) return;
    try {
        const res = await KeenAPI.post(`/workspaces/${KeenStore.activeWorkspace}/suggestions/${suggestionId}/feedback`, { status, feedback: feedbackText });
        if (res.ok) {
            if (status === 'dismissed') {
                showSnackbar("AI Suggestions", "Suggestion dismissed.", "info", 2000);
            } else {
                showSnackbar("AI Suggestions", `Suggestion marked as ${status.toUpperCase()}.`, "success", 3000);
            }
            loadSuggestions();
        } else {
            const err = await res.json();
            showSnackbar("AI Suggestions", `Failed to submit feedback: ${err.error || 'Unknown error'}`, "error", 5000);
        }
    } catch (err) {
        console.error('Failed to submit feedback', err);
        showSnackbar("AI Suggestions", "Failed to submit feedback. Network error.", "error", 5000);
    }
}

export async function checkServerStatus() {
    try {
        const res = await KeenAPI.get(`/health`);
        if (res.ok) {
            if (statusIndicator && !statusIndicator.classList.contains('online')) {
                statusIndicator.className = 'status-indicator online';
                if (statusText) statusText.textContent = 'Server Online';
            }
        } else {
            throw new Error('Server returned non-ok status');
        }
    } catch (e) {
        if (statusIndicator && !statusIndicator.classList.contains('offline')) {
            statusIndicator.className = 'status-indicator offline';
            if (statusText) statusText.textContent = 'Server Offline';
        }
    }
}
