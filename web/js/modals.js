/*
 * Node / edge property field builders + edit-modal openers + metadata parsing.
 */
import {
    nodePropsFields,
    editNodeIdInput,
    editNodeTypeSelect,
    editNodeValueInput,
    editNodePropsFields,
    modalEditNode,
    editEdgeIdInput,
    editEdgeRelationshipInput,
    editEdgePropsFields,
    modalEditEdge,
} from "./dom.js";

export function addPropertyField(name = '', value = '', removable = false) {
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

export function createEditPropField(container, name = '', value = '') {
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

export function openEditNodeModal(node) {
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

export function openEditEdgeModal(edgeId) {
    const edge = KeenStore.currentEdges.find(e => e.id === edgeId);
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

export function parseMetaValue(val) {
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
