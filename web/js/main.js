/*
 * Keen SPA entry point. Loaded as a deferred ES module after the api.js and
 * store.js classic singletons. Wires up all top-level event listeners and kicks
 * off the initial data fetches. Feature logic lives in the imported modules.
 */
import {
    btnThemeToggle,
    sidebar,
    rightPanel,
    terminalContainer,
    sidebarResizer,
    rightPanelResizer,
    terminalResizer,
    contextMenu,
    networkCanvas,
    btnNewWs,
    inputWsName,
    inputWsDesc,
    wsNameWarning,
    modalNewWs,
    btnSettings,
    closeModals,
    modalSettings,
    modalRenameWs,
    nodeTypeSelect,
    nodeValueInput,
    nodePropsFields,
    nodePropsContainer,
    modalCreateNode,
    btnAddCustomProp,
    btnConfirmCreateNode,
    btnUnlockSettings,
    inputMasterPassword,
    apiKeysLocked,
    apiKeysUnlocked,
    btnSaveApiKey,
    prefExtractionMode,
    prefMagicEnabled,
    prefMagicMaxDepth,
    prefMagicInteractive,
    prefMagicExcludeModules,
    btnSavePreferences,
    btnCreateWs,
    btnConfirmRenameWs,
    inputRenameWs,
    btnClearTerm,
    terminalBody,
    moduleSelect,
    moduleDetails,
    moduleDesc,
    moduleAuthor,
    moduleVersion,
    moduleForm,
    btnRunModule,
    editNodeIdInput,
    editNodeTypeSelect,
    editNodeValueInput,
    editNodePropsFields,
    btnAddEditNodeProp,
    btnConfirmEditNode,
    editEdgeIdInput,
    editEdgeRelationshipInput,
    editEdgePropsFields,
    btnAddEditEdgeProp,
    btnConfirmEditEdge,
    modalEditNode,
    modalEditEdge,
    btnExportWs,
    exportMenu,
    timelineSlider,
    btnTimelinePlay,
    timelineSpeed,
    prefAiProvider,
    groupAiBaseUrl,
    prefAiEnabled,
    prefAiModel,
    prefAiBaseUrl,
    prefAiApiKey,
    btnSaveAiSettings,
    btnAnalyzeGraph,
    btnTestAiConn,
    btnDetectAiModel,
} from "./dom.js";
import { makeResizable } from "./layout.js";
import { fetchWorkspaces, selectWorkspace, renderWorkspaces } from "./workspaces.js";
import { fetchModules, executeModule } from "./modules.js";
import {
    fetchApiKeys,
    fetchPreferences,
    loadAISettings,
    pollAISuggestionsStatus,
    renderSuggestions,
    checkServerStatus,
} from "./settings.js";
import { fetchProxies, initProxyListeners } from "./proxies.js";
import { initJobsListeners } from "./jobs.js";
import { fetchIntegrationSettings, initIntegrationsListeners } from "./integrations.js";
import { clearWsScopeRows, collectWsScopeRows, initScopeListeners } from "./scope.js";
import { termPrint, showSnackbar, updateSnackbar } from "./notifications.js";
import { addPropertyField, createEditPropField, parseMetaValue } from "./modals.js";
import { toggleTimelinePlay, updateTimelineFilter } from "./timeline.js";
import { renderTables } from "./graph.js";

// Theme setup
const themeIcon = btnThemeToggle ? btnThemeToggle.querySelector('i') : null;
const savedTheme = localStorage.getItem('keen-theme') || 'dark';
if (savedTheme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
    if (themeIcon) {
        themeIcon.className = 'fa-solid fa-moon';
    }
}
btnThemeToggle.addEventListener('click', () => {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    if (currentTheme === 'light') {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('keen-theme', 'dark');
        if (themeIcon) {
            themeIcon.className = 'fa-solid fa-sun';
        }
    } else {
        document.documentElement.setAttribute('data-theme', 'light');
        localStorage.setItem('keen-theme', 'light');
        if (themeIcon) {
            themeIcon.className = 'fa-solid fa-moon';
        }
    }
    if (KeenStore.activeWorkspace) selectWorkspace(KeenStore.activeWorkspace); // Redraw graph to apply theme
});

// --- Layout Resizing System ---
// Load persisted sizes
const savedSidebarWidth = localStorage.getItem('keen-sidebar-width');
const savedRightPanelWidth = localStorage.getItem('keen-right-panel-width');
const savedTerminalHeight = localStorage.getItem('keen-terminal-height');

