/*
 * Scope UI: declaring scope entries when creating a workspace, and viewing/
 * editing an existing workspace's scope + quarantined nodes from a modal
 * opened via the sidebar workspace list.
 */
import { showSnackbar } from "./notifications.js";

const SCOPE_TYPES = ['domain', 'ip', 'cidr', 'organization', 'person'];

function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function typeOptionsHtml(selected) {
    return SCOPE_TYPES.map(t =>
        `<option value="${t}" ${t === selected ? 'selected' : ''}>${t.charAt(0).toUpperCase() + t.slice(1)}</option>`
    ).join('');
}

// --- New Workspace modal: build up a scope list before the workspace exists ---

export function addWsScopeRow() {
    const container = document.getElementById('ws-scope-rows');
    if (!container) return;

    const row = document.createElement('div');
    row.className = 'ws-scope-row';
    row.style.cssText = 'display:flex; gap:6px; margin-bottom:6px; align-items:center;';
    row.innerHTML = `
        <select class="ws-scope-type" style="flex: 0 0 110px;">${typeOptionsHtml('domain')}</select>
        <input type="text" class="ws-scope-value" placeholder="Value" style="flex:1;" autocomplete="off">
        <input type="text" class="ws-scope-consent" placeholder="Consent basis (person)" style="flex:1;" autocomplete="off">
        <button type="button" class="icon-btn btn-remove-ws-scope-row" style="color: var(--error);"><i class="fa-solid fa-xmark"></i></button>
    `;
    row.querySelector('.btn-remove-ws-scope-row').addEventListener('click', () => row.remove());
    container.appendChild(row);
}

export function clearWsScopeRows() {
    const container = document.getElementById('ws-scope-rows');
    if (container) container.innerHTML = '';
}

/** Collect the New Workspace modal's scope rows into the `scope` array POST /api/workspaces expects. */
export function collectWsScopeRows() {
    const container = document.getElementById('ws-scope-rows');
    if (!container) return [];

    const scope = [];
    container.querySelectorAll('.ws-scope-row').forEach(row => {
        const scope_type = row.querySelector('.ws-scope-type').value;
        const value = row.querySelector('.ws-scope-value').value.trim();
        const consent_basis = row.querySelector('.ws-scope-consent').value.trim();
        if (value) {
            scope.push({ scope_type, value, consent_basis });
        }
    });
    return scope;
}

// --- Existing workspace: manage scope + view quarantined nodes ---

let activeScopeWorkspace = null;

export async function openWorkspaceScopeModal(name) {
    activeScopeWorkspace = name;
    const modal = document.getElementById('modal-workspace-scope');
    const nameEl = document.getElementById('scope-modal-ws-name');
    if (!modal) return;

    if (nameEl) nameEl.textContent = name;
    document.getElementById('scope-modal-value').value = '';
    document.getElementById('scope-modal-consent').value = '';
    modal.classList.add('active');

    await Promise.all([fetchScopeEntries(), fetchQuarantinedNodes()]);
}

export async function fetchScopeEntries() {
    if (!activeScopeWorkspace) return;
    const listEl = document.getElementById('scope-modal-list');
    if (!listEl) return;

    try {
        const res = await KeenAPI.get(`/workspaces/${activeScopeWorkspace}/scope`);
        if (!res.ok) return;
        const entries = await res.json();
        renderScopeEntries(entries);
    } catch (e) {
        console.error('Failed to fetch scope entries', e);
    }
}

function renderScopeEntries(entries) {
    const listEl = document.getElementById('scope-modal-list');
    if (!listEl) return;

    if (!entries.length) {
        listEl.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.8rem;">No scope declared -- enforcement is opted out; every discovery is treated as in-scope.</div>';
        return;
    }

    listEl.innerHTML = entries.map(entry => `
        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; padding:6px 0; border-bottom: 1px solid var(--border-color);">
            <div style="font-size: 0.82rem;">
                <span class="badge" style="text-transform: capitalize;">${escapeHtml(entry.scope_type)}</span>
                <strong style="margin-left: 6px;">${escapeHtml(entry.value)}</strong>
                ${entry.consent_basis ? `<span style="color: var(--text-secondary); margin-left: 6px;">(${escapeHtml(entry.consent_basis)})</span>` : ''}
            </div>
            <button class="icon-btn btn-remove-scope-entry" data-id="${entry.id}" title="Remove" style="color: var(--error);">
                <i class="fa-solid fa-trash"></i>
            </button>
        </div>
    `).join('');

    listEl.querySelectorAll('.btn-remove-scope-entry').forEach(btn => {
        btn.addEventListener('click', () => removeScopeEntry(btn.dataset.id));
    });
}

export async function addScopeEntry() {
    if (!activeScopeWorkspace) return;
    const scope_type = document.getElementById('scope-modal-type').value;
    const value = document.getElementById('scope-modal-value').value.trim();
    const consent_basis = document.getElementById('scope-modal-consent').value.trim();
    if (!value) return;

    try {
        const res = await KeenAPI.post(`/workspaces/${activeScopeWorkspace}/scope`, { scope_type, value, consent_basis });
        if (res.ok) {
            document.getElementById('scope-modal-value').value = '';
            document.getElementById('scope-modal-consent').value = '';
            fetchScopeEntries();
        } else {
            const err = await res.json();
            showSnackbar('Scope', `Failed to add entry: ${err.detail || err.error || 'Unknown error'}`, 'error', 4000);
        }
    } catch (e) {
        showSnackbar('Scope', 'Failed to add entry. Network error.', 'error', 4000);
    }
}

export async function removeScopeEntry(entryId) {
    if (!activeScopeWorkspace) return;
    try {
        const res = await KeenAPI.del(`/workspaces/${activeScopeWorkspace}/scope/${entryId}`);
        if (res.ok) {
            fetchScopeEntries();
        } else {
            showSnackbar('Scope', 'Failed to remove entry.', 'error', 4000);
        }
    } catch (e) {
        showSnackbar('Scope', 'Failed to remove entry. Network error.', 'error', 4000);
    }
}

export async function fetchQuarantinedNodes() {
    if (!activeScopeWorkspace) return;
    const el = document.getElementById('scope-modal-quarantined');
    if (!el) return;

    try {
        const res = await KeenAPI.get(`/workspaces/${activeScopeWorkspace}/quarantined-nodes`);
        if (!res.ok) return;
        const nodes = await res.json();
        if (!nodes.length) {
            el.innerHTML = 'No quarantined nodes.';
            return;
        }
        el.innerHTML = nodes.map(n => `
            <div style="padding: 4px 0; border-bottom: 1px solid var(--border-color);">
                <strong>${escapeHtml(n.type)}</strong>: ${escapeHtml(n.value)}
                <div style="color: var(--text-secondary); font-size: 0.75rem;">${escapeHtml(n.quarantine_reason || '')}</div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Failed to fetch quarantined nodes', e);
    }
}

export function initScopeListeners() {
    const addWsRowBtn = document.getElementById('btn-add-ws-scope-row');
    if (addWsRowBtn) addWsRowBtn.addEventListener('click', addWsScopeRow);

    const addModalBtn = document.getElementById('btn-scope-modal-add');
    if (addModalBtn) addModalBtn.addEventListener('click', addScopeEntry);
}
