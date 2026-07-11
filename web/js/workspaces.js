/*
 * Workspace list rendering + selection / data loading.
 */
import {
    workspaceList,
    activeWorkspaceTitle,
    countNodes,
    countEdges,
    nodesTbody,
    edgesTbody,
    inputRenameWs,
    modalRenameWs,
} from "./dom.js";
import { toggleTimelinePlay, initTimeline } from "./timeline.js";
import { renderTables } from "./graph.js";
import { loadSuggestions, pollAISuggestionsStatus } from "./settings.js";
import { fetchJobs } from "./jobs.js";
import { openWorkspaceScopeModal } from "./scope.js";
import { refreshWorldMap } from "./map.js";

export async function fetchWorkspaces() {
    try {
        const res = await KeenAPI.get(`/workspaces`);
        const data = await res.json();
        KeenStore.currentWorkspaces = data;
        renderWorkspaces();
    } catch (e) {
        console.error('Failed to fetch workspaces', e);
    }
}

export function renderWorkspaces() {
    const query = document.getElementById('search-workspaces')?.value.toLowerCase() || '';
    const filteredWorkspaces = KeenStore.currentWorkspaces.filter(w =>
        w.name.toLowerCase().includes(query) ||
        (w.description && w.description.toLowerCase().includes(query))
    );

    workspaceList.innerHTML = '';
    filteredWorkspaces.forEach(w => {
        const item = document.createElement('div');
        item.className = `workspace-item ${w.name === KeenStore.activeWorkspace ? 'active' : ''}`;
        item.onclick = () => selectWorkspace(w.name);

        item.innerHTML = `
            <div class="workspace-header-actions">
                <div class="workspace-name">${w.name}</div>
                <div class="workspace-actions">
                    <button class="icon-btn btn-ws-scope" data-name="${w.name}" title="Manage Scope"><i class="fa-solid fa-shield-halved"></i></button>
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
                await KeenAPI.del(`/workspaces/${wsName}`);
                if (KeenStore.activeWorkspace === wsName) {
                    KeenStore.setActiveWorkspace(null);
                    activeWorkspaceTitle.textContent = "No Workspace Selected";
                    nodesTbody.innerHTML = '';
                    edgesTbody.innerHTML = '';
                    if (KeenStore.network) KeenStore.network.destroy();
                    const exportDropdown = document.getElementById('export-dropdown');
                    if (exportDropdown) exportDropdown.style.display = 'none';
                    const timelineContainer = document.getElementById('graph-timeline');
                    if (timelineContainer) timelineContainer.style.display = 'none';
                    const minimapEl = document.getElementById('graph-minimap');
                    if (minimapEl) minimapEl.style.bottom = '16px';
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

    document.querySelectorAll('.btn-ws-scope').forEach(btn => {
        btn.onclick = (e) => {
            e.stopPropagation();
            openWorkspaceScopeModal(btn.dataset.name);
        };
    });
}

export async function selectWorkspace(name) {
    // Clear any active play timers on workspace switch
    if (KeenStore.isTimelinePlaying) {
        toggleTimelinePlay(false);
    }

    KeenStore.setActiveWorkspace(name);
    activeWorkspaceTitle.textContent = name;

    // Show export dropdown
    const exportDropdown = document.getElementById('export-dropdown');
    if (exportDropdown) {
        exportDropdown.style.display = 'block';
    }

    // Update UI active state
    document.querySelectorAll('.workspace-item').forEach(el => {
        if (el.querySelector('.workspace-name').textContent === name) el.classList.add('active');
        else el.classList.remove('active');
    });

    // Load nodes and edges
    try {
        const [nodesRes, edgesRes] = await Promise.all([
            KeenAPI.get(`/workspaces/${name}/nodes`),
            KeenAPI.get(`/workspaces/${name}/edges`)
        ]);

        const nodes = await nodesRes.json();
        const edges = await edgesRes.json();
        KeenStore.currentNodes = nodes;
        KeenStore.currentEdges = edges;

        countNodes.textContent = nodes.length || 0;
        countEdges.textContent = edges.length || 0;

        // Update stats on the sidebar workspace list item manually
        const activeItem = Array.from(workspaceList.querySelectorAll('.workspace-item')).find(el => {
            const nameEl = el.querySelector('.workspace-name');
            return nameEl && nameEl.textContent === name;
        });
        if (activeItem) {
            const statBadges = activeItem.querySelectorAll('.stat-badge');
            if (statBadges.length >= 2) {
                statBadges[0].innerHTML = `<i class="fa-solid fa-circle-nodes"></i> ${nodes.length}`;
                statBadges[1].innerHTML = `<i class="fa-solid fa-link"></i> ${edges.length}`;
            }
            // Update local currentWorkspaces array to persist stats during filtering/search
            const ws = KeenStore.currentWorkspaces.find(w => w.name === name);
            if (ws) {
                ws.node_count = nodes.length;
                ws.edge_count = edges.length;
            }
        }

        renderTables();

        initTimeline();
        refreshWorldMap();
        loadSuggestions();
        pollAISuggestionsStatus(name);
        fetchJobs();

        // Note: we don't call fetchWorkspaces() here anymore to avoid infinite loops,
        // since fetchWorkspaces recreates DOM elements. Just update stats manually if needed.
    } catch (e) {
        console.error('Failed to load workspace data', e);
    }
}