if (savedSidebarWidth && sidebar) {
    sidebar.style.width = `${savedSidebarWidth}px`;
}
if (savedRightPanelWidth && rightPanel) {
    rightPanel.style.width = `${savedRightPanelWidth}px`;
}
if (savedTerminalHeight && terminalContainer) {
    terminalContainer.style.height = `${savedTerminalHeight}px`;
}

if (sidebarResizer && sidebar) {
    makeResizable(sidebarResizer, sidebar, 'horizontal-right', 220, 450, 'keen-sidebar-width');
}
if (rightPanelResizer && rightPanel) {
    makeResizable(rightPanelResizer, rightPanel, 'horizontal-left', 300, 600, 'keen-right-panel-width');
}
if (terminalResizer && terminalContainer) {
    makeResizable(terminalResizer, terminalContainer, 'vertical-up', 80, 500, 'keen-terminal-height');
}

// Initialize
fetchWorkspaces();
fetchModules();

// Global Click Listener
document.addEventListener('click', (e) => {
    if (!e.target.closest('.context-menu')) {
        contextMenu.classList.add('hidden');
    }
});

// Global Keydown Listener (Escape handling)
document.addEventListener('keydown', function (e) {
    const btnAddEdge = document.getElementById('btn-add-edge');
    if (e.key === 'Escape' && btnAddEdge && btnAddEdge.classList.contains('active')) {
        btnAddEdge.classList.remove('active');
        networkCanvas.style.cursor = 'default';
        if (KeenStore.network) KeenStore.network.disableEditMode();
    }
});

// Modals Handling
btnNewWs.addEventListener('click', () => {
    inputWsName.value = '';
    inputWsDesc.value = '';
    wsNameWarning.style.display = 'none';
    clearWsScopeRows();
    modalNewWs.classList.add('active');
});
btnSettings.addEventListener('click', () => {
    modalSettings.classList.add('active');
    if (KeenStore.isConfigUnlocked) fetchApiKeys();
    fetchPreferences();
    fetchProxies();
    loadAISettings();
    fetchIntegrationSettings();
});

closeModals.forEach(btn => btn.addEventListener('click', () => {
    modalNewWs.classList.remove('active');
    modalSettings.classList.remove('active');
    modalRenameWs.classList.remove('active');
    document.getElementById('modal-create-node').classList.remove('active');
    document.getElementById('modal-edit-node').classList.remove('active');
    document.getElementById('modal-edit-edge').classList.remove('active');
    document.getElementById('modal-job-logs').classList.remove('active');
    document.getElementById('modal-workspace-scope').classList.remove('active');
    wsNameWarning.style.display = 'none';
}));

// Close modal when clicking outside (on the overlay backdrop)
document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.classList.remove('active');
            wsNameWarning.style.display = 'none';
        }
    });
});

inputWsName.addEventListener('input', () => {
    if (inputWsName.value.includes(' ')) {
        wsNameWarning.style.display = 'block';
    } else {
        wsNameWarning.style.display = 'none';
    }
});

// Node Creation Modal
document.getElementById('btn-add-node').addEventListener('click', () => {
    if (!KeenStore.activeWorkspace) {
        alert('Please select a workspace first.');
        return;
    }
    // Reset form
    nodeTypeSelect.value = '';
    nodeValueInput.value = '';
    nodePropsFields.innerHTML = '';
    nodePropsContainer.style.display = 'none';
    modalCreateNode.classList.add('active');
});

nodeTypeSelect.addEventListener('change', () => {
    const selected = nodeTypeSelect.selectedOptions[0];
    const propsStr = selected.dataset.props || '';
    nodePropsFields.innerHTML = '';

    if (propsStr || selected.value === 'custom') {
        nodePropsContainer.style.display = 'block';
        if (propsStr) {
            const props = propsStr.split(',');
            props.forEach(prop => {
                addPropertyField(prop.trim(), '');
            });
        }
    } else {
        nodePropsContainer.style.display = 'none';
    }
});

btnAddCustomProp.addEventListener('click', () => {
    addPropertyField('', '', true);
});

