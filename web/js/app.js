document.addEventListener('DOMContentLoaded', () => {
    // State
    let activeWorkspace = null;
    let modulesData = {};
    let activeSocket = null;

    // DOM Elements
    const workspaceList = document.getElementById('workspace-list');
    const activeWorkspaceTitle = document.getElementById('active-workspace-title');
    const countNodes = document.getElementById('count-nodes');
    const countEdges = document.getElementById('count-edges');
    const nodesTbody = document.getElementById('nodes-tbody');
    const edgesTbody = document.getElementById('edges-tbody');
    
    const moduleSelect = document.getElementById('module-select');
    const moduleDetails = document.getElementById('module-details');
    const moduleDesc = document.getElementById('module-description');
    const moduleAuthor = document.getElementById('module-author');
    const moduleVersion = document.getElementById('module-version');
    const moduleForm = document.getElementById('module-form');
    const btnRunModule = document.getElementById('btn-run-module');
    
    const terminalBody = document.getElementById('terminal-body');
    const btnClearTerm = document.getElementById('btn-clear-term');

    // Modals
    const modalNewWs = document.getElementById('modal-new-workspace');
    const btnNewWs = document.getElementById('btn-new-workspace');
    const btnCreateWs = document.getElementById('btn-create-ws');
    const inputWsName = document.getElementById('input-ws-name');
    const inputWsDesc = document.getElementById('input-ws-desc');
    const closeModals = document.querySelectorAll('.close-modal');

    // API Base
    const API_BASE = window.location.origin + '/api';
    const WS_BASE = (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + window.location.host + '/ws';

    // Initialize
    fetchWorkspaces();
    fetchModules();

    // Event Listeners
    btnNewWs.addEventListener('click', () => modalNewWs.classList.add('active'));
    closeModals.forEach(btn => btn.addEventListener('click', () => {
        modalNewWs.classList.remove('active');
    }));
    
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

    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(tab.dataset.target).classList.add('active');
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
                const defVal = value[0] || '';
                
                const group = document.createElement('div');
                group.className = 'form-group';
                
                const label = document.createElement('label');
                label.textContent = `${key} ${isRequired ? '*' : ''}`;
                label.title = value[2] || '';
                
                const input = document.createElement('input');
                input.type = 'text';
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
                    <div class="workspace-name">${w.name}</div>
                    <div class="workspace-desc">${w.description || 'No description'}</div>
                    <div class="workspace-stats">
                        <span class="stat-badge"><i class="fa-solid fa-circle-nodes"></i> ${w.node_count || 0}</span>
                        <span class="stat-badge"><i class="fa-solid fa-link"></i> ${w.edge_count || 0}</span>
                    </div>
                `;
                workspaceList.appendChild(item);
            });
        } catch (e) {
            console.error('Failed to fetch workspaces', e);
        }
    }

    async function fetchModules() {
        try {
            const res = await fetch(`${API_BASE}/modules`);
            modulesData = await res.json();
            
            moduleSelect.innerHTML = '<option value="" disabled selected>-- Choose a module --</option>';
            
            // Group by category if we wanted to, for now just list
            for (const key of Object.keys(modulesData).sort()) {
                const mod = modulesData[key];
                const opt = document.createElement('option');
                opt.value = key;
                opt.textContent = `${mod.name} (${key})`;
                moduleSelect.appendChild(opt);
            }
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
            
            fetchWorkspaces(); // silent refresh to update side counts
        } catch (e) {
            console.error('Failed to load workspace data', e);
        }
    }

    function termPrint(text, extraClass = '') {
        const line = document.createElement('div');
        line.className = `log-line ${extraClass}`;
        line.textContent = text;
        terminalBody.appendChild(line);
        terminalBody.scrollTop = terminalBody.scrollHeight;
    }
});
