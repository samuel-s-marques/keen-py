document.addEventListener('DOMContentLoaded', () => {
    // Theme setup
    const btnThemeToggle = document.getElementById('btn-theme-toggle');
    const savedTheme = localStorage.getItem('keen-theme') || 'dark';
    if (savedTheme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }
    btnThemeToggle.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        if (currentTheme === 'light') {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('keen-theme', 'dark');
        } else {
            document.documentElement.setAttribute('data-theme', 'light');
            localStorage.setItem('keen-theme', 'light');
        }
        if (activeWorkspace) selectWorkspace(activeWorkspace); // Redraw graph to apply theme
    });

    // State
    let activeWorkspace = null;
    let modulesData = {};
    let activeSocket = null;
    let network = null;
    let isConfigUnlocked = false;
    let configKeys = {};

    const NODE_TO_VALIDATOR_MAP = {
        'email-addr': ['email'],
        'email-dst': ['email'],
        'domain-name': ['domain', 'url'],
        'ipv4-addr': ['ip'],
        'ipv6-addr': ['ip'],
        'x-phone-number': ['phone'],
        'phone-number': ['phone'],
        'x-url': ['url']
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
    
    const modalRenameWs = document.getElementById('modal-rename-workspace');
    const btnConfirmRenameWs = document.getElementById('btn-confirm-rename-ws');
    const inputRenameWs = document.getElementById('input-rename-ws');

    const modalSettings = document.getElementById('modal-settings');
    const btnSettings = document.getElementById('btn-settings');
    const btnUnlockSettings = document.getElementById('btn-unlock-settings');
    const inputMasterPassword = document.getElementById('input-master-password');
    const settingsLocked = document.getElementById('settings-locked');
    const settingsUnlocked = document.getElementById('settings-unlocked');
    const btnSaveApiKey = document.getElementById('btn-save-api-key');
    const apiKeysList = document.getElementById('api-keys-list');

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

    // Modals Handling
    btnNewWs.addEventListener('click', () => modalNewWs.classList.add('active'));
    btnSettings.addEventListener('click', () => {
        modalSettings.classList.add('active');
        if (isConfigUnlocked) fetchApiKeys();
    });
    
    closeModals.forEach(btn => btn.addEventListener('click', () => {
        modalNewWs.classList.remove('active');
        modalSettings.classList.remove('active');
        modalRenameWs.classList.remove('active');
    }));

    // Settings API Keys
    btnUnlockSettings.addEventListener('click', async () => {
        const password = inputMasterPassword.value;
        const res = await fetch(`${API_BASE}/config/unlock`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ password })
        });
        if (res.ok) {
            isConfigUnlocked = true;
            settingsLocked.classList.add('hidden');
            settingsUnlocked.classList.remove('hidden');
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
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ service, api_key })
        });
        document.getElementById('input-api-service').value = '';
        document.getElementById('input-api-key').value = '';
        fetchApiKeys();
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
                    <div><strong>${k.service}</strong>: <span style="font-family:var(--font-mono)">${k.api_key.substring(0,4)}...</span></div>
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
    }
    
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
            headers: {'Content-Type': 'application/json'},
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
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(tab.dataset.target).classList.add('active');
            
            // Redraw network when tab becomes visible
            if (tab.dataset.target === 'tab-graph' && network) {
                network.redraw();
                network.fit();
            }
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
        moduleVersion.textContent = `v${mod.version || '1.0'}`;

        // Build Form
        moduleForm.innerHTML = '';
        if (mod.options) {
            for (const [key, value] of Object.entries(mod.options)) {
                // value is usually [default, required, description, type]
                const isRequired = value[1];
                let defVal = value[0] || '';
                
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
                const input = document.createElement('input');
                input.type = isSecret ? 'password' : 'text';
                input.name = key;
                input.value = defVal;
                input.placeholder = value[2] || '';
                
                group.appendChild(label);
                group.appendChild(input);
                moduleForm.appendChild(group);
            }
        }
        
        moduleDetails.classList.remove('hidden');
    });

    // Run Module via WebSockets
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

        // Connect WS
        if (activeSocket) {
            activeSocket.close();
        }

        termPrint(`Connecting to module execution engine for ${modName}...`, 'sys-msg');
        btnRunModule.disabled = true;
        btnRunModule.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Running...';

        const ws = new WebSocket(`${WS_BASE}/modules/${modName}/run`);
        activeSocket = ws;

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
                    termPrint(data.message);
                } else if (data.type === 'status') {
                    termPrint(`Execution completed: ${data.status}`, 'sys-msg');
                } else if (data.type === 'error') {
                    termPrint(`Error: ${data.message}`, 'sys-msg');
                }
            } catch (e) {
                termPrint(event.data);
            }
        };

        ws.onclose = () => {
            btnRunModule.disabled = false;
            btnRunModule.innerHTML = '<i class="fa-solid fa-play"></i> Run Module';
            termPrint(`Connection closed.`, 'sys-msg');
            activeSocket = null;
            
            // Refresh workspace to show new nodes
            if (activeWorkspace) {
                selectWorkspace(activeWorkspace);
            }
        };
    });

    // --- Functions ---

    function formatModuleName(key, mod) {
        let cat = mod.category ? mod.category : "Uncategorized";
        cat = cat.charAt(0).toUpperCase() + cat.slice(1);
        cat = cat.replace(/[_-]/g, ' ');
        const name = mod.name ? mod.name.replace(/[_-]/g, ' ') : key;
        return `${cat} - ${name}`;
    }

    function buildModuleDropdown(compatibleValidators = [], prefillValue = null) {
        moduleSelect.innerHTML = '<option value="" disabled selected>-- Choose a module --</option>';
        
        const compatGroup = document.createElement('optgroup');
        compatGroup.label = 'Compatible Modules';
        
        const allGroup = document.createElement('optgroup');
        allGroup.label = 'All Modules';

        let firstMatch = null;

        for (const key of Object.keys(modulesData).sort()) {
            const mod = modulesData[key];
            let isMatch = false;

            if (compatibleValidators.length > 0 && mod.options) {
                for (const [optName, optValue] of Object.entries(mod.options)) {
                    if (compatibleValidators.includes(optValue[3])) {
                        isMatch = true;
                        break;
                    }
                }
            }

            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = formatModuleName(key, mod);

            if (isMatch) {
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
                const inputs = moduleForm.querySelectorAll('input');
                for (const input of inputs) {
                    const optVal = modulesData[firstMatch].options[input.name];
                    if (optVal && compatibleValidators.includes(optVal[3])) {
                        input.value = prefillValue;
                    }
                }
            }, 50);
        }
    }

    async function fetchWorkspaces() {
        try {
            const res = await fetch(`${API_BASE}/workspaces`);
            const data = await res.json();
            
            workspaceList.innerHTML = '';
            data.forEach(w => {
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

        } catch (e) {
            console.error('Failed to fetch workspaces', e);
        }
    }

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
            
            countNodes.textContent = nodes.length || 0;
            countEdges.textContent = edges.length || 0;
            
            nodesTbody.innerHTML = '';
            if (nodes.length) {
                nodes.forEach(n => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><span class="badge">${n.type}</span></td>
                        <td>${n.value}</td>
                        <td style="color:var(--text-secondary);font-size:0.8rem">${n.timestamp}</td>
                    `;
                    nodesTbody.appendChild(tr);
                });
            } else {
                nodesTbody.innerHTML = '<tr><td colspan="3">No nodes found.</td></tr>';
            }

            edgesTbody.innerHTML = '';
            if (edges.length) {
                edges.forEach(e => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${e.source_id}</td>
                        <td>${e.target_id}</td>
                        <td><span class="badge">${e.relationship}</span></td>
                    `;
                    edgesTbody.appendChild(tr);
                });
            } else {
                edgesTbody.innerHTML = '<tr><td colspan="3">No edges found.</td></tr>';
            }

            drawGraph(nodes, edges);
            
            // Note: we don't call fetchWorkspaces() here anymore to avoid infinite loops, 
            // since fetchWorkspaces recreates DOM elements. Just update stats manually if needed.
        } catch (e) {
            console.error('Failed to load workspace data', e);
        }
    }

    function drawGraph(nodes, edges) {
        const visNodes = nodes.map(n => {
            let icon = '\uf111'; // fa-circle default
            let color = '#8b92a5';
            
            if (n.type.includes('email')) { icon = '\uf0e0'; color = '#0072ff'; }
            else if (n.type.includes('domain')) { icon = '\uf0ac'; color = '#00f0ff'; }
            else if (n.type.includes('ip')) { icon = '\uf233'; color = '#ff00ff'; }
            else if (n.type.includes('phone')) { icon = '\uf095'; color = '#00e676'; }
            else if (n.type.includes('organization')) { icon = '\uf1ad'; color = '#ffb300'; }

            return {
                id: n.id || n.value,
                label: n.value,
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
        });

        const visEdges = edges.map(e => ({
            id: e.id,
            from: e.source_id,
            to: e.target_id,
            label: e.relationship.replace(/[_-]/g, ' '),
            font: { color: document.documentElement.getAttribute('data-theme') === 'light' ? '#1a1c23' : '#8b92a5', size: 10, align: 'middle' },
            color: { color: document.documentElement.getAttribute('data-theme') === 'light' ? '#1a1c2355' : '#8b92a588' },
            arrows: 'to'
        }));

        const data = {
            nodes: new vis.DataSet(visNodes),
            edges: new vis.DataSet(visEdges)
        };

        const options = {
            edges: { smooth: false },
            layout: { improvedLayout: false },
            physics: {
                enabled: true,
                barnesHut: { gravitationalConstant: -3000 },
                stabilization: { iterations: 150 }
            },
            interaction: { hover: true },
            manipulation: {
                enabled: false,
                deleteNode: function(data, callback) {
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
                deleteEdge: function(data, callback) {
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
                addEdge: function(edgeData, callback) {
                    const rel = prompt("Enter relationship (e.g. resolves-to, belongs-to):");
                    if (rel) {
                        edgeData.label = rel;
                        fetch(`${API_BASE}/workspaces/${activeWorkspace}/edges`, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                                source_id: String(edgeData.from),
                                target_id: String(edgeData.to),
                                relationship: rel
                            })
                        }).then(res => {
                            if(res.ok) {
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
        }
        network = new vis.Network(networkCanvas, data, options);

        // Freeze physics once initial stabilization is done to save CPU
        network.once("stabilizationIterationsDone", function () {
            network.setOptions({ physics: { enabled: false } });
            const btnPhy = document.getElementById('btn-toggle-physics');
            if(btnPhy) btnPhy.classList.remove('active');
        });

        // Setup Layout & Action Buttons
        const btnForce = document.getElementById('btn-layout-force');
        const btnHierarchical = document.getElementById('btn-layout-hierarchical');
        const btnCircle = document.getElementById('btn-layout-circle');
        const btnPhysics = document.getElementById('btn-toggle-physics');
        const btnAddEdge = document.getElementById('btn-add-edge');
        const btnDeleteSelected = document.getElementById('btn-delete-selected');

        function clearLayoutButtons() {
            btnForce.classList.remove('active');
            btnHierarchical.classList.remove('active');
            btnCircle.classList.remove('active');
        }

        if(btnDeleteSelected) btnDeleteSelected.onclick = () => {
            network.deleteSelected();
        };

        if(btnForce) btnForce.onclick = () => {
            clearLayoutButtons();
            btnForce.classList.add('active');
            network.setOptions({
                layout: { hierarchical: false },
                physics: { enabled: true }
            });
            btnPhysics.classList.add('active');
            network.stabilize();
        };

        if(btnHierarchical) btnHierarchical.onclick = () => {
            clearLayoutButtons();
            btnHierarchical.classList.add('active');
            network.setOptions({
                layout: { hierarchical: { enabled: true, sortMethod: 'directed' } },
                physics: { enabled: false }
            });
            btnPhysics.classList.remove('active');
        };

        if(btnCircle) btnCircle.onclick = () => {
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
        };

        if(btnPhysics) btnPhysics.onclick = () => {
            const isEnabled = btnPhysics.classList.contains('active');
            if (isEnabled) {
                btnPhysics.classList.remove('active');
                network.setOptions({ physics: { enabled: false } });
            } else {
                btnPhysics.classList.add('active');
                network.setOptions({ physics: { enabled: true } });
            }
        };

        if(btnAddEdge) btnAddEdge.onclick = () => {
            network.addEdgeMode();
        };

        network.on('oncontext', function (params) {
            params.event.preventDefault();
            const nodeId = this.getNodeAt(params.pointer.DOM);
            if (nodeId) {
                const selectedNode = nodes.find(n => n.id === nodeId || n.value === nodeId);
                if (selectedNode) {
                    showContextMenu(params.event.pageX, params.event.pageY, selectedNode);
                }
            } else {
                contextMenu.classList.add('hidden');
            }
        });

        network.on('click', function (params) {
            contextMenu.classList.add('hidden');
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                const selectedNode = nodes.find(n => n.id === nodeId || n.value === nodeId);
                if (selectedNode) {
                    handleNodeSelection(selectedNode);
                }
            }
        });
    }

    function showContextMenu(x, y, node) {
        const validators = NODE_TO_VALIDATOR_MAP[node.type] || [];
        contextMenuItems.innerHTML = '';
        
        let found = false;

        for (const key of Object.keys(modulesData).sort()) {
            const mod = modulesData[key];
            let isMatch = false;

            if (validators.length > 0 && mod.options) {
                for (const [optName, optValue] of Object.entries(mod.options)) {
                    if (validators.includes(optValue[3])) {
                        isMatch = true;
                        break;
                    }
                }
            }

            if (isMatch) {
                found = true;
                const item = document.createElement('div');
                item.className = 'context-menu-item';
                item.innerHTML = `<i class="fa-solid fa-play"></i> ${formatModuleName(key, mod)}`;
                item.onclick = (e) => {
                    e.stopPropagation();
                    contextMenu.classList.add('hidden');
                    // Select node and module
                    handleNodeSelection(node);
                    moduleSelect.value = key;
                    moduleSelect.dispatchEvent(new Event('change'));
                    
                    // Auto-fill target
                    setTimeout(() => {
                        const inputs = moduleForm.querySelectorAll('input');
                        for (const input of inputs) {
                            const optVal = modulesData[key].options[input.name];
                            if (optVal && validators.includes(optVal[3])) {
                                input.value = node.value;
                            }
                        }
                    }, 50);
                };
                contextMenuItems.appendChild(item);
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

        const deleteItem = document.createElement('div');
        deleteItem.className = 'context-menu-item';
        deleteItem.style.color = 'var(--error)';
        deleteItem.style.borderTop = '1px solid var(--border-color)';
        deleteItem.style.marginTop = '4px';
        deleteItem.style.paddingTop = '8px';
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

    function handleNodeSelection(node) {
        const validators = NODE_TO_VALIDATOR_MAP[node.type] || [];
        buildModuleDropdown(validators, node.value);
        termPrint(`Selected node: ${node.value} (${node.type}). Auto-filling compatible modules.`, 'sys-msg');
    }

    function termPrint(text, extraClass = '') {
        const line = document.createElement('div');
        line.className = `log-line ${extraClass}`;
        line.textContent = text;
        terminalBody.appendChild(line);
        terminalBody.scrollTop = terminalBody.scrollHeight;
    }
});