btnConfirmCreateNode.addEventListener('click', async () => {
    const type = nodeTypeSelect.value;
    const value = nodeValueInput.value.trim();
    if (!type || !value) {
        alert('Please select a type and enter a value.');
        return;
    }

    // Gather properties into metadata
    const metadata = {};
    const nameInputs = nodePropsFields.querySelectorAll('.node-prop-name');
    const valInputs = nodePropsFields.querySelectorAll('.node-prop-value');
    nameInputs.forEach((ni, i) => {
        const propName = ni.value.trim();
        const propVal = valInputs[i] ? valInputs[i].value.trim() : '';
        if (propName && propVal) {
            metadata[propName] = propVal;
        }
    });

    try {
        const res = await KeenAPI.post(`/workspaces/${KeenStore.activeWorkspace}/nodes`, { type, value, metadata });
        if (res.ok) {
            modalCreateNode.classList.remove('active');
            selectWorkspace(KeenStore.activeWorkspace);
            termPrint(`Node created: ${value} (${type})`, 'sys-msg');
        } else {
            const err = await res.json();
            alert(`Failed to create node: ${err.error || 'Unknown error'}`);
        }
    } catch (e) {
        alert('Failed to create node. Check server connection.');
    }
});

// Settings API Keys
btnUnlockSettings.addEventListener('click', async () => {
    const password = inputMasterPassword.value;
    const res = await KeenAPI.post(`/config/unlock`, { password });
    if (res.ok) {
        KeenStore.setConfigUnlocked(true);
        // Persist the session token returned by unlock. Used as a bearer
        // token when the server runs with KEEN_REQUIRE_AUTH enabled; harmless
        // otherwise. (window.keenAuthToken is read by future authenticated
        // request helpers.)
        try {
            const data = await res.json();
            if (data && data.token) {
                KeenAPI.setToken(data.token);
            }
        } catch (e) { /* no token in response body */ }
        apiKeysLocked.classList.add('hidden');
        apiKeysUnlocked.classList.remove('hidden');
        inputMasterPassword.value = '';
        fetchApiKeys();
    } else {
        alert('Invalid master password');
    }
});

btnSaveApiKey.addEventListener('click', async () => {
    const service = document.getElementById('input-api-service').value.trim().toUpperCase();
    const api_key = document.getElementById('input-api-key').value.trim();
    if (!service || !api_key) return;

    await KeenAPI.post(`/config/keys`, { service, api_key });
    document.getElementById('input-api-service').value = '';
    document.getElementById('input-api-key').value = '';
    fetchApiKeys();
});

btnSavePreferences.addEventListener('click', async () => {
    const extraction_mode = prefExtractionMode.value;
    const payload = {
        extraction_mode: extraction_mode,
        magic_enabled: String(prefMagicEnabled.checked),
        magic_max_depth: String(prefMagicMaxDepth.value),
        magic_interactive: String(prefMagicInteractive.checked),
        magic_exclude_modules: prefMagicExcludeModules.value.trim()
    };
    await KeenAPI.post(`/config/preferences`, payload);
    alert('Preferences saved!');
});

// Call init listeners when loaded
initProxyListeners();
initJobsListeners();
initIntegrationsListeners();
initScopeListeners();

// Workspace Management
btnCreateWs.addEventListener('click', async () => {
    const name = inputWsName.value.trim();
    const desc = inputWsDesc.value.trim();
    if (!name) return;

    const scope = collectWsScopeRows();

    try {
        const res = await KeenAPI.post(`/workspaces`, { name, description: desc, scope });
        if (res.ok) {
            modalNewWs.classList.remove('active');
            inputWsName.value = '';
            inputWsDesc.value = '';
            wsNameWarning.style.display = 'none';
            clearWsScopeRows();
            await fetchWorkspaces();
            selectWorkspace(name);
        } else {
            const err = await res.json();
            alert(`Failed to create workspace: ${err.detail || err.error || 'Unknown error'}`);
        }
    } catch (e) {
        console.error('Failed to create workspace', e);
    }
});

btnConfirmRenameWs.addEventListener('click', async () => {
    const oldName = inputRenameWs.dataset.oldName;
    const newName = inputRenameWs.value.trim();
    if (!newName || newName === oldName) return;

    const res = await KeenAPI.put(`/workspaces/${oldName}`, { new_name: newName });

    if (res.ok) {
        modalRenameWs.classList.remove('active');
        if (KeenStore.activeWorkspace === oldName) KeenStore.setActiveWorkspace(newName);
        await fetchWorkspaces();
        if (KeenStore.activeWorkspace === newName) selectWorkspace(newName);
    } else {
        alert("Failed to rename workspace. Ensure no other instances are locking it.");
    }
});

