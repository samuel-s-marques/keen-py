document.addEventListener('DOMContentLoaded', () => {
    // Theme setup
    const btnThemeToggle = document.getElementById('btn-theme-toggle');
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
        if (activeWorkspace) selectWorkspace(activeWorkspace); // Redraw graph to apply theme
    });

    // State
    let activeWorkspace = null;
    let modulesData = {};
    let network = null;
    let nodesDataSet = null;
    let edgesDataSet = null;
    let currentWorkspace = null;
    let lastSelection = { nodes: [], edges: [] };
    let minimap = null;
    let isConfigUnlocked = false;
    let configKeys = {};
    let currentNodes = [];
    let currentEdges = [];
    let activeSockets = [];
    const activeSocketsMap = new Map();
    let currentWorkspaces = [];
    const activeRuns = new Set(); // Tracks "moduleName:targetValue" strings to prevent duplicates

    const NODE_TO_VALIDATOR_MAP = {
        'email-addr': ['email'],
        'email-dst': ['email'],
        'domain-name': ['domain', 'url'],
        'ipv4-addr': ['ip'],
        'ipv6-addr': ['ip'],
        'x-phone-number': ['phone'],
        'phone-number': ['phone'],
        'x-url': ['url'],
        'person': ['name', 'username'],
        'user-account': ['username'],
        'organization': ['name', 'domain'],
    };

    // DOM Elements
    const workspaceList = document.getElementById('workspace-list');
    const activeWorkspaceTitle = document.getElementById('active-workspace-title');
    const countNodes = document.getElementById('count-nodes');
    const countEdges = document.getElementById('count-edges');
    const nodesTbody = document.getElementById('nodes-tbody');
    const edgesTbody = document.getElementById('edges-tbody');

    const networkCanvas = document.getElementById('network-canvas');

    const moduleSelect = document.getElementById('module-select');
    const moduleDetails = document.getElementById('module-details');
    const moduleDesc = document.getElementById('module-description');
    const moduleAuthor = document.getElementById('module-author');
    const moduleVersion = document.getElementById('module-version');
    const moduleForm = document.getElementById('module-form');
    const btnRunModule = document.getElementById('btn-run-module');

    const terminalBody = document.getElementById('terminal-body');
    const btnClearTerm = document.getElementById('btn-clear-term');

    const contextMenu = document.getElementById('context-menu');
    const contextMenuItems = document.getElementById('context-menu-items');

    // Modals
    const modalNewWs = document.getElementById('modal-new-workspace');
    const btnNewWs = document.getElementById('btn-new-workspace');
    const btnCreateWs = document.getElementById('btn-create-ws');
    const inputWsName = document.getElementById('input-ws-name');
    const inputWsDesc = document.getElementById('input-ws-desc');
    const wsNameWarning = document.getElementById('ws-name-warning');

    const modalRenameWs = document.getElementById('modal-rename-workspace');
    const btnConfirmRenameWs = document.getElementById('btn-confirm-rename-ws');
    const inputRenameWs = document.getElementById('input-rename-ws');

    const modalSettings = document.getElementById('modal-settings');
    const btnSettings = document.getElementById('btn-settings');
    const btnUnlockSettings = document.getElementById('btn-unlock-settings');
    const inputMasterPassword = document.getElementById('input-master-password');
    const apiKeysLocked = document.getElementById('api-keys-locked');
    const apiKeysUnlocked = document.getElementById('api-keys-unlocked');
    const btnSaveApiKey = document.getElementById('btn-save-api-key');
    const apiKeysList = document.getElementById('api-keys-list');
    const prefExtractionMode = document.getElementById('pref-extraction-mode');
    const prefMagicEnabled = document.getElementById('pref-magic-enabled');
    const prefMagicMaxDepth = document.getElementById('pref-magic-max-depth');
    const prefMagicInteractive = document.getElementById('pref-magic-interactive');
    const prefMagicExcludeModules = document.getElementById('pref-magic-exclude-modules');
    const btnSavePreferences = document.getElementById('btn-save-preferences');

    const closeModals = document.querySelectorAll('.close-modal');

    // API Base
    const API_BASE = window.location.origin + '/api';
    const WS_BASE = (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + window.location.host + '/ws';

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
            if (network) network.disableEditMode();
        }
    });

    // Modals Handling
    btnNewWs.addEventListener('click', () => {
        inputWsName.value = '';
        inputWsDesc.value = '';
        wsNameWarning.style.display = 'none';
        modalNewWs.classList.add('active');
    });
    btnSettings.addEventListener('click', () => {
        modalSettings.classList.add('active');
        if (isConfigUnlocked) fetchApiKeys();
        fetchPreferences();
        fetchProxies();
    });

    closeModals.forEach(btn => btn.addEventListener('click', () => {
        modalNewWs.classList.remove('active');
        modalSettings.classList.remove('active');
        modalRenameWs.classList.remove('active');
        document.getElementById('modal-create-node').classList.remove('active');
        document.getElementById('modal-edit-node').classList.remove('active');
        document.getElementById('modal-edit-edge').classList.remove('active');
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
    const modalCreateNode = document.getElementById('modal-create-node');
    const nodeTypeSelect = document.getElementById('node-type-select');
    const nodeValueInput = document.getElementById('node-value');
    const nodePropsContainer = document.getElementById('node-props-container');
    const nodePropsFields = document.getElementById('node-props-fields');
    const btnAddCustomProp = document.getElementById('btn-add-custom-prop');
    const btnConfirmCreateNode = document.getElementById('btn-confirm-create-node');

    document.getElementById('btn-add-node').addEventListener('click', () => {
        if (!activeWorkspace) {
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

    function addPropertyField(name = '', value = '', removable = false) {
        const row = document.createElement('div');
        row.style.cssText = 'display: flex; gap: 6px; align-items: center;';
        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.placeholder = 'Property name';
        nameInput.value = name;
        nameInput.style.flex = '1';
        nameInput.className = 'node-prop-name';
        if (name && !removable) nameInput.readOnly = true;

        const valInput = document.createElement('input');
        valInput.type = 'text';
        valInput.placeholder = 'Value';
        valInput.value = value;
        valInput.style.flex = '2';
        valInput.className = 'node-prop-value';

        row.appendChild(nameInput);
        row.appendChild(valInput);

        if (removable || !name) {
            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'icon-btn';
            removeBtn.style.cssText = 'color: var(--error); font-size: 0.85rem; padding: 4px;';
            removeBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
            removeBtn.onclick = () => row.remove();
            row.appendChild(removeBtn);
        }

        nodePropsFields.appendChild(row);
        return row;
    }

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
            const res = await fetch(`${API_BASE}/workspaces/${activeWorkspace}/nodes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type, value, metadata })
            });
            if (res.ok) {
                modalCreateNode.classList.remove('active');
                selectWorkspace(activeWorkspace);
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
        const res = await fetch(`${API_BASE}/config/unlock`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        if (res.ok) {
            isConfigUnlocked = true;
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

        await fetch(`${API_BASE}/config/keys`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ service, api_key })
        });
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
        await fetch(`${API_BASE}/config/preferences`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        alert('Preferences saved!');
    });

    async function fetchApiKeys() {
        if (!isConfigUnlocked) return;
        const res = await fetch(`${API_BASE}/config/keys`);
        if (res.ok) {
            const keys = await res.json();
            configKeys = {};
            apiKeysList.innerHTML = keys.length ? '' : 'No keys configured.';
            keys.forEach(k => {
                configKeys[k.service] = k.api_key;
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

    async function fetchPreferences() {
        const res = await fetch(`${API_BASE}/config/preferences`);
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

    async function fetchProxies() {
        const tbody = document.getElementById('proxies-tbody');
        if (!tbody) return;

        try {
            const res = await fetch(`${API_BASE}/proxies`);
            if (res.ok) {
                const proxies = await res.json();
                tbody.innerHTML = '';

                let onlineCount = 0;
                const totalCount = proxies.length;

                proxies.forEach(p => {
                    const status = p.status || 'unknown';
                    if (status === 'online') onlineCount++;

                    let latencyText = '-';
                    if (p.latency !== -1 && status === 'online') {
                        latencyText = `${Math.round(p.latency * 1000)}ms`;
                    }

                    const maskUrl = (url) => {
                        try {
                            const u = new URL(url);
                            if (u.username || u.password) {
                                return `${u.protocol}//${u.username}:${u.password ? '****' : ''}@${u.host}`;
                            }
                        } catch (e) { }
                        return url;
                    };

                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="word-break: break-all;">${maskUrl(p.url)}</td>
                        <td style="text-align: center;"><span class="status-badge ${status}">${status.toUpperCase()}</span></td>
                        <td style="text-align: right; color: var(--accent-cyan); font-family: var(--font-mono);">${latencyText}</td>
                        <td style="text-align: center;">
                            <input type="checkbox" class="proxy-row-toggle" data-id="${p.id}" ${p.is_enabled === 1 ? 'checked' : ''} style="width: auto; cursor: pointer;">
                        </td>
                        <td style="text-align: center;">
                            <button class="icon-btn btn-delete-proxy" data-id="${p.id}" style="color: var(--error);" title="Delete"><i class="fa-solid fa-trash"></i></button>
                        </td>
                    `;

                    // Row Toggle Event
                    const toggleInput = tr.querySelector('.proxy-row-toggle');
                    toggleInput.addEventListener('change', async (e) => {
                        const is_enabled = e.target.checked;
                        await fetch(`${API_BASE}/proxies/${p.id}/toggle`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ is_enabled })
                        });
                    });

                    // Row Delete Event
                    const delBtn = tr.querySelector('.btn-delete-proxy');
                    delBtn.addEventListener('click', async () => {
                        if (confirm('Delete this proxy?')) {
                            const dRes = await fetch(`${API_BASE}/proxies/${p.id}`, { method: 'DELETE' });
                            if (dRes.ok) {
                                fetchProxies();
                            }
                        }
                    });

                    tbody.appendChild(tr);
                });

                const onlineCountSpan = document.getElementById('proxy-online-count');
                const totalCountSpan = document.getElementById('proxy-total-count');
                if (onlineCountSpan) onlineCountSpan.textContent = onlineCount;
                if (totalCountSpan) totalCountSpan.textContent = totalCount;

                const btnTestProxies = document.getElementById('btn-test-proxies');
                if (btnTestProxies && !btnTestProxies.innerHTML.includes('Testing...')) {
                    btnTestProxies.disabled = (totalCount === 0);
                }
            }
        } catch (err) {
            console.error('Failed to fetch proxies', err);
        }
    }

    // Set up proxy events listeners once settings loads
    function initProxyListeners() {
        const toggleProxyRouting = document.getElementById('toggle-proxy-routing');
        const selectProxyRotation = document.getElementById('select-proxy-rotation');
        const btnAddProxy = document.getElementById('btn-add-proxy');
        const inputProxyUrl = document.getElementById('input-proxy-url');
        const btnTestProxies = document.getElementById('btn-test-proxies');

        if (toggleProxyRouting) {
            toggleProxyRouting.addEventListener('change', async (e) => {
                const checked = e.target.checked;
                await fetch(`${API_BASE}/config/preferences`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ proxy_enabled: String(checked) })
                });
                const proxyStatusVal = document.getElementById('proxy-status-val');
                if (proxyStatusVal) {
                    proxyStatusVal.textContent = checked ? 'Enabled' : 'Disabled';
                    proxyStatusVal.style.color = checked ? 'var(--success)' : 'var(--error)';
                }
            });
        }

        if (selectProxyRotation) {
            selectProxyRotation.addEventListener('change', async (e) => {
                const val = e.target.value;
                await fetch(`${API_BASE}/config/preferences`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ proxy_rotation_mode: val })
                });
                const proxyModeVal = document.getElementById('proxy-mode-val');
                if (proxyModeVal) {
                    proxyModeVal.textContent = val;
                }
            });
        }

        if (btnAddProxy && inputProxyUrl) {
            btnAddProxy.addEventListener('click', async () => {
                const url = inputProxyUrl.value.trim();
                if (!url) return;

                const res = await fetch(`${API_BASE}/proxies`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });
                if (res.ok) {
                    const data = await res.json();
                    if (data.success) {
                        inputProxyUrl.value = '';
                        fetchProxies();
                    } else {
                        alert(data.error || 'Failed to add proxy');
                    }
                }
            });
        }

        if (btnTestProxies) {
            btnTestProxies.addEventListener('click', async () => {
                btnTestProxies.disabled = true;
                btnTestProxies.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Testing...';
                await fetch(`${API_BASE}/proxies/test`, { method: 'POST' });

                // Poll check every 2 seconds for a total of 5 times to update table
                let count = 0;
                const interval = setInterval(async () => {
                    await fetchProxies();
                    count++;
                    if (count >= 5) {
                        clearInterval(interval);
                        // Re-evaluate button disabled state after testing completes
                        const totalCountSpan = document.getElementById('proxy-total-count');
                        const totalCount = totalCountSpan ? parseInt(totalCountSpan.textContent || '0', 10) : 0;
                        btnTestProxies.disabled = (totalCount === 0);
                        btnTestProxies.innerHTML = '<i class="fa-solid fa-play"></i> Test Connectivity';
                    }
                }, 2000);
            });
        }

        // Drag & Drop Bulk upload list
        const dragZone = document.getElementById('proxy-drag-zone');
        const fileInput = document.getElementById('input-proxy-file');

        if (dragZone && fileInput) {
            dragZone.addEventListener('click', () => fileInput.click());

            dragZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dragZone.style.borderColor = 'var(--accent-cyan)';
                dragZone.style.background = 'rgba(0, 240, 255, 0.05)';
            });

            dragZone.addEventListener('dragleave', () => {
                dragZone.style.borderColor = 'var(--border-color)';
                dragZone.style.background = 'rgba(0,0,0,0.2)';
            });

            const uploadFile = async (file) => {
                // Prevent uploading non-TXT files
                if (!file.name.toLowerCase().endsWith('.txt')) {
                    alert('Only .txt files are allowed.');
                    return;
                }

                // Check file MIME type (if present)
                if (file.type && !file.type.startsWith('text/')) {
                    alert('Selected file is not a valid text file.');
                    return;
                }

                const reader = new FileReader();
                reader.onload = async (e) => {
                    const text = e.target.result;

                    // Content-based heuristic check for binary files (e.g., check for null bytes or control characters)
                    if (text.includes('\0') || /[\x00-\x08\x0E-\x1F\x7F]/.test(text)) {
                        alert('Error: The file contains binary data and does not appear to be a real text file.');
                        return;
                    }

                    const res = await fetch(`${API_BASE}/proxies/load`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ content: text })
                    });
                    if (res.ok) {
                        const data = await res.json();
                        alert(`Successfully loaded ${data.loaded} proxies!`);
                        fetchProxies();
                    }
                };
                reader.readAsText(file);
            };

            dragZone.addEventListener('drop', (e) => {
                e.preventDefault();
                dragZone.style.borderColor = 'var(--border-color)';
                dragZone.style.background = 'rgba(0,0,0,0.2)';
                if (e.dataTransfer.files.length) {
                    uploadFile(e.dataTransfer.files[0]);
                }
            });

            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length) {
                    uploadFile(e.target.files[0]);
                }
            });
        }
    }

    // Call init listeners when loaded
    initProxyListeners();

    // Workspace Management
    btnCreateWs.addEventListener('click', async () => {
        const name = inputWsName.value.trim();
        const desc = inputWsDesc.value.trim();
        if (!name) return;

        try {
            const res = await fetch(`${API_BASE}/workspaces`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description: desc })
            });
            if (res.ok) {
                modalNewWs.classList.remove('active');
                inputWsName.value = '';
                inputWsDesc.value = '';
                wsNameWarning.style.display = 'none';
                await fetchWorkspaces();
                selectWorkspace(name);
            }
        } catch (e) {
            console.error('Failed to create workspace', e);
        }
    });

    btnConfirmRenameWs.addEventListener('click', async () => {
        const oldName = inputRenameWs.dataset.oldName;
        const newName = inputRenameWs.value.trim();
        if (!newName || newName === oldName) return;

        const res = await fetch(`${API_BASE}/workspaces/${oldName}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_name: newName })
        });

        if (res.ok) {
            modalRenameWs.classList.remove('active');
            if (activeWorkspace === oldName) activeWorkspace = newName;
            await fetchWorkspaces();
            if (activeWorkspace === newName) selectWorkspace(newName);
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
            if (tab.dataset.target === 'tab-graph' && network) {
                network.redraw();
                network.fit();
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
        if (!modName || !modulesData[modName]) {
            moduleDetails.classList.add('hidden');
            return;
        }

        const mod = modulesData[modName];
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
                if (isConfigUnlocked && configKeys[key.toUpperCase()]) {
                    defVal = configKeys[key.toUpperCase()];
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

    function getRunKey(modName, options) {
        // Try to find the primary target value from options for dedup
        const mod = modulesData[modName];
        let targetValue = '';
        if (mod && mod.options) {
            for (const [key, optMeta] of Object.entries(mod.options)) {
                const validator = optMeta[3];
                if (validator && options[key]) {
                    targetValue = options[key];
                    break;
                }
            }
        }
        // Fallback: if no validator-matched value, use first non-empty option value
        if (!targetValue) {
            for (const val of Object.values(options)) {
                if (val) { targetValue = val; break; }
            }
        }
        return `${modName}:${targetValue}`;
    }

    function getTargetLabel(options, modName) {
        const mod = modulesData[modName];
        if (mod && mod.options) {
            for (const [key, optMeta] of Object.entries(mod.options)) {
                const validator = optMeta[3];
                if (validator && options[key]) {
                    return options[key];
                }
            }
        }
        return null;
    }

    function executeModule(modName, options) {
        const runKey = getRunKey(modName, options);
        const targetLabel = getTargetLabel(options, modName);
        const displayName = formatModuleName(modName, modulesData[modName] || {});

        // Duplicate prevention
        if (activeRuns.has(runKey)) {
            const msg = targetLabel
                ? `Already running on ${targetLabel}`
                : 'Already running';
            showSnackbar(displayName, msg, 'warning', 3000);
            return;
        }

        activeRuns.add(runKey);
        const snackbarId = 'run-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
        const runMsg = targetLabel ? `Running on ${targetLabel}...` : 'Running...';
        showSnackbar(displayName, runMsg, 'info', 0, snackbarId);

        termPrint(`[${modName}] Connecting...`, 'sys-msg');

        const ws = new WebSocket(`${WS_BASE}/modules/${modName}/run`);
        activeSockets.push(ws);
        activeSocketsMap.set(snackbarId, ws);
        let gotResult = false;

        ws.onopen = () => {
            ws.send(JSON.stringify({
                workspace_name: activeWorkspace || "",
                options: options
            }));
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'log') {
                    termPrint(`[${modName}] ${data.message}`);
                } else if (data.type === 'status') {
                    gotResult = true;
                    termPrint(`[${modName}] Completed: ${data.status}`, 'success');
                    updateSnackbar(snackbarId, displayName, 'Completed successfully', 'success', 4000);
                } else if (data.type === 'error') {
                    gotResult = true;
                    termPrint(`[${modName}] Error: ${data.message}`, 'error');
                    updateSnackbar(snackbarId, displayName, `Error: ${data.message}`, 'error', 5000);
                }
            } catch (e) {
                termPrint(`[${modName}] ${event.data}`);
            }
        };

        ws.onclose = () => {
            activeSockets = activeSockets.filter(s => s !== ws);
            activeSocketsMap.delete(snackbarId);
            activeRuns.delete(runKey);
            termPrint(`[${modName}] Connection closed.`, 'sys-msg');

            if (!gotResult) {
                updateSnackbar(snackbarId, displayName, 'Connection closed', 'warning', 4000);
            }

            // Refresh workspace to show new nodes
            if (activeWorkspace) {
                selectWorkspace(activeWorkspace);
            }
        };
    }

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

    // --- Functions ---

    function formatModuleName(key, mod) {
        let cat = mod.category ? mod.category : "Uncategorized";
        cat = cat.charAt(0).toUpperCase() + cat.slice(1);
        cat = cat.replace(/[_-]/g, ' ');
        const name = mod.name ? mod.name.replace(/[_-]/g, ' ') : key;
        return `${cat} - ${name}`;
    }

    function populateNodeInfo(item, isEdge = false) {
        // Populate info tab FIRST — this is the primary action
        try {
            const infoEmpty = document.getElementById('node-info-empty');
            const infoContent = document.getElementById('node-info-content');
            if (infoEmpty && infoContent) {
                infoEmpty.style.display = 'none';
                infoContent.style.display = 'flex';

                let metadataHtml = '';
                if (item.metadata) {
                    try {
                        const meta = typeof item.metadata === 'string' ? JSON.parse(item.metadata) : item.metadata;
                        if (meta && typeof meta === 'object' && Object.keys(meta).length > 0) {
                            for (const [key, val] of Object.entries(meta)) {
                                let displayVal = val;
                                if (val === null || val === undefined) {
                                    displayVal = '<span style="color: var(--text-secondary); font-style: italic;">N/A</span>';
                                } else if (Array.isArray(val)) {
                                    displayVal = val.map(v => `<span class="badge" style="margin-right: 4px;">${v}</span>`).join(' ');
                                } else if (typeof val === 'object') {
                                    displayVal = `<pre style="margin: 0; padding: 6px; background: var(--term-bg); border: 1px solid var(--border-color); border-radius: 4px; overflow-x: auto; font-family: var(--font-mono); font-size: 0.8rem; color: var(--term-color);">${JSON.stringify(val, null, 2)}</pre>`;
                                } else if (typeof val === 'string' && val.startsWith('http')) {
                                    displayVal = `<a href="${val}" target="_blank" style="color: var(--accent-cyan); text-decoration: none;">${val}</a>`;
                                } else {
                                    displayVal = `<span style="word-break: break-all;">${val}</span>`;
                                }
                                metadataHtml += `<div style="margin-bottom: 8px;"><strong style="color: var(--text-primary); text-transform: capitalize;">${key.replace(/_/g, ' ')}:</strong><br/>${displayVal}</div>`;
                            }
                        }
                    } catch (e) {
                        metadataHtml = `<div style="word-break: break-all;">${item.metadata}</div>`;
                    }
                }
                if (!metadataHtml) {
                    metadataHtml = `<div style="color: var(--text-secondary); font-style: italic;">No extra info available for this ${isEdge ? 'edge' : 'node'}.</div>`;
                }

                if (isEdge) {
                    const sourceNode = currentNodes.find(n => n.id === item.source_id) || { value: item.source_id };
                    const targetNode = currentNodes.find(n => n.id === item.target_id) || { value: item.target_id };

                    infoContent.innerHTML = `
                        <div style="font-size: 1.1rem; color: var(--text-primary); font-weight: 600; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                            <span style="word-break: break-all;">${sourceNode.value}</span>
                            <span style="color: var(--text-secondary); font-size: 0.9rem;"><i class="fa-solid fa-arrow-right-long"></i></span>
                            <span style="word-break: break-all;">${targetNode.value}</span>
                        </div>
                        <div style="margin-bottom: 16px;"><span class="badge" style="background: rgba(255, 0, 255, 0.1); color: var(--accent-magenta); border-color: rgba(255, 0, 255, 0.2);">${item.relationship}</span></div>
                        ${metadataHtml}
                    `;
                } else {
                    const displayValue = item.label || item.value;
                    const platformBadge = item.platform ? `<span class="badge" style="margin-left: 6px; background: rgba(171, 71, 188, 0.15); color: #ab47bc; border-color: rgba(171, 71, 188, 0.3);">${item.platform}</span>` : '';
                    infoContent.innerHTML = `
                        <div style="font-size: 1.1rem; color: var(--text-primary); font-weight: 600; margin-bottom: 4px; word-break: break-all;">${displayValue}</div>
                        <div style="margin-bottom: 16px;"><span class="badge">${item.type}</span>${platformBadge}${item.timestamp ? `<span class="badge" style="margin-left: 6px;">${item.timestamp}</span>` : ''}</div>
                        ${metadataHtml}
                    `;
                }

                // Auto-switch to Info tab
                document.querySelectorAll('.right-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.right-tab-content').forEach(c => c.classList.remove('active'));
                const infoTab = document.querySelector('.right-tab[data-target="tab-node-info"]');
                if (infoTab) infoTab.classList.add('active');
                const infoPanel = document.getElementById('tab-node-info');
                if (infoPanel) infoPanel.classList.add('active');
            }
        } catch (err) {
            console.error('Error populating info tab:', err);
        }
    }

    function handleNodeSelection(node) {
        populateNodeInfo(node);

        // Build compatible module dropdown
        // Use clean_value for module execution, platform for filtering
        try {
            const validators = NODE_TO_VALIDATOR_MAP[node.type] || [];
            const prefillValue = node.clean_value || node.value;
            const platform = node.platform || null;
            buildModuleDropdown(validators, prefillValue, platform);
        } catch (err) {
            console.error('Error building module dropdown:', err);
        }
    }

    function runModuleImmediately(modName, node) {
        if (!modName || !modulesData[modName]) return;

        const mod = modulesData[modName];
        const options = {};
        const validators = NODE_TO_VALIDATOR_MAP[node.type] || [];

        if (mod.options) {
            for (const [key, value] of Object.entries(mod.options)) {
                let defVal = (value[0] !== undefined && value[0] !== null) ? value[0] : '';

                // Auto-pull API keys if unlocked
                if (isConfigUnlocked && configKeys[key.toUpperCase()]) {
                    defVal = configKeys[key.toUpperCase()];
                }

                // Check if this option should take the node's value
                const validator = value[3];
                if (validator) {
                    const vals = Array.isArray(validator)
                        ? validator
                        : validator.split(',').map(v => v.trim());
                    if (vals.some(v => validators.includes(v))) {
                        defVal = node.clean_value || node.value;
                    }
                }

                if (defVal !== undefined && defVal !== null && defVal !== '') {
                    options[key] = defVal.toString().trim();
                }
            }
        }

        executeModule(modName, options);
    }

    function buildModuleDropdown(compatibleValidators = [], prefillValue = null, platform = null) {
        moduleSelect.innerHTML = '<option value="" disabled selected>-- Choose a module --</option>';

        const compatGroup = document.createElement('optgroup');
        compatGroup.label = platform ? `${platform.charAt(0).toUpperCase() + platform.slice(1)} Modules` : 'Compatible Modules';

        const allGroup = document.createElement('optgroup');
        allGroup.label = 'All Modules';

        let firstMatch = null;

        for (const key of Object.keys(modulesData).sort()) {
            const mod = modulesData[key];
            let isMatch = false;

            if (compatibleValidators.length > 0 && mod.options) {
                for (const [optName, optValue] of Object.entries(mod.options)) {
                    const validator = optValue[3];
                    if (validator) {
                        const vals = Array.isArray(validator)
                            ? validator
                            : validator.split(',').map(v => v.trim());
                        if (vals.some(v => compatibleValidators.includes(v))) {
                            isMatch = true;
                            break;
                        }
                    }
                }
            }

            // Platform-specific filtering: prioritize modules matching the platform prefix
            if (isMatch && platform) {
                const lowerKey = key.toLowerCase();
                const lowerName = (mod.name || '').toLowerCase();
                const lowerDesc = (mod.description || '').toLowerCase();
                const lowerPlatform = platform.toLowerCase();
                const platformMatch = lowerKey.includes(lowerPlatform) || lowerName.includes(lowerPlatform) || lowerDesc.includes(lowerPlatform);
                // If platform-specific modules exist, mark non-matching ones as general
                if (!platformMatch) {
                    isMatch = 'general';  // Still compatible but not platform-specific
                }
            }

            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = formatModuleName(key, mod);

            if (isMatch === true) {
                // Direct platform match or non-platform compatible
                if (!firstMatch) firstMatch = key;
                compatGroup.appendChild(opt.cloneNode(true));
            } else if (isMatch === 'general') {
                // Compatible but not platform-specific — still add to compat group
                if (!firstMatch) firstMatch = key;
                compatGroup.appendChild(opt.cloneNode(true));
            }
            allGroup.appendChild(opt);
        }

        if (compatGroup.children.length > 0) {
            moduleSelect.appendChild(compatGroup);
        }
        moduleSelect.appendChild(allGroup);

        if (firstMatch && prefillValue) {
            moduleSelect.value = firstMatch;
            moduleSelect.dispatchEvent(new Event('change'));

            setTimeout(() => {
                const inputs = moduleForm.querySelectorAll('input, select');
                for (const input of inputs) {
                    const optVal = modulesData[firstMatch].options[input.name];
                    if (optVal) {
                        const validator = optVal[3];
                        if (validator) {
                            const vals = Array.isArray(validator)
                                ? validator
                                : validator.split(',').map(v => v.trim());
                            if (vals.some(v => compatibleValidators.includes(v))) {
                                input.value = prefillValue;
                            }
                        }
                    }
                }
            }, 50);
        }
    }

    async function fetchWorkspaces() {
        try {
            const res = await fetch(`${API_BASE}/workspaces`);
            const data = await res.json();
            currentWorkspaces = data;
            renderWorkspaces();
        } catch (e) {
            console.error('Failed to fetch workspaces', e);
        }
    }

    function renderWorkspaces() {
        const query = document.getElementById('search-workspaces')?.value.toLowerCase() || '';
        const filteredWorkspaces = currentWorkspaces.filter(w =>
            w.name.toLowerCase().includes(query) ||
            (w.description && w.description.toLowerCase().includes(query))
        );

        workspaceList.innerHTML = '';
        filteredWorkspaces.forEach(w => {
            const item = document.createElement('div');
            item.className = `workspace-item ${w.name === activeWorkspace ? 'active' : ''}`;
            item.onclick = () => selectWorkspace(w.name);

            item.innerHTML = `
                <div class="workspace-header-actions">
                    <div class="workspace-name">${w.name}</div>
                    <div class="workspace-actions">
                        <button class="icon-btn btn-ws-edit" data-name="${w.name}" title="Rename Workspace"><i class="fa-solid fa-pen"></i></button>
                        <button class="icon-btn btn-ws-delete" data-name="${w.name}" title="Delete Workspace" style="color: var(--error);"><i class="fa-solid fa-trash"></i></button>
                    </div>
                </div>
                <div class="workspace-desc">${w.description || 'No description'}</div>
                <div class="workspace-stats">
                    <span class="stat-badge"><i class="fa-solid fa-circle-nodes"></i> ${w.node_count || 0}</span>
                    <span class="stat-badge"><i class="fa-solid fa-link"></i> ${w.edge_count || 0}</span>
                </div>
            `;
            workspaceList.appendChild(item);
        });

        // Bind workspace actions
        document.querySelectorAll('.btn-ws-delete').forEach(btn => {
            btn.onclick = async (e) => {
                e.stopPropagation();
                const wsName = btn.dataset.name;
                if (confirm(`Are you sure you want to delete workspace "${wsName}"? This cannot be undone.`)) {
                    await fetch(`${API_BASE}/workspaces/${wsName}`, { method: 'DELETE' });
                    if (activeWorkspace === wsName) {
                        activeWorkspace = null;
                        activeWorkspaceTitle.textContent = "No Workspace Selected";
                        nodesTbody.innerHTML = '';
                        edgesTbody.innerHTML = '';
                        if (network) network.destroy();
                    }
                    fetchWorkspaces();
                }
            };
        });

        document.querySelectorAll('.btn-ws-edit').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                const wsName = btn.dataset.name;
                inputRenameWs.value = wsName;
                inputRenameWs.dataset.oldName = wsName;
                modalRenameWs.classList.add('active');
            };
        });
    }

    // Bind search input
    document.getElementById('search-workspaces')?.addEventListener('input', renderWorkspaces);

    async function fetchModules() {
        try {
            const res = await fetch(`${API_BASE}/modules`);
            modulesData = await res.json();
            buildModuleDropdown();
        } catch (e) {
            console.error('Failed to fetch modules', e);
        }
    }

    async function selectWorkspace(name) {
        activeWorkspace = name;
        activeWorkspaceTitle.textContent = name;

        // Update UI active state
        document.querySelectorAll('.workspace-item').forEach(el => {
            if (el.querySelector('.workspace-name').textContent === name) el.classList.add('active');
            else el.classList.remove('active');
        });

        // Load nodes and edges
        try {
            const [nodesRes, edgesRes] = await Promise.all([
                fetch(`${API_BASE}/workspaces/${name}/nodes`),
                fetch(`${API_BASE}/workspaces/${name}/edges`)
            ]);

            const nodes = await nodesRes.json();
            const edges = await edgesRes.json();
            currentNodes = nodes;
            currentEdges = edges;

            countNodes.textContent = nodes.length || 0;
            countEdges.textContent = edges.length || 0;

            renderTables();

            drawGraph(nodes, edges);

            // Note: we don't call fetchWorkspaces() here anymore to avoid infinite loops, 
            // since fetchWorkspaces recreates DOM elements. Just update stats manually if needed.
        } catch (e) {
            console.error('Failed to load workspace data', e);
        }
    }

    function renderTables() {
        const nodesSearchQuery = document.getElementById('search-nodes')?.value.toLowerCase() || '';
        const edgesSearchQuery = document.getElementById('search-edges')?.value.toLowerCase() || '';

        const filteredNodes = currentNodes.filter(n =>
            n.type.toLowerCase().includes(nodesSearchQuery) ||
            n.value.toLowerCase().includes(nodesSearchQuery) ||
            (n.timestamp && n.timestamp.toLowerCase().includes(nodesSearchQuery))
        );

        nodesTbody.innerHTML = '';
        if (filteredNodes.length) {
            filteredNodes.forEach(n => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><span class="badge">${n.type}</span></td>
                    <td>${n.label || n.value}${n.platform ? ' <span class="badge" style="font-size:0.7rem; background:rgba(171,71,188,0.15); color:#ab47bc; border-color:rgba(171,71,188,0.3);">' + n.platform + '</span>' : ''}</td>
                    <td style="color:var(--text-secondary);font-size:0.8rem">${n.timestamp}</td>
                `;
                tr.onclick = () => {
                    handleNodeSelection(n);
                    if (network) {
                        network.setSelection({ nodes: [n.id || n.value], edges: [] });
                        network.focus(n.id || n.value, { animation: true });
                    }
                };
                nodesTbody.appendChild(tr);
            });
        } else {
            nodesTbody.innerHTML = '<tr><td colspan="3">No nodes found.</td></tr>';
        }

        const filteredEdges = currentEdges.filter(e =>
            String(e.source_id).toLowerCase().includes(edgesSearchQuery) ||
            String(e.target_id).toLowerCase().includes(edgesSearchQuery) ||
            String(e.relationship).toLowerCase().includes(edgesSearchQuery)
        );

        edgesTbody.innerHTML = '';
        if (filteredEdges.length) {
            filteredEdges.forEach(e => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${e.source_id}</td>
                    <td>${e.target_id}</td>
                    <td><span class="badge">${e.relationship}</span></td>
                `;
                tr.onclick = () => {
                    populateNodeInfo(e, true);
                    if (network) {
                        network.setSelection({ nodes: [], edges: [e.id] });
                    }
                };
                edgesTbody.appendChild(tr);
            });
        } else {
            edgesTbody.innerHTML = '<tr><td colspan="3">No edges found.</td></tr>';
        }
    }

    // Bind search inputs
    document.getElementById('search-nodes')?.addEventListener('input', renderTables);
    document.getElementById('search-edges')?.addEventListener('input', renderTables);

    function drawGraph(nodes, edges) {
        let allHavePositions = nodes.length > 0;
        lastSelection = { nodes: [], edges: [] };

        const visNodes = nodes.map(n => {
            let icon = '\uf111'; // fa-circle default
            let color = '#8b92a5';

            if (n.type.includes('email')) { icon = '\uf0e0'; color = '#0072ff'; }
            else if (n.type.includes('domain')) { icon = '\uf0ac'; color = '#00f0ff'; }
            else if (n.type.includes('ip')) { icon = '\uf233'; color = '#ff00ff'; }
            else if (n.type.includes('phone')) { icon = '\uf095'; color = '#00e676'; }
            else if (n.type.includes('person')) { icon = '\uf007'; color = '#ff6f61'; }
            else if (n.type.includes('user-account')) { icon = '\uf2bd'; color = '#ab47bc'; }
            else if (n.type.includes('organization')) { icon = '\uf1ad'; color = '#ffb300'; }
            else if (n.type.includes('url')) { icon = '\uf0c1'; color = '#26c6da'; }
            else if (n.type.includes('breach')) { icon = '\uf071'; color = '#ff5252'; }
            else if (n.type.includes('service')) { icon = '\uf233'; color = '#ffa726'; }

            const fullText = n.label || n.value;
            const shortText = fullText.length > 20 ? fullText.substring(0, 18) + '...' : fullText;

            const visNode = {
                id: n.id || n.value,
                label: shortText,
                title: fullText,
                fullLabel: fullText,
                shortLabel: shortText,
                group: n.type,
                shape: 'icon',
                icon: {
                    face: '"Font Awesome 6 Free"',
                    code: icon,
                    size: 40,
                    color: color,
                    weight: "900"
                },
                font: { color: document.documentElement.getAttribute('data-theme') === 'light' ? '#1a1c23' : '#f0f2f8' }
            };

            if (n.x !== null && n.x !== undefined && n.y !== null && n.y !== undefined) {
                visNode.x = n.x;
                visNode.y = n.y;
            } else {
                allHavePositions = false;
            }

            return visNode;
        });

        const visEdges = edges.map(e => ({
            id: e.id,
            from: e.source_id,
            to: e.target_id,
            label: e.relationship.replace(/[_-]/g, ' '),
            font: { color: document.documentElement.getAttribute('data-theme') === 'light' ? '#1a1c23' : '#8b92a5', size: 10, align: 'middle', strokeWidth: 0 },
            color: { color: document.documentElement.getAttribute('data-theme') === 'light' ? '#1a1c2355' : '#8b92a588' },
            arrows: 'to'
        }));

        const isWorkspaceSwitched = (activeWorkspace !== currentWorkspace);
        currentWorkspace = activeWorkspace;

        if (network && !isWorkspaceSwitched && nodesDataSet && edgesDataSet) {
            // Keep track of which nodes are new to decide if we need to enable physics
            const existingNodeIds = new Set(nodesDataSet.getIds());
            const newNodesWithoutPos = visNodes.filter(n => !existingNodeIds.has(n.id) && (n.x === null || n.x === undefined || n.y === null || n.y === undefined));

            // Synchronize nodes
            const newNodeIds = new Set(visNodes.map(n => n.id));
            const nodeIdsToRemove = nodesDataSet.getIds().filter(id => !newNodeIds.has(id));

            if (nodeIdsToRemove.length > 0) {
                nodesDataSet.remove(nodeIdsToRemove);
            }

            // For updates/adds: use nodesDataSet.update
            if (visNodes.length > 0) {
                nodesDataSet.update(visNodes);
            }

            // Synchronize edges
            const newEdgeIds = new Set(visEdges.map(e => e.id));
            const edgeIdsToRemove = edgesDataSet.getIds().filter(id => !newEdgeIds.has(id));

            if (edgeIdsToRemove.length > 0) {
                edgesDataSet.remove(edgeIdsToRemove);
            }

            if (visEdges.length > 0) {
                edgesDataSet.update(visEdges);
            }

            // If there are new nodes without positions, enable physics so they float in smoothly
            if (newNodesWithoutPos.length > 0) {
                network.setOptions({ physics: { enabled: true } });
                const btnPhy = document.getElementById('btn-toggle-physics');
                if (btnPhy) btnPhy.classList.add('active');
            }

            if (minimap) {
                setTimeout(() => {
                    if (minimap) minimap.fit();
                }, 200);
            }
            return;
        }

        nodesDataSet = new vis.DataSet(visNodes);
        edgesDataSet = new vis.DataSet(visEdges);

        const data = {
            nodes: nodesDataSet,
            edges: edgesDataSet
        };

        const options = {
            edges: { smooth: false },
            layout: { improvedLayout: false },
            physics: {
                enabled: !allHavePositions,
                barnesHut: { gravitationalConstant: -3000 },
                stabilization: { iterations: 150 }
            },
            interaction: { hover: true, multiselect: true },
            manipulation: {
                enabled: false,
                deleteNode: function (data, callback) {
                    if (confirm("Delete selected node(s)? This will also cascade delete any connected edges.")) {
                        const promises = data.nodes.map(id => fetch(`${API_BASE}/workspaces/${activeWorkspace}/nodes/${id}`, { method: 'DELETE' }));
                        Promise.all(promises).then(() => {
                            callback(data);
                            selectWorkspace(activeWorkspace);
                        }).catch(e => {
                            alert("Failed to delete nodes.");
                            callback(null);
                        });
                    } else {
                        callback(null);
                    }
                },
                deleteEdge: function (data, callback) {
                    if (confirm("Delete selected edge(s)?")) {
                        const promises = data.edges.map(id => fetch(`${API_BASE}/workspaces/${activeWorkspace}/edges/${id}`, { method: 'DELETE' }));
                        Promise.all(promises).then(() => {
                            callback(data);
                            selectWorkspace(activeWorkspace);
                        }).catch(e => {
                            alert("Failed to delete edges.");
                            callback(null);
                        });
                    } else {
                        callback(null);
                    }
                },
                addEdge: function (edgeData, callback) {
                    const btnAddEdge = document.getElementById('btn-add-edge');
                    if (btnAddEdge) btnAddEdge.classList.remove('active');
                    networkCanvas.style.cursor = 'default';
                    const rel = prompt("Enter relationship (e.g. resolves-to, belongs-to):");
                    if (rel) {
                        edgeData.label = rel;
                        fetch(`${API_BASE}/workspaces/${activeWorkspace}/edges`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                source_id: String(edgeData.from),
                                target_id: String(edgeData.to),
                                relationship: rel
                            })
                        }).then(res => {
                            if (res.ok) {
                                callback(edgeData);
                                selectWorkspace(activeWorkspace);
                            } else {
                                alert("Failed to save edge.");
                                callback(null);
                            }
                        });
                    } else {
                        callback(null);
                    }
                }
            }
        };



        if (network) {
            network.destroy();
            network = null;
        }
        network = new vis.Network(networkCanvas, data, options);

        // Mini-map implementation
        const minimapCanvas = document.getElementById('minimap-canvas');
        if (minimap) {
            minimap.destroy();
            minimap = null;
        }
        if (minimapCanvas) {
            const minimapOptions = {
                edges: {
                    smooth: false,
                    font: { size: 0 } // Hide edge labels on minimap
                },
                layout: { improvedLayout: false },
                physics: { enabled: false },
                interaction: {
                    dragNodes: false,
                    dragView: false,
                    zoomView: false,
                    hover: false
                }
            };
            minimap = new vis.Network(minimapCanvas, data, minimapOptions);

            setTimeout(() => {
                if (minimap) minimap.fit();
            }, 200);

            minimap.on("afterDrawing", (ctx) => {
                if (!network) return;
                const topLeft = network.DOMtoCanvas({ x: 0, y: 0 });
                const bottomRight = network.DOMtoCanvas({ x: networkCanvas.clientWidth, y: networkCanvas.clientHeight });

                ctx.strokeStyle = "rgba(0, 240, 255, 0.8)";
                ctx.lineWidth = 3;
                ctx.strokeRect(topLeft.x, topLeft.y, bottomRight.x - topLeft.x, bottomRight.y - topLeft.y);
            });

            network.on("afterDrawing", () => {
                if (minimap) minimap.redraw();
            });

            // Interactivity for minimap
            const minimapEl = document.getElementById('graph-minimap');
            if (minimapEl) {
                function handleMinimapAction(e) {
                    if (!minimap || !network) return;
                    const rect = minimapEl.getBoundingClientRect();
                    const x = e.clientX - rect.left;
                    const y = e.clientY - rect.top;

                    // Convert DOM coordinates on the minimap to graph coordinates
                    const graphPos = minimap.DOMtoCanvas({ x, y });

                    // Move the main network to center on this position
                    network.moveTo({
                        position: graphPos,
                        animation: false // Instant move makes it feel fast
                    });
                }

                minimapEl.addEventListener('click', handleMinimapAction);

                let isDraggingMinimap = false;
                minimapEl.addEventListener('mousedown', (e) => {
                    isDraggingMinimap = true;
                    handleMinimapAction(e);
                });
                window.addEventListener('mousemove', (e) => {
                    if (isDraggingMinimap) {
                        handleMinimapAction(e);
                    }
                });
                window.addEventListener('mouseup', () => {
                    isDraggingMinimap = false;
                });
            }
        }

        function savePositions() {
            if (!activeWorkspace || !network) return;
            const positions = network.getPositions();
            const formattedPositions = {};
            for (const [id, pos] of Object.entries(positions)) {
                formattedPositions[id] = { x: pos.x, y: pos.y };
            }
            fetch(`${API_BASE}/workspaces/${activeWorkspace}/nodes/positions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ positions: formattedPositions })
            });
        }

        // Freeze physics once initial stabilization is done to save CPU
        network.once("stabilizationIterationsDone", function () {
            network.setOptions({ physics: { enabled: false } });
            const btnPhy = document.getElementById('btn-toggle-physics');
            if (btnPhy) btnPhy.classList.remove('active');
            savePositions();
        });

        network.on("dragEnd", function () {
            savePositions();
        });

        // Setup Layout & Action Buttons
        const btnForce = document.getElementById('btn-layout-force');
        const btnHierarchical = document.getElementById('btn-layout-hierarchical');
        const btnCircle = document.getElementById('btn-layout-circle');
        const btnPhysics = document.getElementById('btn-toggle-physics');
        const btnAddEdge = document.getElementById('btn-add-edge');
        const btnDeleteSelected = document.getElementById('btn-delete-selected');
        const btnFitScreen = document.getElementById('btn-fit-screen');

        function clearLayoutButtons() {
            btnForce.classList.remove('active');
            btnHierarchical.classList.remove('active');
            btnCircle.classList.remove('active');
        }

        if (btnFitScreen) btnFitScreen.onclick = () => {
            if (network) network.fit();
        };

        if (btnDeleteSelected) btnDeleteSelected.onclick = async () => {
            const selectedNodes = lastSelection ? lastSelection.nodes : [];
            const selectedEdges = lastSelection ? lastSelection.edges : [];

            if (selectedNodes.length === 0 && selectedEdges.length === 0) {
                showSnackbar("Error", "No elements selected.", "error");
                return;
            }

            if (confirm(`Are you sure you want to delete ${selectedNodes.length} node(s) and ${selectedEdges.length} edge(s)?`)) {
                try {
                    const nodePromises = selectedNodes.map(id =>
                        fetch(`${API_BASE}/workspaces/${activeWorkspace}/nodes/${id}`, { method: 'DELETE' })
                    );
                    const edgePromises = selectedEdges.map(id =>
                        fetch(`${API_BASE}/workspaces/${activeWorkspace}/edges/${id}`, { method: 'DELETE' })
                    );

                    await Promise.all([...nodePromises, ...edgePromises]);

                    // Clear selection
                    if (lastSelection) lastSelection = { nodes: [], edges: [] };
                    if (network) network.setSelection({ nodes: [], edges: [] });

                    // Refresh workspace
                    selectWorkspace(activeWorkspace);

                    showSnackbar("Success", "Selected items deleted successfully.", "success");
                } catch (e) {
                    console.error("Failed to delete selected items", e);
                    showSnackbar("Error", "Failed to delete some items.", "error");
                }
            }
        };

        if (btnForce) btnForce.onclick = () => {
            clearLayoutButtons();
            btnForce.classList.add('active');
            network.setOptions({
                layout: { hierarchical: false },
                physics: { enabled: true }
            });
            btnPhysics.classList.add('active');
            network.stabilize();
        };

        if (btnHierarchical) btnHierarchical.onclick = () => {
            clearLayoutButtons();
            btnHierarchical.classList.add('active');
            network.setOptions({
                layout: { hierarchical: { enabled: true, sortMethod: 'directed' } },
                physics: { enabled: false }
            });
            btnPhysics.classList.remove('active');
            setTimeout(savePositions, 500);
        };

        if (btnCircle) btnCircle.onclick = () => {
            clearLayoutButtons();
            btnCircle.classList.add('active');
            network.setOptions({ physics: { enabled: false }, layout: { hierarchical: false } });
            btnPhysics.classList.remove('active');

            const nodeIds = data.nodes.getIds();
            const radius = Math.max(300, nodeIds.length * 15);
            const step = 2 * Math.PI / nodeIds.length;

            const updates = [];
            nodeIds.forEach((id, index) => {
                updates.push({
                    id: id,
                    x: radius * Math.cos(index * step),
                    y: radius * Math.sin(index * step)
                });
            });
            data.nodes.update(updates);
            network.fit();
            setTimeout(savePositions, 500);
        };

        if (btnPhysics) btnPhysics.onclick = () => {
            const isEnabled = btnPhysics.classList.contains('active');
            if (isEnabled) {
                btnPhysics.classList.remove('active');
                network.setOptions({ physics: { enabled: false } });
            } else {
                btnPhysics.classList.add('active');
                network.setOptions({ physics: { enabled: true } });
            }
        };

        if (btnAddEdge) btnAddEdge.onclick = () => {
            if (btnAddEdge.classList.contains('active')) {
                btnAddEdge.classList.remove('active');
                networkCanvas.style.cursor = 'default';
                network.disableEditMode();
            } else {
                btnAddEdge.classList.add('active');
                networkCanvas.style.cursor = 'crosshair';
                network.addEdgeMode();
            }
        };

        network.on('oncontext', function (params) {
            params.event.preventDefault();
            const nodeId = this.getNodeAt(params.pointer.DOM);
            const edgeId = this.getEdgeAt(params.pointer.DOM);

            if (nodeId) {
                const selectedNode = nodes.find(n => n.id === nodeId || n.value === nodeId);
                if (selectedNode) {
                    showContextMenu(params.event.pageX, params.event.pageY, selectedNode, null);
                }
            } else if (edgeId) {
                showContextMenu(params.event.pageX, params.event.pageY, null, edgeId);
            } else {
                contextMenu.classList.add('hidden');
            }
        });

        function updateSelectionDisplay(selectedNodeIds, selectedEdgeIds) {
            const totalSelected = selectedNodeIds.length + selectedEdgeIds.length;
            const infoEmpty = document.getElementById('node-info-empty');
            const infoContent = document.getElementById('node-info-content');

            if (!infoEmpty || !infoContent) return;

            if (totalSelected === 0) {
                infoEmpty.style.display = 'flex';
                infoContent.style.display = 'none';
                moduleSelect.innerHTML = '<option value="" disabled selected>-- Select a node to run modules --</option>';
                moduleDetails.classList.add('hidden');
            } else if (selectedNodeIds.length === 1 && selectedEdgeIds.length === 0) {
                const nodeId = selectedNodeIds[0];
                const selectedNode = nodes.find(n => n.id === nodeId || n.value === nodeId);
                if (selectedNode) {
                    handleNodeSelection(selectedNode);
                }
            } else if (selectedNodeIds.length === 0 && selectedEdgeIds.length === 1) {
                const edgeId = selectedEdgeIds[0];
                const selectedEdge = edges.find(e => e.id === edgeId);
                if (selectedEdge) {
                    populateNodeInfo(selectedEdge, true);
                    moduleSelect.innerHTML = '<option value="" disabled selected>-- Select a node to run modules --</option>';
                    moduleDetails.classList.add('hidden');
                }
            } else {
                // Multi-select
                infoEmpty.style.display = 'none';
                infoContent.style.display = 'flex';

                let html = `<div style="font-size: 1.1rem; color: var(--text-primary); font-weight: 600; margin-bottom: 12px;">Selection Summary</div>`;

                if (selectedNodeIds.length > 0) {
                    html += `<div style="margin-bottom: 8px;"><strong style="color: var(--text-primary);">Nodes (${selectedNodeIds.length}):</strong></div>`;
                    html += `<div style="display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 12px;">`;
                    selectedNodeIds.forEach(id => {
                        const node = nodes.find(n => n.id === id || n.value === id);
                        const val = node ? (node.label || node.value) : id;
                        html += `<span class="badge">${val}</span>`;
                    });
                    html += `</div>`;
                }

                if (selectedEdgeIds.length > 0) {
                    html += `<div style="margin-bottom: 8px;"><strong style="color: var(--text-primary);">Edges (${selectedEdgeIds.length}):</strong></div>`;
                    html += `<div style="display: flex; flex-wrap: wrap; gap: 4px;">`;
                    selectedEdgeIds.forEach(id => {
                        const edge = edges.find(e => e.id === id);
                        const rel = edge ? edge.relationship : id;
                        html += `<span class="badge" style="background: rgba(255, 0, 255, 0.1); color: var(--accent-magenta); border-color: rgba(255, 0, 255, 0.2);">${rel}</span>`;
                    });
                    html += `</div>`;
                }

                infoContent.innerHTML = html;

                // Auto-switch to Info tab
                const infoTab = document.querySelector('.right-tab[data-target="tab-node-info"]');
                if (infoTab) infoTab.classList.add('active');
                const infoPanel = document.getElementById('tab-node-info');
                if (infoPanel) infoPanel.classList.add('active');

                moduleSelect.innerHTML = '<option value="" disabled selected>-- Multiple nodes selected --</option>';
                moduleDetails.classList.add('hidden');
            }

            // Update labels for all nodes based on selectedNodeIds
            const allNodes = data.nodes.get();
            const updates = [];
            const isLight = document.documentElement.getAttribute('data-theme') === 'light';

            allNodes.forEach(node => {
                const isSelected = selectedNodeIds.includes(node.id);
                if (isSelected && node.fullLabel && node.label !== node.fullLabel) {
                    updates.push({
                        id: node.id,
                        label: node.fullLabel,
                        font: { color: isLight ? '#1a1c23' : '#f0f2f8', background: isLight ? '#ffffff' : '#111318' }
                    });
                } else if (!isSelected && node.shortLabel && node.label !== node.shortLabel) {
                    updates.push({
                        id: node.id,
                        label: node.shortLabel,
                        font: { color: isLight ? '#1a1c23' : '#f0f2f8', background: 'transparent' }
                    });
                }
            });

            if (updates.length > 0) {
                data.nodes.update(updates);
            }
        }
        network.updateSelectionDisplay = updateSelectionDisplay;

        // Always track the current selection from vis.js (handles both click and drag)
        network.on('select', function (params) {
            lastSelection = { nodes: params.nodes, edges: params.edges };
            updateSelectionDisplay(params.nodes, params.edges);
        });

        network.on('click', function (params) {
            if (btnAddEdge && btnAddEdge.classList.contains('active')) {
                // If user clicks without drawing an edge, abort edge mode
                btnAddEdge.classList.remove('active');
                networkCanvas.style.cursor = 'default';
                network.disableEditMode();
            }

            contextMenu.classList.add('hidden');
        });
    }

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
            if (network && currentNodes.length > 0) {
                e.preventDefault(); // Prevent selecting text on page
                const allNodeIds = currentNodes.map(n => n.id || n.value);
                network.setSelection({ nodes: allNodeIds, edges: [] });
                lastSelection = { nodes: allNodeIds, edges: [] };
                if (network.updateSelectionDisplay) {
                    network.updateSelectionDisplay(allNodeIds, []);
                }
            }
        }
    });

    function showContextMenu(x, y, node, edgeId = null) {
        contextMenuItems.innerHTML = '';

        if (edgeId !== null) {
            const editEdgeItem = document.createElement('div');
            editEdgeItem.className = 'context-menu-item';
            editEdgeItem.innerHTML = `<i class="fa-solid fa-pen"></i> Edit Edge`;
            editEdgeItem.onclick = (e) => {
                e.stopPropagation();
                contextMenu.classList.add('hidden');
                openEditEdgeModal(edgeId);
            };
            contextMenuItems.appendChild(editEdgeItem);

            const deleteEdgeItem = document.createElement('div');
            deleteEdgeItem.className = 'context-menu-item';
            deleteEdgeItem.style.color = 'var(--error)';
            deleteEdgeItem.innerHTML = `<i class="fa-solid fa-trash"></i> Delete Edge`;
            deleteEdgeItem.onclick = (e) => {
                e.stopPropagation();
                contextMenu.classList.add('hidden');
                if (confirm("Delete this edge?")) {
                    fetch(`${API_BASE}/workspaces/${activeWorkspace}/edges/${edgeId}`, { method: 'DELETE' })
                        .then(() => selectWorkspace(activeWorkspace))
                        .catch(() => alert("Failed to delete edge."));
                }
            };
            contextMenuItems.appendChild(deleteEdgeItem);

            contextMenu.style.left = `${x}px`;
            contextMenu.style.top = `${y}px`;
            contextMenu.classList.remove('hidden');
            return;
        }

        const validators = NODE_TO_VALIDATOR_MAP[node.type] || [];

        let found = false;
        const categories = {};

        for (const key of Object.keys(modulesData).sort()) {
            const mod = modulesData[key];
            let isMatch = false;

            if (validators.length > 0 && mod.options) {
                for (const [optName, optValue] of Object.entries(mod.options)) {
                    const validator = optValue[3];
                    if (validator) {
                        const vals = Array.isArray(validator)
                            ? validator
                            : validator.split(',').map(v => v.trim());
                        if (vals.some(v => validators.includes(v))) {
                            isMatch = true;
                            break;
                        }
                    }
                }
            }

            if (isMatch) {
                found = true;
                const cat = mod.category || 'Uncategorized';
                if (!categories[cat]) categories[cat] = [];
                categories[cat].push({ key, mod });
            }
        }

        if (found) {
            for (const cat of Object.keys(categories).sort()) {
                const catItem = document.createElement('div');
                const capitalizedCat = cat.charAt(0).toUpperCase() + cat.slice(1);
                catItem.className = 'context-menu-item has-submenu';
                catItem.innerHTML = `<i class="fa-solid fa-folder"></i> ${capitalizedCat} <i class="fa-solid fa-chevron-right submenu-arrow"></i>`;

                const submenu = document.createElement('div');
                submenu.className = 'submenu';

                categories[cat].forEach(({ key, mod }) => {
                    const item = document.createElement('div');
                    item.className = 'context-menu-item';
                    const shortName = mod.name ? mod.name.replace(/[_-]/g, ' ') : key;
                    item.innerHTML = `<i class="fa-solid fa-play"></i> ${shortName}`;
                    item.onclick = (e) => {
                        e.stopPropagation();
                        contextMenu.classList.add('hidden');
                        populateNodeInfo(node);
                        runModuleImmediately(key, node);
                    };
                    submenu.appendChild(item);
                });

                catItem.appendChild(submenu);
                contextMenuItems.appendChild(catItem);
            }
        }

        if (!found) {
            const empty = document.createElement('div');
            empty.className = 'context-menu-item';
            empty.style.cursor = 'default';
            empty.style.color = 'var(--text-secondary)';
            empty.textContent = 'No compatible modules';
            contextMenuItems.appendChild(empty);
        }

        const magicItem = document.createElement('div');
        magicItem.className = 'context-menu-item';
        magicItem.style.borderTop = '1px solid var(--border-color)';
        magicItem.style.marginTop = '4px';
        magicItem.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles" style="color: var(--accent-cyan);"></i> Magic Chaining`;
        magicItem.onclick = (e) => {
            e.stopPropagation();
            contextMenu.classList.add('hidden');
            runMagicChainingImmediately(node.clean_value || node.value);
        };
        contextMenuItems.appendChild(magicItem);

        const editItem = document.createElement('div');
        editItem.className = 'context-menu-item';
        editItem.style.borderTop = '1px solid var(--border-color)';
        editItem.style.marginTop = '4px';
        editItem.innerHTML = `<i class="fa-solid fa-pen"></i> Edit Node`;
        editItem.onclick = (e) => {
            e.stopPropagation();
            contextMenu.classList.add('hidden');
            openEditNodeModal(node);
        };
        contextMenuItems.appendChild(editItem);

        const deleteItem = document.createElement('div');
        deleteItem.className = 'context-menu-item';
        deleteItem.style.color = 'var(--error)';
        deleteItem.style.marginTop = '4px';
        deleteItem.innerHTML = `<i class="fa-solid fa-trash"></i> Delete Node`;
        deleteItem.onclick = (e) => {
            e.stopPropagation();
            contextMenu.classList.add('hidden');
            if (confirm("Delete this node? This will also cascade delete any connected edges.")) {
                fetch(`${API_BASE}/workspaces/${activeWorkspace}/nodes/${node.id || node.value}`, { method: 'DELETE' })
                    .then(() => selectWorkspace(activeWorkspace))
                    .catch(() => alert("Failed to delete node."));
            }
        };
        contextMenuItems.appendChild(deleteItem);

        contextMenu.style.left = `${x}px`;
        contextMenu.style.top = `${y}px`;
        contextMenu.classList.remove('hidden');
    }

    // --- Node / Edge Editing Handlers ---

    const modalEditNode = document.getElementById('modal-edit-node');
    const editNodeIdInput = document.getElementById('edit-node-id');
    const editNodeTypeSelect = document.getElementById('edit-node-type');
    const editNodeValueInput = document.getElementById('edit-node-value');
    const editNodePropsFields = document.getElementById('edit-node-props-fields');
    const btnAddEditNodeProp = document.getElementById('btn-add-edit-node-prop');
    const btnConfirmEditNode = document.getElementById('btn-confirm-edit-node');

    const modalEditEdge = document.getElementById('modal-edit-edge');
    const editEdgeIdInput = document.getElementById('edit-edge-id');
    const editEdgeRelationshipInput = document.getElementById('edit-edge-relationship');
    const editEdgePropsFields = document.getElementById('edit-edge-props-fields');
    const btnAddEditEdgeProp = document.getElementById('btn-add-edit-edge-prop');
    const btnConfirmEditEdge = document.getElementById('btn-confirm-edit-edge');

    function createEditPropField(container, name = '', value = '') {
        const row = document.createElement('div');
        row.style.cssText = 'display: flex; gap: 6px; align-items: center;';
        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.placeholder = 'Property name';
        nameInput.value = name;
        nameInput.style.flex = '1';
        nameInput.className = 'edit-prop-name';

        const valInput = document.createElement('input');
        valInput.type = 'text';
        valInput.placeholder = 'Value';
        valInput.value = value;
        valInput.style.flex = '2';
        valInput.className = 'edit-prop-value';

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'icon-btn';
        removeBtn.style.cssText = 'color: var(--error); font-size: 0.85rem; padding: 4px;';
        removeBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        removeBtn.onclick = () => row.remove();

        row.appendChild(nameInput);
        row.appendChild(valInput);
        row.appendChild(removeBtn);

        container.appendChild(row);
        return row;
    }

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

    function openEditNodeModal(node) {
        editNodeIdInput.value = node.id || node.value;
        editNodeValueInput.value = node.value;

        // Set type, if not found in select, fallback to custom
        let typeFound = false;
        for (const opt of editNodeTypeSelect.options) {
            if (opt.value === node.type) {
                typeFound = true;
                break;
            }
        }
        if (!typeFound && node.type) {
            const newOpt = document.createElement('option');
            newOpt.value = node.type;
            newOpt.textContent = `Extended (${node.type})`;
            editNodeTypeSelect.appendChild(newOpt);
        }
        editNodeTypeSelect.value = node.type || 'custom';

        editNodePropsFields.innerHTML = '';
        if (node.metadata) {
            try {
                const meta = typeof node.metadata === 'string' ? JSON.parse(node.metadata) : node.metadata;
                if (meta && typeof meta === 'object') {
                    for (const [k, v] of Object.entries(meta)) {
                        createEditPropField(editNodePropsFields, k, typeof v === 'object' ? JSON.stringify(v) : v);
                    }
                }
            } catch (e) {
                // Ignore parsing error
            }
        }
        modalEditNode.classList.add('active');
    }

    function openEditEdgeModal(edgeId) {
        const edge = currentEdges.find(e => e.id === edgeId);
        if (!edge) return;

        editEdgeIdInput.value = edge.id;
        editEdgeRelationshipInput.value = edge.relationship;

        editEdgePropsFields.innerHTML = '';
        if (edge.metadata) {
            try {
                const meta = typeof edge.metadata === 'string' ? JSON.parse(edge.metadata) : edge.metadata;
                if (meta && typeof meta === 'object') {
                    for (const [k, v] of Object.entries(meta)) {
                        createEditPropField(editEdgePropsFields, k, typeof v === 'object' ? JSON.stringify(v) : v);
                    }
                }
            } catch (e) {
                // Ignore parsing error
            }
        }
        modalEditEdge.classList.add('active');
    }

    function parseMetaValue(val) {
        if (val === 'true') return true;
        if (val === 'false') return false;
        if (val === 'null') return null;
        try {
            if (val.startsWith('{') || val.startsWith('[')) {
                return JSON.parse(val);
            }
            if (!isNaN(val) && val !== '') {
                const num = Number(val);
                if (Number.isSafeInteger(num)) {
                    return num;
                }
            }
        } catch (e) {
            // Fallback to string
        }
        return val;
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
                const res = await fetch(`${API_BASE}/workspaces/${activeWorkspace}/nodes/${nodeId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type, value, metadata })
                });
                if (res.ok) {
                    modalEditNode.classList.remove('active');
                    selectWorkspace(activeWorkspace);
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
                const res = await fetch(`${API_BASE}/workspaces/${activeWorkspace}/edges/${edgeId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ relationship, metadata })
                });
                if (res.ok) {
                    modalEditEdge.classList.remove('active');
                    selectWorkspace(activeWorkspace);
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

    function termPrint(text, extraClass = '') {
        let finalClass = extraClass;

        // Auto-detect class based on text content if no explicit success/warning/error class is provided
        if (finalClass !== 'success' && finalClass !== 'warning' && finalClass !== 'error') {
            const lowerText = text.toLowerCase();
            if (lowerText.includes(' | success | ') || lowerText.includes('completed:') || lowerText.includes('success:')) {
                finalClass = 'success';
            } else if (lowerText.includes(' | warning | ') || lowerText.includes(' | warn | ') || lowerText.includes('warning:')) {
                finalClass = 'warning';
            } else if (lowerText.includes(' | error | ') || lowerText.includes(' | critical | ') || lowerText.includes('error:')) {
                finalClass = 'error';
            }
        }

        const line = document.createElement('div');
        line.className = `log-line ${finalClass}`;
        line.textContent = text;
        terminalBody.appendChild(line);
        terminalBody.scrollTop = terminalBody.scrollHeight;
    }

    // --- Snackbar System ---
    const snackbarContainer = document.getElementById('snackbar-container');

    const SNACKBAR_ICONS = {
        info: '<div class="snackbar-spinner"></div>',
        success: '<i class="fa-solid fa-check"></i>',
        error: '<i class="fa-solid fa-xmark"></i>',
        warning: '<i class="fa-solid fa-exclamation"></i>',
    };

    function showSnackbar(title, message, type = 'info', duration = 3000, id = null) {
        const el = document.createElement('div');
        el.className = `snackbar snackbar-${type}`;
        if (id) el.dataset.snackbarId = id;

        // Hide close button if duration is 0 (persistent/running state)
        const closeBtnStyle = duration === 0 ? 'style="display: none;"' : '';
        const cancelBtnStyle = duration === 0 ? 'style="display: block;"' : 'style="display: none;"';

        el.innerHTML = `
            <div class="snackbar-icon">${SNACKBAR_ICONS[type] || SNACKBAR_ICONS.info}</div>
            <div class="snackbar-body">
                <div class="snackbar-title"></div>
                <div class="snackbar-message"></div>
            </div>
            <button class="snackbar-cancel" ${cancelBtnStyle}><i class="fa-solid fa-circle-stop"></i></button>
            <button class="snackbar-close" ${closeBtnStyle}><i class="fa-solid fa-xmark"></i></button>
        `;

        const titleEl = el.querySelector('.snackbar-title');
        if (titleEl) { titleEl.textContent = title; titleEl.title = title; }
        const msgEl = el.querySelector('.snackbar-message');
        if (msgEl) { msgEl.textContent = message; msgEl.title = message; }

        el.querySelector('.snackbar-close').addEventListener('click', () => removeSnackbar(el));

        const cancelBtn = el.querySelector('.snackbar-cancel');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                if (id && activeSocketsMap.has(id)) {
                    const ws = activeSocketsMap.get(id);
                    if (ws) ws.close();
                } else {
                    removeSnackbar(el);
                }
            });
        }

        snackbarContainer.appendChild(el);

        if (duration > 0) {
            el._timeout = setTimeout(() => removeSnackbar(el), duration);
        }

        return el;
    }

    function updateSnackbar(id, title, message, type, duration = 4000) {
        const el = snackbarContainer.querySelector(`[data-snackbar-id="${id}"]`);
        if (!el) {
            // Snackbar was manually closed, just show a new one
            showSnackbar(title, message, type, duration);
            return;
        }

        // Update classes
        el.className = `snackbar snackbar-${type}`;

        // Update icon
        const iconEl = el.querySelector('.snackbar-icon');
        if (iconEl) iconEl.innerHTML = SNACKBAR_ICONS[type] || SNACKBAR_ICONS.info;

        // Update text
        const titleEl = el.querySelector('.snackbar-title');
        if (titleEl) { titleEl.textContent = title; titleEl.title = title; }
        const msgEl = el.querySelector('.snackbar-message');
        if (msgEl) { msgEl.textContent = message; msgEl.title = message; }

        // Update close button visibility: show if duration > 0, hide if 0
        const closeEl = el.querySelector('.snackbar-close');
        if (closeEl) {
            if (duration === 0) {
                closeEl.style.display = 'none';
            } else {
                closeEl.style.display = 'block';
            }
        }

        const cancelEl = el.querySelector('.snackbar-cancel');
        if (cancelEl) {
            if (duration === 0) {
                cancelEl.style.display = 'block';
            } else {
                cancelEl.style.display = 'none';
            }
        }

        // Clear old timeout and set new auto-dismiss
        if (el._timeout) clearTimeout(el._timeout);
        if (duration > 0) {
            el._timeout = setTimeout(() => removeSnackbar(el), duration);
        }
    }

    function removeSnackbar(el) {
        if (!el || !el.parentNode) return;
        if (el._timeout) clearTimeout(el._timeout);
        el.classList.add('removing');
        el.addEventListener('animationend', () => {
            if (el.parentNode) el.parentNode.removeChild(el);
        }, { once: true });
    }

    // Server status monitoring
    const statusIndicator = document.querySelector('.status-indicator');
    const statusText = document.querySelector('.server-status span');

    async function checkServerStatus() {
        try {
            const res = await fetch(`${API_BASE}/health`, { method: 'GET' });
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

    function runMagicChainingImmediately(targetValue) {
        const runKey = `magic:${targetValue}`;
        const displayName = `✨ Magic Chaining`;

        if (activeRuns.has(runKey)) {
            showSnackbar(displayName, `Already running on ${targetValue}`, 'warning', 3000);
            return;
        }

        activeRuns.add(runKey);
        const snackbarId = 'magic-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
        showSnackbar(displayName, `Initializing on ${targetValue}...`, 'info', 0, snackbarId);

        termPrint(`[magic] Connecting for target: ${targetValue}`, 'sys-msg');

        const ws = new WebSocket(`${WS_BASE}/magic/run`);
        activeSockets.push(ws);
        activeSocketsMap.set(snackbarId, ws);
        let gotResult = false;

        ws.onopen = () => {
            ws.send(JSON.stringify({
                target: targetValue,
                workspace_name: activeWorkspace || ""
            }));
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'log') {
                    termPrint(`[magic] ${data.message}`);
                } else if (data.type === 'status') {
                    gotResult = true;
                    termPrint(`[magic] Completed: ${data.status}`, 'success');
                    updateSnackbar(snackbarId, displayName, 'Completed successfully', 'success', 4000);
                } else if (data.type === 'error') {
                    gotResult = true;
                    termPrint(`[magic] Error: ${data.message}`, 'error');
                    updateSnackbar(snackbarId, displayName, `Error: ${data.message}`, 'error', 5000);
                }
            } catch (e) {
                termPrint(`[magic] ${event.data}`);
            }
        };

        ws.onclose = () => {
            activeSockets = activeSockets.filter(s => s !== ws);
            activeSocketsMap.delete(snackbarId);
            activeRuns.delete(runKey);
            termPrint(`[magic] Connection closed.`, 'sys-msg');

            if (!gotResult) {
                updateSnackbar(snackbarId, displayName, 'Connection closed', 'warning', 4000);
            }

            // Refresh workspace to show new nodes and edges
            if (activeWorkspace) {
                selectWorkspace(activeWorkspace);
            }
        };
    }

    // Check on startup and then periodically every 10s
    checkServerStatus();
    setInterval(checkServerStatus, 10000);

    // Periodically refresh the active workspace graph to stream new nodes and edges in real time
    // but only when there is an active module run or magic chaining in progress.
    setInterval(() => {
        if (activeWorkspace && activeSockets.length > 0) {
            selectWorkspace(activeWorkspace);
        }
    }, 2000);
});