// Tabs
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
        const isRightTab = tab.classList.contains('right-tab');
        const tabClass = isRightTab ? '.right-tab' : '.tab:not(.right-tab)';
        const contentClass = isRightTab ? '.right-tab-content' : '.tab-content:not(.right-tab-content)';

        document.querySelectorAll(tabClass).forEach(t => t.classList.remove('active'));
        document.querySelectorAll(contentClass).forEach(c => c.classList.remove('active'));

        tab.classList.add('active');
        document.getElementById(tab.dataset.target).classList.add('active');

        // Redraw network when tab becomes visible
        if (tab.dataset.target === 'tab-graph' && KeenStore.network) {
            KeenStore.network.redraw();
            KeenStore.network.fit();
        }
    });
});

// Settings Tabs
document.querySelectorAll('.settings-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.settings-section').forEach(c => c.classList.remove('active'));

        tab.classList.add('active');
        const target = document.getElementById(tab.dataset.target);
        if (target) target.classList.add('active');
    });
});

// Terminal Clear
btnClearTerm.addEventListener('click', () => {
    terminalBody.innerHTML = '<div class="log-line sys-msg">Terminal cleared.</div>';
});

// Module Selection
moduleSelect.addEventListener('change', (e) => {
    const modName = e.target.value;
    if (!modName || !KeenStore.modulesData[modName]) {
        moduleDetails.classList.add('hidden');
        return;
    }

    const mod = KeenStore.modulesData[modName];
    moduleDesc.textContent = mod.description || 'No description';
    moduleAuthor.textContent = mod.author || 'Unknown';
    moduleVersion.textContent = `v${mod.version || '1.0.0'}`;

    // Build Form
    moduleForm.innerHTML = '';
    if (mod.options) {
        for (const [key, value] of Object.entries(mod.options)) {
            // value is usually [default, required, description, type]
            const isRequired = value[1];
            let defVal = (value[0] !== undefined && value[0] !== null) ? value[0] : '';

            // Auto-pull API keys if unlocked
            if (KeenStore.isConfigUnlocked && KeenStore.configKeys[key.toUpperCase()]) {
                defVal = KeenStore.configKeys[key.toUpperCase()];
            }

            const group = document.createElement('div');
            group.className = 'form-group';

            const label = document.createElement('label');
            label.textContent = `${key} ${isRequired ? '*' : ''}`;
            label.title = value[2] || '';

            const isSecret = key.toUpperCase().includes('KEY') || key.toUpperCase().includes('PASSWORD') || key.toUpperCase().includes('SECRET');
            const type = value[3];

            let input;
            if (type === 'bool' || type === 'boolean') {
                input = document.createElement('select');
                input.name = key;

                const optTrue = document.createElement('option');
                optTrue.value = 'True';
                optTrue.textContent = 'True';

                const optFalse = document.createElement('option');
                optFalse.value = 'False';
                optFalse.textContent = 'False';

                input.appendChild(optTrue);
                input.appendChild(optFalse);

                // Set default value
                const lowerDefVal = String(defVal).toLowerCase();
                if (lowerDefVal === 'true') {
                    input.value = 'True';
                } else {
                    input.value = 'False';
                }
            } else {
                input = document.createElement('input');
                input.type = isSecret ? 'password' : 'text';
                input.name = key;
                // Use 'new-password' and 'one-time-code' to prevent aggressive browser autofill
                input.autocomplete = isSecret ? 'new-password' : 'one-time-code';
                input.value = defVal;
                input.placeholder = value[2] || '';
            }

            group.appendChild(label);
            group.appendChild(input);
            moduleForm.appendChild(group);
        }
    }

    moduleDetails.classList.remove('hidden');
});

btnRunModule.addEventListener('click', () => {
    const modName = moduleSelect.value;
    if (!modName) return;

    // Gather options
    const options = {};
    const formData = new FormData(moduleForm);
    for (const [key, val] of formData.entries()) {
        if (val.trim()) {
            options[key] = val.trim();
        }
    }

    executeModule(modName, options);
});

// Bind search input
document.getElementById('search-workspaces')?.addEventListener('input', renderWorkspaces);

// Bind search inputs
document.getElementById('search-nodes')?.addEventListener('input', renderTables);
document.getElementById('search-edges')?.addEventListener('input', renderTables);

window.addEventListener('keydown', (e) => {
    if (e.key === 'Delete') {
        const activeEl = document.activeElement;
        if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable)) {
            return; // Don't delete nodes when typing
        }
        const btnDelete = document.getElementById('btn-delete-selected');
        if (btnDelete) btnDelete.click();
    }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) {
        const activeEl = document.activeElement;
        if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable)) {
            return; // Don't intercept Ctrl+A in inputs
        }
        if (KeenStore.network && KeenStore.currentNodes.length > 0) {
            e.preventDefault(); // Prevent selecting text on page
            const allNodeIds = KeenStore.currentNodes.map(n => n.id || n.value);
            KeenStore.network.setSelection({ nodes: allNodeIds, edges: [] });
            KeenStore.lastSelection = { nodes: allNodeIds, edges: [] };
            if (KeenStore.network.updateSelectionDisplay) {
                KeenStore.network.updateSelectionDisplay(allNodeIds, []);
            }
        }
    }
});

// --- Node / Edge Editing Handlers ---
if (btnAddEditNodeProp) {
    btnAddEditNodeProp.addEventListener('click', () => {
        createEditPropField(editNodePropsFields, '', '');
    });
}

if (btnAddEditEdgeProp) {
    btnAddEditEdgeProp.addEventListener('click', () => {
        createEditPropField(editEdgePropsFields, '', '');
    });
}

if (btnConfirmEditNode) {
    btnConfirmEditNode.addEventListener('click', async () => {
        const nodeId = editNodeIdInput.value;
        const type = editNodeTypeSelect.value;
        const value = editNodeValueInput.value.trim();

        if (!value) {
            alert('Please enter a value.');
            return;
        }

        const metadata = {};
        const nameInputs = editNodePropsFields.querySelectorAll('.edit-prop-name');
        const valInputs = editNodePropsFields.querySelectorAll('.edit-prop-value');
        nameInputs.forEach((ni, i) => {
            const propName = ni.value.trim();
            const propVal = valInputs[i] ? valInputs[i].value.trim() : '';
            if (propName && propVal) {
                metadata[propName] = parseMetaValue(propVal);
            }
        });

        try {
            const res = await KeenAPI.put(`/workspaces/${KeenStore.activeWorkspace}/nodes/${nodeId}`, { type, value, metadata });
            if (res.ok) {
                modalEditNode.classList.remove('active');
                selectWorkspace(KeenStore.activeWorkspace);
                termPrint(`Node updated: ${value}`, 'sys-msg');
            } else {
                const err = await res.json();
                alert(`Failed to update node: ${err.error || 'Unknown error'}`);
            }
        } catch (e) {
            alert('Failed to update node. Check server connection.');
        }
    });
}

if (btnConfirmEditEdge) {
    btnConfirmEditEdge.addEventListener('click', async () => {
        const edgeId = editEdgeIdInput.value;
        const relationship = editEdgeRelationshipInput.value.trim();

        if (!relationship) {
            alert('Please enter a relationship.');
            return;
        }

        const metadata = {};
        const nameInputs = editEdgePropsFields.querySelectorAll('.edit-prop-name');
        const valInputs = editEdgePropsFields.querySelectorAll('.edit-prop-value');
        nameInputs.forEach((ni, i) => {
            const propName = ni.value.trim();
            const propVal = valInputs[i] ? valInputs[i].value.trim() : '';
            if (propName && propVal) {
                metadata[propName] = parseMetaValue(propVal);
            }
        });

        try {
            const res = await KeenAPI.put(`/workspaces/${KeenStore.activeWorkspace}/edges/${edgeId}`, { relationship, metadata });
            if (res.ok) {
                modalEditEdge.classList.remove('active');
                selectWorkspace(KeenStore.activeWorkspace);
                termPrint(`Edge updated: ${relationship}`, 'sys-msg');
            } else {
                const err = await res.json();
                alert(`Failed to update edge: ${err.error || 'Unknown error'}`);
            }
        } catch (e) {
            alert('Failed to update edge. Check server connection.');
        }
    });
}

// Check on startup and then periodically every 10s
checkServerStatus();
setInterval(checkServerStatus, 10000);

// Periodically refresh the active workspace graph to stream new nodes and edges in real time
// but only when there is an active module run or magic chaining in progress.
setInterval(() => {
    if (KeenStore.activeWorkspace && KeenStore.activeSockets.length > 0) {
        selectWorkspace(KeenStore.activeWorkspace);
    }
}, 2000);

// --- Export Workspace UI Controls ---
if (btnExportWs && exportMenu) {
    btnExportWs.addEventListener('click', (e) => {
        e.stopPropagation();
        exportMenu.classList.toggle('show');
    });

    // Close export menu when clicking outside
    document.addEventListener('click', () => {
        exportMenu.classList.remove('show');
    });

    // Export menu item actions
    exportMenu.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            exportMenu.classList.remove('show');

            if (!KeenStore.activeWorkspace) {
                alert('No active workspace to export.');
                return;
            }

            const format = link.dataset.format;
            const displayName = `Export Workspace (${format.toUpperCase()})`;
            const snackbarId = 'export-' + Date.now();

            showSnackbar(displayName, 'Generating export file...', 'info', 0, snackbarId);

            try {
                const res = await KeenAPI.get(`/workspaces/${KeenStore.activeWorkspace}/export?format=${format}`);
                if (res.ok) {
                    const blob = await res.blob();
                    // Guess filename from headers or default to workspace name
                    let filename = `${KeenStore.activeWorkspace}_export.${format === 'stix2' ? 'json' : format}`;
                    const disposition = res.headers.get('Content-Disposition');
                    if (disposition && disposition.indexOf('attachment') !== -1) {
                        const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
                        const matches = filenameRegex.exec(disposition);
                        if (matches != null && matches[1]) {
                            filename = matches[1].replace(/['"]/g, '');
                        }
                    }

                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.style.display = 'none';
                    a.href = url;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    a.remove();

                    updateSnackbar(snackbarId, displayName, 'Export completed!', 'success', 3000);
                } else {
                    const err = await res.json();
                    updateSnackbar(snackbarId, displayName, `Export failed: ${err.error || 'Unknown error'}`, 'error', 5000);
                }
            } catch (err) {
                console.error('Export error:', err);
                updateSnackbar(snackbarId, displayName, 'Export failed: network error.', 'error', 5000);
            }
        });
    });
}

// --- Event Timeline Event Listeners ---
if (timelineSlider) {
    timelineSlider.addEventListener('input', () => {
        if (KeenStore.isTimelinePlaying) {
            toggleTimelinePlay(false);
        }
        updateTimelineFilter();
    });
}

if (btnTimelinePlay) {
    btnTimelinePlay.addEventListener('click', () => {
        toggleTimelinePlay();
    });
}

if (timelineSpeed) {
    timelineSpeed.addEventListener('change', () => {
        if (KeenStore.isTimelinePlaying) {
            toggleTimelinePlay(false);
            toggleTimelinePlay(true);
        }
    });
}

// --- Analysis Modal ---
window.openAnalysisModal = function () {
    const modal = document.getElementById('analysis-modal');
    const modalBody = document.getElementById('analysis-modal-body');
    const srcBody = document.getElementById('analysis-summary-body');
    if (modal && modalBody && srcBody) {
        modalBody.innerHTML = srcBody.innerHTML;
        modal.style.display = 'flex';
        document.addEventListener('keydown', _closeModalOnEsc);
    }
};
window.closeAnalysisModal = function () {
    const modal = document.getElementById('analysis-modal');
    if (modal) modal.style.display = 'none';
    document.removeEventListener('keydown', _closeModalOnEsc);
};
function _closeModalOnEsc(e) {
    if (e.key === 'Escape') window.closeAnalysisModal();
}
// Close on backdrop click
document.getElementById('analysis-modal')?.addEventListener('click', function (e) {
    if (e.target === this) window.closeAnalysisModal();
});

// --- AI Thinking Partner Logic ---
if (prefAiProvider && groupAiBaseUrl) {
    prefAiProvider.addEventListener('change', () => {
        const provider = prefAiProvider.value;
        if (provider === 'openai' || provider === 'anthropic') {
            groupAiBaseUrl.style.display = 'none';
        } else {
            groupAiBaseUrl.style.display = 'block';
        }
    });
}

if (btnSaveAiSettings) {
    btnSaveAiSettings.addEventListener('click', async () => {
        const enabled = String(prefAiEnabled.checked);
        const provider = prefAiProvider.value;
        const model = prefAiModel.value.trim();
        const baseUrl = prefAiBaseUrl.value.trim();
        const apiKey = prefAiApiKey.value.trim();
        const prefAiExportEnabled = document.getElementById('pref-ai-export-enabled');
        const exportEnabled = String(prefAiExportEnabled ? prefAiExportEnabled.checked : false);
        const prefAiExportAnalysisEnabled = document.getElementById('pref-ai-export-analysis-enabled');
        const exportAnalysisEnabled = String(prefAiExportAnalysisEnabled ? prefAiExportAnalysisEnabled.checked : false);

        btnSaveAiSettings.disabled = true;
        btnSaveAiSettings.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';

        try {
            // Save preferences
            await KeenAPI.post(`/config/preferences`, {
                llm_thinking_partner_enabled: enabled,
                llm_provider: provider,
                llm_model: model,
                llm_base_url: baseUrl,
                llm_export_suggestions_enabled: exportEnabled,
                llm_export_analysis_enabled: exportAnalysisEnabled
            });

            // Save API key if provided and config is unlocked
            if (apiKey && KeenStore.isConfigUnlocked) {
                await KeenAPI.post(`/config/keys`, {
                    service: provider.toLowerCase(),
                    api_key: apiKey
                });
                fetchApiKeys(); // Refresh keys list
            }

            alert('AI Thinking Partner settings saved!');
        } catch (err) {
            console.error('Failed to save AI settings', err);
            alert('Error saving settings.');
        } finally {
            btnSaveAiSettings.disabled = false;
            btnSaveAiSettings.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save AI Settings';
        }
    });
}

if (btnAnalyzeGraph) {
    btnAnalyzeGraph.addEventListener('click', async () => {
        if (!KeenStore.activeWorkspace) {
            alert('Please select a workspace first.');
            return;
        }

        const queryInput = document.getElementById('input-partner-query');
        const userQuery = queryInput ? queryInput.value.trim() : "";

        // Gather selected nodes metadata
        let selectedNodesPayload = [];
        if (KeenStore.lastSelection && KeenStore.lastSelection.nodes && KeenStore.lastSelection.nodes.length > 0 && KeenStore.nodesDataSet) {
            selectedNodesPayload = KeenStore.lastSelection.nodes.map(id => {
                const node = KeenStore.nodesDataSet.get(id);
                if (node) {
                    return {
                        id: node.id,
                        type: node.group,
                        value: node.fullLabel || node.id,
                        metadata: node.metadata || {}
                    };
                }
                return null;
            }).filter(Boolean);
        }

        btnAnalyzeGraph.disabled = true;
        btnAnalyzeGraph.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analyzing...';
        termPrint(`[AI Thinking Partner] Triggering manual graph analysis...`, 'sys-msg');

        if (userQuery) {
            termPrint(`[AI Thinking Partner] User Query: "${userQuery}"`, 'sys-msg');
        }
        if (selectedNodesPayload.length > 0) {
            const nodeVals = selectedNodesPayload.map(n => n.value).join(', ');
            termPrint(`[AI Thinking Partner] Context nodes: [${nodeVals}]`, 'sys-msg');
        }

        // Start polling immediately to show pulsing dot and activity log container
        pollAISuggestionsStatus(KeenStore.activeWorkspace);

        try {
            const payload = {};
            if (userQuery) payload.user_query = userQuery;
            if (selectedNodesPayload.length > 0) payload.selected_nodes = selectedNodesPayload;

            const res = await KeenAPI.post(`/workspaces/${KeenStore.activeWorkspace}/suggestions/generate`, payload);
            if (res.ok) {
                const suggestions = await res.json();
                termPrint(`[AI Thinking Partner] Completed. Generated ${suggestions.length} suggestions.`, 'success');
                if (queryInput) queryInput.value = '';
                renderSuggestions(suggestions);
            } else {
                const err = await res.json();
                termPrint(`[AI Thinking Partner] Error: ${err.error || 'Failed to generate'}`, 'error');
                showSnackbar("AI Thinking Partner", err.error || "Failed to generate suggestions", "error", 6000);
            }
        } catch (err) {
            console.error('Failed to generate suggestions', err);
            termPrint(`[AI Thinking Partner] Network error during analysis.`, 'error');
            showSnackbar("AI Thinking Partner", "Network error during analysis. Check server logs.", "error", 6000);
        } finally {
            btnAnalyzeGraph.disabled = false;
            btnAnalyzeGraph.innerHTML = '<i class="fa-solid fa-sync"></i> Analyze';
        }
    });
}

// Bind Quick Prompts
document.querySelectorAll('.btn-quick-prompt').forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        const promptType = btn.getAttribute('data-prompt');
        const queryInput = document.getElementById('input-partner-query');
        if (!queryInput) return;

        if (promptType === 'Trace selected nodes') {
            if (KeenStore.lastSelection && KeenStore.lastSelection.nodes && KeenStore.lastSelection.nodes.length > 0 && KeenStore.nodesDataSet) {
                const selected = KeenStore.lastSelection.nodes.map(id => KeenStore.nodesDataSet.get(id)).filter(Boolean);
                if (selected.length === 1) {
                    const node = selected[0];
                    const val = node.fullLabel || node.id;
                    const type = node.group;
                    if (type === 'email-addr') {
                        queryInput.value = `What does this email "${val}" connect to across the evidence, including people, domains, and social profiles?`;
                    } else if (type === 'domain-name') {
                        queryInput.value = `What does this domain "${val}" connect to across the evidence, including emails, servers, and subdomains?`;
                    } else if (type === 'phone-number') {
                        queryInput.value = `What does this phone number "${val}" connect to across the evidence, including names, leaks, and geographic details?`;
                    } else {
                        queryInput.value = `What does this node "${val}" connect to across the evidence, including related accounts, domains, and profiles?`;
                    }
                } else if (selected.length > 1) {
                    const vals = selected.map(n => `"${n.fullLabel || n.id}"`).join(', ');
                    queryInput.value = `What do these entities [${vals}] connect to across the evidence, including domains, emails, and profiles?`;
                }
                queryInput.focus();
            } else {
                alert('Please select one or more nodes in the visualizer graph first to trace.');
            }
        } else if (promptType === 'Next best step') {
            queryInput.value = 'What is the next best investigative step to take based on the current evidence?';
            queryInput.focus();
        } else if (promptType === 'Review phone intel') {
            queryInput.value = 'Review all phone number nodes in the evidence and identify any related leaks, links, or carrier info.';
            queryInput.focus();
        } else if (promptType === 'Summarize strongest links') {
            queryInput.value = 'Summarize the strongest correlation links and suspicious patterns found in this workspace.';
            queryInput.focus();
        } else {
            queryInput.value = promptType;
            queryInput.focus();
        }
    });
});

if (btnTestAiConn) {
    btnTestAiConn.addEventListener('click', async () => {
        const provider = prefAiProvider.value;
        const model = prefAiModel.value.trim();
        const baseUrl = prefAiBaseUrl.value.trim();
        const apiKey = prefAiApiKey.value.trim();

        btnTestAiConn.disabled = true;
        btnTestAiConn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Testing...';

        try {
            const res = await KeenAPI.post(`/config/ai/test`, {
                provider,
                model,
                base_url: baseUrl,
                api_key: apiKey
            });
            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    showSnackbar('AI Configuration', 'API Connection Successful!', 'success', 3000);
                } else {
                    showSnackbar('AI Configuration', `API Connection Failed: ${data.error || 'Unknown error'}`, 'error', 6000);
                }
            } else {
                showSnackbar('AI Configuration', `API Connection Failed: Server returned status ${res.status}`, 'error', 6000);
            }
        } catch (err) {
            console.error('Test connection error', err);
            showSnackbar('AI Configuration', 'API Connection Failed: Network error.', 'error', 6000);
        } finally {
            btnTestAiConn.disabled = false;
            btnTestAiConn.innerHTML = '<i class="fa-solid fa-vial"></i> Test API';
        }
    });
}

if (btnDetectAiModel) {
    btnDetectAiModel.addEventListener('click', async () => {
        const provider = prefAiProvider.value;
        const baseUrl = prefAiBaseUrl.value.trim();
        const apiKey = prefAiApiKey.value.trim();

        btnDetectAiModel.disabled = true;
        btnDetectAiModel.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Detecting...';

        try {
            const res = await KeenAPI.post(`/config/ai/detect-models`, {
                provider,
                base_url: baseUrl,
                api_key: apiKey
            });
            if (res.ok) {
                const data = await res.json();
                if (data.success && data.models && data.models.length > 0) {
                    if (data.models.length === 1) {
                        prefAiModel.value = data.models[0];
                        showSnackbar('AI Configuration', `Auto-detected model: ${data.models[0]}`, 'success', 3000);
                    } else {
                        const modelList = data.models.map((m, idx) => `${idx + 1}. ${m}`).join('\n');
                        const choice = prompt(`Select a model number to use:\n\n${modelList}`, "1");
                        if (choice !== null) {
                            const selectedIdx = parseInt(choice, 10) - 1;
                            if (selectedIdx >= 0 && selectedIdx < data.models.length) {
                                prefAiModel.value = data.models[selectedIdx];
                                showSnackbar('AI Configuration', `Set model to: ${data.models[selectedIdx]}`, 'success', 3000);
                            }
                        }
                    }
                } else {
                    showSnackbar('AI Configuration', `Failed to detect models: ${data.error || 'No models found'}`, 'error', 6000);
                }
            } else {
                showSnackbar('AI Configuration', `Failed to detect models: Server returned status ${res.status}`, 'error', 6000);
            }
        } catch (err) {
            console.error('Detect models error', err);
            showSnackbar('AI Configuration', 'Failed to detect models: Network error.', 'error', 6000);
        } finally {
            btnDetectAiModel.disabled = false;
            btnDetectAiModel.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Detect Model';
        }
    });
}
