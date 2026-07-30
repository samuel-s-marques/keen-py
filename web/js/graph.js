/*
 * Network graph rendering (vis-network), minimap, context menu, node/edge info
 * panel, and the nodes/edges tables.
 */
import {
    networkCanvas,
    contextMenu,
    contextMenuItems,
    moduleSelect,
    moduleDetails,
    nodesTbody,
    edgesTbody,
    modalMergeNodes,
    mergeNodesList,
    mergePreview,
} from "./dom.js";
import { showSnackbar } from "./notifications.js";
import { selectWorkspace } from "./workspaces.js";
import { getNodeStyle, mediaImageUrl } from "./graph-styles.js";
import { drawGraphCytoscape } from "./graph-cytoscape.js";
import {
    NODE_TO_VALIDATOR_MAP,
    buildModuleDropdown,
    runModuleImmediately,
    runMagicChainingImmediately,
} from "./modules.js";
import { openEditEdgeModal, openEditNodeModal, openCreateNodeModal } from "./modals.js";

// --- Clipboard helpers ---

function fallbackCopyToClipboard(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
        ok = document.execCommand('copy');
    } catch (e) {
        ok = false;
    }
    document.body.removeChild(ta);
    return ok;
}

export function copyTextToClipboard(text, label = 'Value') {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(() => showSnackbar('Copied', `${label} copied to clipboard.`, 'success', 2000))
            .catch(() => {
                if (fallbackCopyToClipboard(text)) {
                    showSnackbar('Copied', `${label} copied to clipboard.`, 'success', 2000);
                } else {
                    showSnackbar('Copy failed', 'Could not copy to clipboard.', 'error', 3000);
                }
            });
    } else if (fallbackCopyToClipboard(text)) {
        showSnackbar('Copied', `${label} copied to clipboard.`, 'success', 2000);
    } else {
        showSnackbar('Copy failed', 'Could not copy to clipboard.', 'error', 3000);
    }
}

function edgeToText(edge) {
    if (!edge) return '';
    const sourceNode = KeenStore.currentNodes.find(n => n.id === edge.source_id) || { value: edge.source_id };
    const targetNode = KeenStore.currentNodes.find(n => n.id === edge.target_id) || { value: edge.target_id };
    return `${sourceNode.value} -[${edge.relationship}]-> ${targetNode.value}`;
}

// Stashes full node data (type/value/metadata) in the in-app clipboard so
// Ctrl+V / "Paste Node" can recreate the node(s) -- the OS clipboard only
// carries the plain-text value written by copyTextToClipboard, which isn't
// enough to reconstruct a node.
function stashNodesForPaste(nodes) {
    KeenStore.nodeClipboard = nodes.map(n => ({
        type: n.type,
        value: n.value,
        metadata: n.metadata || {},
    }));
}

export function copyNodeToClipboard(node) {
    if (!node) return;
    stashNodesForPaste([node]);
    copyTextToClipboard(node.clean_value || node.value, 'Node value');
}

export function copyEdgeToClipboard(edge) {
    if (!edge) return;
    // An edge needs both endpoints to recreate -- not pasteable, and stale
    // node data in the clipboard would otherwise silently paste on Ctrl+V.
    KeenStore.nodeClipboard = null;
    copyTextToClipboard(edgeToText(edge), 'Edge');
}

// Copies the current node/edge selection to the clipboard. Nodes take
// priority over edges when both are selected, matching the "nodes are the
// primary selection" convention used elsewhere (renderSelectionSummary).
export function copySelectionToClipboard(selectedNodeIds, selectedEdgeIds) {
    if (selectedNodeIds && selectedNodeIds.length > 0) {
        const nodes = selectedNodeIds
            .map(id => KeenStore.currentNodes.find(n => String(n.id) === String(id) || n.value === id))
            .filter(Boolean);
        stashNodesForPaste(nodes);
        const values = selectedNodeIds.map(id => {
            const node = KeenStore.currentNodes.find(n => String(n.id) === String(id) || n.value === id);
            return node ? (node.clean_value || node.value) : id;
        });
        copyTextToClipboard(values.join('\n'), values.length === 1 ? 'Node value' : `${values.length} node values`);
    } else if (selectedEdgeIds && selectedEdgeIds.length > 0) {
        KeenStore.nodeClipboard = null;
        const values = selectedEdgeIds.map(id => {
            const edge = KeenStore.currentEdges.find(e => String(e.id) === String(id));
            return edge ? edgeToText(edge) : id;
        });
        copyTextToClipboard(values.join('\n'), values.length === 1 ? 'Edge' : `${values.length} edges`);
    }
}

// Node values are globally unique per workspace (see get_or_add_node in
// managers.py, which dedups by `value` alone) -- pasting a node whose value
// already exists would otherwise silently no-op and just hand back the
// existing id. Suffix the value so the paste actually creates a new,
// distinguishable row instead of appearing to do nothing.
function uniqueDuplicateValue(baseValue, existingValues) {
    let n = 2;
    let candidate = `${baseValue} (copy)`;
    while (existingValues.has(candidate)) {
        candidate = `${baseValue} (copy ${n})`;
        n++;
    }
    return candidate;
}

// Ctrl+V / "Paste Node" entry point. Prefers the in-app node clipboard
// (recreates full node data, including across workspaces); falls back to
// whatever plain text is on the system clipboard and lets the user pick a
// type for it via the create-node modal.
export async function pasteFromClipboard() {
    if (!KeenStore.activeWorkspace) {
        showSnackbar('Paste', 'Please select a workspace first.', 'error', 4000);
        return;
    }

    if (KeenStore.nodeClipboard && KeenStore.nodeClipboard.length > 0) {
        const nodes = KeenStore.nodeClipboard;
        // Sequential, not Promise.all -- pasting the same clipboard entry
        // more than once in a row needs each iteration's synthesized value
        // to account for the ones minted earlier in this same paste, not
        // just what's already in KeenStore.currentNodes.
        const existingValues = new Set(KeenStore.currentNodes.map(n => n.value));
        let pastedCount = 0;
        let duplicateCount = 0;
        let failedCount = 0;
        try {
            for (const n of nodes) {
                const metadata = { ...(n.metadata || {}), pasted: true };
                let value = n.value;
                let isDuplicate = false;
                if (existingValues.has(value)) {
                    value = uniqueDuplicateValue(value, existingValues);
                    metadata.duplicate = true;
                    metadata.duplicate_of = n.value;
                    isDuplicate = true;
                }
                existingValues.add(value);
                const res = await KeenAPI.post(`/workspaces/${KeenStore.activeWorkspace}/nodes`, {
                    type: n.type,
                    value,
                    metadata,
                });
                if (res.ok) {
                    pastedCount++;
                    if (isDuplicate) duplicateCount++;
                } else {
                    failedCount++;
                }
            }
            selectWorkspace(KeenStore.activeWorkspace);
            const suffix = duplicateCount > 0
                ? ` (${duplicateCount} duplicate${duplicateCount > 1 ? 's' : ''} of existing node${duplicateCount > 1 ? 's' : ''})`
                : '';
            if (pastedCount > 0) {
                showSnackbar('Paste', `Pasted ${pastedCount} node(s)${suffix}.`, failedCount > 0 ? 'warning' : 'success', 3000);
            }
            if (failedCount > 0) {
                showSnackbar('Paste', `Failed to paste ${failedCount} node(s).`, 'error', 4000);
            }
        } catch (e) {
            showSnackbar('Paste', 'Failed to paste node(s).', 'error', 4000);
        }
        return;
    }

    if (!navigator.clipboard || !navigator.clipboard.readText) {
        showSnackbar('Paste', 'Nothing to paste.', 'error', 3000);
        return;
    }
    try {
        const text = (await navigator.clipboard.readText()).trim();
        if (!text) {
            showSnackbar('Paste', 'Clipboard is empty.', 'error', 3000);
            return;
        }
        openCreateNodeModal(text);
    } catch (e) {
        showSnackbar('Paste', 'Could not read clipboard. Grant clipboard permission and try again.', 'error', 4000);
    }
}

export function renderTables() {
    const nodesSearchQuery = document.getElementById('search-nodes')?.value.toLowerCase() || '';
    const edgesSearchQuery = document.getElementById('search-edges')?.value.toLowerCase() || '';

    const filteredNodes = KeenStore.currentNodes.filter(n =>
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
                if (KeenStore.network) {
                    KeenStore.network.setSelection({ nodes: [n.id || n.value], edges: [] });
                    KeenStore.network.focus(n.id || n.value, { animation: true });
                }
            };
            nodesTbody.appendChild(tr);
        });
    } else {
        nodesTbody.innerHTML = '<tr><td colspan="3">No nodes found.</td></tr>';
    }

    const filteredEdges = KeenStore.currentEdges.filter(e =>
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
                if (KeenStore.network) {
                    KeenStore.network.setSelection({ nodes: [], edges: [e.id] });
                }
            };
            edgesTbody.appendChild(tr);
        });
    } else {
        edgesTbody.innerHTML = '<tr><td colspan="3">No edges found.</td></tr>';
    }
}

// Dispatches to whichever engine is active (KeenStore.graphEngine, defaults
// to 'vis'). Every caller (timeline.js, workspaces.js) just calls drawGraph()
// -- this is the one place that needs to know two engines exist.
export function drawGraph(nodes, edges) {
    if (KeenStore.graphEngine === 'cytoscape') {
        drawGraphCytoscape(nodes, edges);
        return;
    }
    drawGraphVis(nodes, edges);
}

function drawGraphVis(nodes, edges) {
    let allHavePositions = nodes.length > 0;
    KeenStore.lastSelection = { nodes: [], edges: [] };

    const visNodes = nodes.map(n => {
        const { icon, color } = getNodeStyle(n.type);

        const fullText = n.label || n.value;
        const shortText = fullText.length > 20 ? fullText.substring(0, 18) + '...' : fullText;
        const imageUrl = mediaImageUrl(n);

        const visNode = {
            id: n.id || n.value,
            label: shortText,
            title: fullText,
            fullLabel: fullText,
            shortLabel: shortText,
            group: n.type,
            font: { color: document.documentElement.getAttribute('data-theme') === 'light' ? '#1a1c23' : '#f0f2f8' }
        };

        if (imageUrl) {
            visNode.shape = 'circularImage';
            visNode.image = imageUrl;
            visNode.size = 22;
            visNode.borderWidth = 2;
            visNode.color = { border: color };
        } else {
            visNode.shape = 'icon';
            visNode.icon = {
                face: '"Font Awesome 6 Free"',
                code: icon,
                size: 40,
                color: color,
                weight: "900"
            };
        }

        if (n.x !== null && n.x !== undefined && n.y !== null && n.y !== undefined) {
            visNode.x = n.x;
            visNode.y = n.y;
        } else {
            allHavePositions = false;
        }

        return visNode;
    });

    const minimapVisNodes = visNodes.map(n => ({
        ...n,
        icon: n.icon ? { ...n.icon, size: 12 } : undefined,
        size: n.shape === 'circularImage' ? 8 : n.size,
        font: { size: 0 }
    }));

    const visEdges = edges.map(e => ({
        id: e.id,
        from: e.source_id,
        to: e.target_id,
        label: e.relationship.replace(/[_-]/g, ' '),
        font: { color: document.documentElement.getAttribute('data-theme') === 'light' ? '#1a1c23' : '#8b92a5', size: 10, align: 'middle', strokeWidth: 0 },
        color: { color: document.documentElement.getAttribute('data-theme') === 'light' ? '#1a1c2355' : '#8b92a588' },
        arrows: 'to'
    }));

    const isWorkspaceSwitched = (KeenStore.activeWorkspace !== KeenStore.currentWorkspace);
    KeenStore.currentWorkspace = KeenStore.activeWorkspace;

    if (KeenStore.network && !isWorkspaceSwitched && KeenStore.nodesDataSet && KeenStore.edgesDataSet) {
        // Keep track of which nodes are new to decide if we need to enable physics
        const existingNodeIds = new Set(KeenStore.nodesDataSet.getIds());
        const newNodesWithoutPos = visNodes.filter(n => !existingNodeIds.has(n.id) && (n.x === null || n.x === undefined || n.y === null || n.y === undefined));

        // Synchronize nodes
        const newNodeIds = new Set(visNodes.map(n => n.id));
        const nodeIdsToRemove = KeenStore.nodesDataSet.getIds().filter(id => !newNodeIds.has(id));

        if (nodeIdsToRemove.length > 0) {
            KeenStore.nodesDataSet.remove(nodeIdsToRemove);
        }

        // For updates/adds: use nodesDataSet.update
        if (visNodes.length > 0) {
            KeenStore.nodesDataSet.update(visNodes);
        }

        // Synchronize edges
        const newEdgeIds = new Set(visEdges.map(e => e.id));
        const edgeIdsToRemove = KeenStore.edgesDataSet.getIds().filter(id => !newEdgeIds.has(id));

        if (edgeIdsToRemove.length > 0) {
            KeenStore.edgesDataSet.remove(edgeIdsToRemove);
        }

        if (visEdges.length > 0) {
            KeenStore.edgesDataSet.update(visEdges);
        }

        // Synchronize minimap nodes
        if (KeenStore.minimapNodesDataSet && KeenStore.minimapEdgesDataSet) {
            const newMinimapNodeIds = new Set(minimapVisNodes.map(n => n.id));
            const minimapNodeIdsToRemove = KeenStore.minimapNodesDataSet.getIds().filter(id => !newMinimapNodeIds.has(id));

            if (minimapNodeIdsToRemove.length > 0) {
                KeenStore.minimapNodesDataSet.remove(minimapNodeIdsToRemove);
            }
            if (minimapVisNodes.length > 0) {
                KeenStore.minimapNodesDataSet.update(minimapVisNodes);
            }

            // Synchronize minimap edges
            const newMinimapEdgeIds = new Set(visEdges.map(e => e.id));
            const minimapEdgeIdsToRemove = KeenStore.minimapEdgesDataSet.getIds().filter(id => !newMinimapEdgeIds.has(id));

            if (minimapEdgeIdsToRemove.length > 0) {
                KeenStore.minimapEdgesDataSet.remove(minimapEdgeIdsToRemove);
            }
            if (visEdges.length > 0) {
                KeenStore.minimapEdgesDataSet.update(visEdges);
            }
        }

        // If there are new nodes without positions, enable physics so they float in smoothly
        if (newNodesWithoutPos.length > 0) {
            KeenStore.network.setOptions({ physics: { enabled: true } });
            const btnPhy = document.getElementById('btn-toggle-physics');
            if (btnPhy) btnPhy.classList.add('active');
        }

        if (KeenStore.minimap) {
            setTimeout(() => {
                if (KeenStore.minimap) KeenStore.minimap.fit();
            }, 200);
        }
        return;
    }

    KeenStore.nodesDataSet = new vis.DataSet(visNodes);
    KeenStore.edgesDataSet = new vis.DataSet(visEdges);
    KeenStore.minimapNodesDataSet = new vis.DataSet(minimapVisNodes);
    KeenStore.minimapEdgesDataSet = new vis.DataSet(visEdges);

    const data = {
        nodes: KeenStore.nodesDataSet,
        edges: KeenStore.edgesDataSet
    };

    const options = {
        // 'dynamic' bends each edge along its own invisible support node, so
        // multiple edges between the same two nodes (or edges that happen to
        // cross the same area) fan out instead of stacking into one solid,
        // near-black line -- straight edges (smooth: false) is what made
        // overlapping edges visually merge.
        edges: { smooth: { enabled: true, type: 'dynamic', roundness: 0.5 } },
        layout: { improvedLayout: false },
        physics: {
            enabled: !allHavePositions,
            barnesHut: { gravitationalConstant: -6000, avoidOverlap: 1, springLength: 150 },
            stabilization: { iterations: 200 }
        },
        interaction: { hover: true, multiselect: true },
        manipulation: {
            enabled: false,
            deleteNode: function (data, callback) {
                if (confirm("Delete selected node(s)? This will also cascade delete any connected edges.")) {
                    const promises = data.nodes.map(id => KeenAPI.del(`/workspaces/${KeenStore.activeWorkspace}/nodes/${id}`));
                    Promise.all(promises).then(() => {
                        callback(data);
                        selectWorkspace(KeenStore.activeWorkspace);
                    }).catch(e => {
                        showSnackbar('Nodes', 'Failed to delete nodes.', 'error', 5000);
                        callback(null);
                    });
                } else {
                    callback(null);
                }
            },
            deleteEdge: function (data, callback) {
                if (confirm("Delete selected edge(s)?")) {
                    const promises = data.edges.map(id => KeenAPI.del(`/workspaces/${KeenStore.activeWorkspace}/edges/${id}`));
                    Promise.all(promises).then(() => {
                        callback(data);
                        selectWorkspace(KeenStore.activeWorkspace);
                    }).catch(e => {
                        showSnackbar('Edges', 'Failed to delete edges.', 'error', 5000);
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
                    KeenAPI.post(`/workspaces/${KeenStore.activeWorkspace}/edges`, {
                        source_id: String(edgeData.from),
                        target_id: String(edgeData.to),
                        relationship: rel
                    }).then(res => {
                        if (res.ok) {
                            callback(edgeData);
                            selectWorkspace(KeenStore.activeWorkspace);
                        } else {
                            showSnackbar('Edges', 'Failed to save edge.', 'error', 5000);
                            callback(null);
                        }
                    });
                } else {
                    callback(null);
                }
            }
        }
    };



    if (KeenStore.network) {
        KeenStore.network.destroy();
        KeenStore.network = null;
    }
    KeenStore.network = new vis.Network(networkCanvas, data, options);

    // Mini-map implementation
    const minimapCanvas = document.getElementById('minimap-canvas');
    if (KeenStore.minimap) {
        KeenStore.minimap.destroy();
        KeenStore.minimap = null;
    }
    if (minimapCanvas) {
        const minimapOptions = {
            nodes: {
                icon: { size: 12 },
                font: { size: 0 }
            },
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
        const minimapData = {
            nodes: KeenStore.minimapNodesDataSet,
            edges: KeenStore.minimapEdgesDataSet
        };
        KeenStore.minimap = new vis.Network(minimapCanvas, minimapData, minimapOptions);

        setTimeout(() => {
            if (KeenStore.minimap) KeenStore.minimap.fit();
        }, 200);

        KeenStore.minimap.on("afterDrawing", (ctx) => {
            if (!KeenStore.network) return;
            const topLeft = KeenStore.network.DOMtoCanvas({ x: 0, y: 0 });
            const bottomRight = KeenStore.network.DOMtoCanvas({ x: networkCanvas.clientWidth, y: networkCanvas.clientHeight });

            ctx.strokeStyle = "rgba(0, 240, 255, 0.8)";
            ctx.lineWidth = 3;
            ctx.strokeRect(topLeft.x, topLeft.y, bottomRight.x - topLeft.x, bottomRight.y - topLeft.y);
        });

        KeenStore.network.on("afterDrawing", () => {
            if (KeenStore.minimap) KeenStore.minimap.redraw();
        });

        // Interactivity for minimap
        const minimapEl = document.getElementById('graph-minimap');
        if (minimapEl) {
            function handleMinimapAction(e) {
                if (!KeenStore.minimap || !KeenStore.network) return;
                const rect = minimapEl.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;

                // Convert DOM coordinates on the minimap to graph coordinates
                const graphPos = KeenStore.minimap.DOMtoCanvas({ x, y });

                // Move the main network to center on this position
                KeenStore.network.moveTo({
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
        if (!KeenStore.activeWorkspace || !KeenStore.network) return;
        const positions = KeenStore.network.getPositions();
        const formattedPositions = {};
        for (const [id, pos] of Object.entries(positions)) {
            formattedPositions[id] = { x: pos.x, y: pos.y };
        }
        KeenAPI.post(`/workspaces/${KeenStore.activeWorkspace}/nodes/positions`, { positions: formattedPositions });
    }

    // Freeze physics once initial stabilization is done to save CPU
    KeenStore.network.once("stabilizationIterationsDone", function () {
        KeenStore.network.setOptions({ physics: { enabled: false } });
        const btnPhy = document.getElementById('btn-toggle-physics');
        if (btnPhy) btnPhy.classList.remove('active');
        savePositions();
    });

    KeenStore.network.on("dragEnd", function () {
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
        if (KeenStore.network) KeenStore.network.fit();
    };

    if (btnDeleteSelected) btnDeleteSelected.onclick = async () => {
        const selectedNodes = KeenStore.lastSelection ? KeenStore.lastSelection.nodes : [];
        const selectedEdges = KeenStore.lastSelection ? KeenStore.lastSelection.edges : [];

        if (selectedNodes.length === 0 && selectedEdges.length === 0) {
            showSnackbar("Error", "No elements selected.", "error");
            return;
        }

        if (confirm(`Are you sure you want to delete ${selectedNodes.length} node(s) and ${selectedEdges.length} edge(s)?`)) {
            try {
                const nodePromises = selectedNodes.map(id =>
                    KeenAPI.del(`/workspaces/${KeenStore.activeWorkspace}/nodes/${id}`)
                );
                const edgePromises = selectedEdges.map(id =>
                    KeenAPI.del(`/workspaces/${KeenStore.activeWorkspace}/edges/${id}`)
                );

                await Promise.all([...nodePromises, ...edgePromises]);

                // Clear selection
                if (KeenStore.lastSelection) KeenStore.lastSelection = { nodes: [], edges: [] };
                if (KeenStore.network) KeenStore.network.setSelection({ nodes: [], edges: [] });

                // Refresh workspace
                selectWorkspace(KeenStore.activeWorkspace);

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
        KeenStore.network.setOptions({
            layout: { hierarchical: false },
            physics: { enabled: true }
        });
        btnPhysics.classList.add('active');
        KeenStore.network.stabilize();
    };

    if (btnHierarchical) btnHierarchical.onclick = () => {
        clearLayoutButtons();
        btnHierarchical.classList.add('active');
        KeenStore.network.setOptions({
            layout: { hierarchical: { enabled: true, sortMethod: 'directed' } },
            physics: { enabled: false }
        });
        btnPhysics.classList.remove('active');
        setTimeout(savePositions, 500);
    };

    if (btnCircle) btnCircle.onclick = () => {
        clearLayoutButtons();
        btnCircle.classList.add('active');
        KeenStore.network.setOptions({ physics: { enabled: false }, layout: { hierarchical: false } });
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
        KeenStore.network.fit();
        setTimeout(savePositions, 500);
    };

    if (btnPhysics) btnPhysics.onclick = () => {
        const isEnabled = btnPhysics.classList.contains('active');
        if (isEnabled) {
            btnPhysics.classList.remove('active');
            KeenStore.network.setOptions({ physics: { enabled: false } });
        } else {
            btnPhysics.classList.add('active');
            KeenStore.network.setOptions({ physics: { enabled: true } });
        }
    };

    if (btnAddEdge) btnAddEdge.onclick = () => {
        if (btnAddEdge.classList.contains('active')) {
            btnAddEdge.classList.remove('active');
            networkCanvas.style.cursor = 'default';
            KeenStore.network.disableEditMode();
        } else {
            btnAddEdge.classList.add('active');
            networkCanvas.style.cursor = 'crosshair';
            KeenStore.network.addEdgeMode();
        }
    };

    KeenStore.network.on('oncontext', function (params) {
        params.event.preventDefault();
        const nodeId = this.getNodeAt(params.pointer.DOM);
        const edgeId = this.getEdgeAt(params.pointer.DOM);

        if (nodeId) {
            const selectedNode = KeenStore.currentNodes.find(n => n.id === nodeId || n.value === nodeId);
            if (selectedNode) {
                showContextMenu(params.event.pageX, params.event.pageY, selectedNode, null);
            }
        } else if (edgeId) {
            showContextMenu(params.event.pageX, params.event.pageY, null, edgeId);
        } else {
            showContextMenu(params.event.pageX, params.event.pageY, null, null);
        }
    });

    function updateSelectionDisplay(selectedNodeIds, selectedEdgeIds) {
        renderSelectionSummary(selectedNodeIds, selectedEdgeIds);

        // Update labels for all nodes based on selectedNodeIds -- vis-specific
        // (a Cytoscape engine does this itself; see graph-cytoscape.js).
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
    KeenStore.network.updateSelectionDisplay = updateSelectionDisplay;

    // Always track the current selection from vis.js (handles both click and drag)
    KeenStore.network.on('select', function (params) {
        KeenStore.lastSelection = { nodes: params.nodes, edges: params.edges };
        updateSelectionDisplay(params.nodes, params.edges);
    });

    KeenStore.network.on('click', function (params) {
        if (btnAddEdge && btnAddEdge.classList.contains('active')) {
            // If user clicks without drawing an edge, abort edge mode
            btnAddEdge.classList.remove('active');
            networkCanvas.style.cursor = 'default';
            KeenStore.network.disableEditMode();
        }

        contextMenu.classList.add('hidden');
    });
}

// Builds the right-panel "Info" tab content for the current node/edge
// selection (single node, single edge, multi-node, multi-edge, or empty).
export function renderSelectionSummary(selectedNodeIds, selectedEdgeIds) {
    const totalSelected = selectedNodeIds.length + selectedEdgeIds.length;
    const infoEmpty = document.getElementById('node-info-empty');
    const infoContent = document.getElementById('node-info-content');

    if (!infoEmpty || !infoContent) return;

    if (selectedNodeIds.length === 1) {
        const nodeId = selectedNodeIds[0];
        const selectedNode = KeenStore.currentNodes.find(n => String(n.id) === String(nodeId) || n.value === nodeId);
        if (selectedNode) {
            handleNodeSelection(selectedNode);
        }
    } else if (selectedNodeIds.length > 1) {
        // Multi-node select
        infoEmpty.style.display = 'none';
        infoContent.style.display = 'flex';

        let html = `<div style="font-size: 1.1rem; color: var(--text-primary); font-weight: 600; margin-bottom: 12px;">Selection Summary</div>`;
        html += `<div style="margin-bottom: 8px;"><strong style="color: var(--text-primary);">Nodes (${selectedNodeIds.length}):</strong></div>`;
        html += `<div style="display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 12px;">`;
        selectedNodeIds.forEach(id => {
            const node = KeenStore.currentNodes.find(n => String(n.id) === String(id) || n.value === id);
            const val = node ? (node.label || node.value) : id;
            html += `<span class="badge">${val}</span>`;
        });
        html += `</div>`;
        html += `<div style="display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;">`;
        html += `<button id="btn-merge-selected-nodes" class="btn-primary"><i class="fa-solid fa-code-merge"></i> Merge Nodes</button>`;
        html += `<button id="btn-copy-selected-nodes" class="btn-secondary" title="Copy node values (Ctrl+C)"><i class="fa-solid fa-copy"></i> Copy Nodes</button>`;
        html += `</div>`;

        if (selectedEdgeIds.length > 0) {
            html += `<div style="margin-bottom: 8px;"><strong style="color: var(--text-primary);">Edges (${selectedEdgeIds.length}):</strong></div>`;
            html += `<div style="display: flex; flex-wrap: wrap; gap: 4px;">`;
            selectedEdgeIds.forEach(id => {
                const edge = KeenStore.currentEdges.find(e => String(e.id) === String(id));
                const rel = edge ? edge.relationship : id;
                html += `<span class="badge" style="background: rgba(255, 0, 255, 0.1); color: var(--accent-magenta); border-color: rgba(255, 0, 255, 0.2);">${rel}</span>`;
            });
            html += `</div>`;
        }

        infoContent.innerHTML = html;

        const mergeBtn = document.getElementById('btn-merge-selected-nodes');
        if (mergeBtn) mergeBtn.onclick = () => openMergeNodesModal(selectedNodeIds);
        const copyNodesBtn = document.getElementById('btn-copy-selected-nodes');
        if (copyNodesBtn) copyNodesBtn.onclick = () => copySelectionToClipboard(selectedNodeIds, []);

        // Auto-switch to Info tab
        const infoTab = document.querySelector('.right-tab[data-target="tab-node-info"]');
        if (infoTab) infoTab.classList.add('active');
        const infoPanel = document.getElementById('tab-node-info');
        if (infoPanel) infoPanel.classList.add('active');

        moduleSelect.innerHTML = '<option value="" disabled selected>-- Multiple nodes selected --</option>';
        moduleDetails.classList.add('hidden');
    } else if (selectedNodeIds.length === 0 && selectedEdgeIds.length === 1) {
        const edgeId = selectedEdgeIds[0];
        const selectedEdge = KeenStore.currentEdges.find(e => String(e.id) === String(edgeId));
        if (selectedEdge) {
            populateNodeInfo(selectedEdge, true);
            moduleSelect.innerHTML = '<option value="" disabled selected>-- Select a node to run modules --</option>';
            moduleDetails.classList.add('hidden');
        }
    } else if (selectedNodeIds.length === 0 && selectedEdgeIds.length > 1) {
        // Multi-edge select
        infoEmpty.style.display = 'none';
        infoContent.style.display = 'flex';

        let html = `<div style="font-size: 1.1rem; color: var(--text-primary); font-weight: 600; margin-bottom: 12px;">Selection Summary</div>`;
        html += `<div style="margin-bottom: 8px;"><strong style="color: var(--text-primary);">Edges (${selectedEdgeIds.length}):</strong></div>`;
        html += `<div style="display: flex; flex-wrap: wrap; gap: 4px;">`;
        selectedEdgeIds.forEach(id => {
            const edge = KeenStore.currentEdges.find(e => String(e.id) === String(id));
            const rel = edge ? edge.relationship : id;
            html += `<span class="badge" style="background: rgba(255, 0, 255, 0.1); color: var(--accent-magenta); border-color: rgba(255, 0, 255, 0.2);">${rel}</span>`;
        });
        html += `</div>`;
        html += `<button id="btn-copy-selected-edges" class="btn-secondary" style="margin-top: 12px;" title="Copy edges (Ctrl+C)"><i class="fa-solid fa-copy"></i> Copy Edges</button>`;

        infoContent.innerHTML = html;

        const copyEdgesBtn = document.getElementById('btn-copy-selected-edges');
        if (copyEdgesBtn) copyEdgesBtn.onclick = () => copySelectionToClipboard([], selectedEdgeIds);

        // Auto-switch to Info tab
        const infoTab = document.querySelector('.right-tab[data-target="tab-node-info"]');
        if (infoTab) infoTab.classList.add('active');
        const infoPanel = document.getElementById('tab-node-info');
        if (infoPanel) infoPanel.classList.add('active');

        moduleSelect.innerHTML = '<option value="" disabled selected>-- Multiple edges selected --</option>';
        moduleDetails.classList.add('hidden');
    } else {
        // totalSelected === 0
        infoEmpty.style.display = 'flex';
        infoContent.style.display = 'none';
        moduleSelect.innerHTML = '<option value="" disabled selected>-- Select a node to run modules --</option>';
        moduleDetails.classList.add('hidden');
    }
}

export function populateNodeInfo(item, isEdge = false) {
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
                const sourceNode = KeenStore.currentNodes.find(n => n.id === item.source_id) || { value: item.source_id };
                const targetNode = KeenStore.currentNodes.find(n => n.id === item.target_id) || { value: item.target_id };

                infoContent.innerHTML = `
                    <div style="font-size: 1.1rem; color: var(--text-primary); font-weight: 600; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                        <span style="word-break: break-all;">${sourceNode.value}</span>
                        <span style="color: var(--text-secondary); font-size: 0.9rem;"><i class="fa-solid fa-arrow-right-long"></i></span>
                        <span style="word-break: break-all;">${targetNode.value}</span>
                    </div>
                    <div style="margin-bottom: 16px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                        <span class="badge" style="background: rgba(255, 0, 255, 0.1); color: var(--accent-magenta); border-color: rgba(255, 0, 255, 0.2);">${item.relationship}</span>
                        <button id="btn-copy-item" class="btn-secondary" title="Copy edge (Ctrl+C)"><i class="fa-solid fa-copy"></i> Copy</button>
                    </div>
                    ${metadataHtml}
                `;
            } else {
                const displayValue = item.label || item.value;
                const platformBadge = item.platform ? `<span class="badge" style="margin-left: 6px; background: rgba(171, 71, 188, 0.15); color: #ab47bc; border-color: rgba(171, 71, 188, 0.3);">${item.platform}</span>` : '';

                let mediaHtml = '';
                if (item.type === 'media' && KeenStore.activeWorkspace) {
                    const imageUrl = mediaImageUrl(item);
                    const fileUrl = `${KeenAPI.API_BASE}/workspaces/${KeenStore.activeWorkspace}/media/${item.id}/file`;
                    if (imageUrl) {
                        mediaHtml = `<img src="${imageUrl}" alt="media preview" style="max-width: 100%; border-radius: 6px; border: 1px solid var(--border-color); margin-bottom: 12px;">`;
                    } else {
                        mediaHtml = `<a href="${fileUrl}" target="_blank" class="btn-primary" style="display: inline-flex; align-items: center; gap: 6px; margin-bottom: 12px; text-decoration: none;"><i class="fa-solid fa-download"></i> Download attachment</a>`;
                    }
                }

                infoContent.innerHTML = `
                    <div style="font-size: 1.1rem; color: var(--text-primary); font-weight: 600; margin-bottom: 4px; word-break: break-all;">${displayValue}</div>
                    <div style="margin-bottom: 16px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                        <span class="badge">${item.type}</span>${platformBadge}${item.timestamp ? `<span class="badge" style="margin-left: 6px;">${item.timestamp}</span>` : ''}
                        <button id="btn-copy-item" class="btn-secondary" title="Copy node value (Ctrl+C)"><i class="fa-solid fa-copy"></i> Copy</button>
                    </div>
                    ${mediaHtml}
                    ${metadataHtml}
                `;
            }

            const copyItemBtn = document.getElementById('btn-copy-item');
            if (copyItemBtn) {
                copyItemBtn.onclick = () => {
                    if (isEdge) {
                        copyEdgeToClipboard(item);
                    } else {
                        copyNodeToClipboard(item);
                    }
                };
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

export function handleNodeSelection(node) {
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

export function showContextMenu(x, y, node, edgeId = null) {
    contextMenuItems.innerHTML = '';

    if (!node && edgeId === null) {
        // Right-clicked empty canvas -- no node/edge under the cursor, so
        // module-running/edit/delete don't apply. Offer canvas-level actions
        // instead (create a node from scratch, or paste one from clipboard).
        const addNodeItem = document.createElement('div');
        addNodeItem.className = 'context-menu-item';
        addNodeItem.innerHTML = `<i class="fa-solid fa-plus"></i> Add Node`;
        addNodeItem.onclick = (e) => {
            e.stopPropagation();
            contextMenu.classList.add('hidden');
            openCreateNodeModal();
        };
        contextMenuItems.appendChild(addNodeItem);

        const hasNodeClipboard = KeenStore.nodeClipboard && KeenStore.nodeClipboard.length > 0;
        const pasteItem = document.createElement('div');
        pasteItem.className = 'context-menu-item';
        const pasteLabel = hasNodeClipboard
            ? (KeenStore.nodeClipboard.length > 1 ? `Paste ${KeenStore.nodeClipboard.length} Nodes` : 'Paste Node')
            : 'Paste as New Node';
        pasteItem.innerHTML = `<i class="fa-solid fa-paste"></i> ${pasteLabel}`;
        pasteItem.onclick = (e) => {
            e.stopPropagation();
            contextMenu.classList.add('hidden');
            pasteFromClipboard();
        };
        contextMenuItems.appendChild(pasteItem);

        contextMenu.style.left = `${x}px`;
        contextMenu.style.top = `${y}px`;
        contextMenu.classList.remove('hidden');
        return;
    }

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

        const copyEdgeItem = document.createElement('div');
        copyEdgeItem.className = 'context-menu-item';
        copyEdgeItem.innerHTML = `<i class="fa-solid fa-copy"></i> Copy Edge`;
        copyEdgeItem.onclick = (e) => {
            e.stopPropagation();
            contextMenu.classList.add('hidden');
            const edge = KeenStore.currentEdges.find(ed => String(ed.id) === String(edgeId));
            copyEdgeToClipboard(edge);
        };
        contextMenuItems.appendChild(copyEdgeItem);

        const deleteEdgeItem = document.createElement('div');
        deleteEdgeItem.className = 'context-menu-item';
        deleteEdgeItem.style.color = 'var(--error)';
        deleteEdgeItem.innerHTML = `<i class="fa-solid fa-trash"></i> Delete Edge`;
        deleteEdgeItem.onclick = (e) => {
            e.stopPropagation();
            contextMenu.classList.add('hidden');
            if (confirm("Delete this edge?")) {
                KeenAPI.del(`/workspaces/${KeenStore.activeWorkspace}/edges/${edgeId}`)
                    .then(() => selectWorkspace(KeenStore.activeWorkspace))
                    .catch(() => showSnackbar('Edges', 'Failed to delete edge.', 'error', 5000));
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

    for (const key of Object.keys(KeenStore.modulesData).sort()) {
        const mod = KeenStore.modulesData[key];
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

    const copyNodeItem = document.createElement('div');
    copyNodeItem.className = 'context-menu-item';
    copyNodeItem.innerHTML = `<i class="fa-solid fa-copy"></i> Copy Node`;
    copyNodeItem.onclick = (e) => {
        e.stopPropagation();
        contextMenu.classList.add('hidden');
        copyNodeToClipboard(node);
    };
    contextMenuItems.appendChild(copyNodeItem);

    const deleteItem = document.createElement('div');
    deleteItem.className = 'context-menu-item';
    deleteItem.style.color = 'var(--error)';
    deleteItem.style.marginTop = '4px';
    deleteItem.innerHTML = `<i class="fa-solid fa-trash"></i> Delete Node`;
    deleteItem.onclick = (e) => {
        e.stopPropagation();
        contextMenu.classList.add('hidden');
        if (confirm("Delete this node? This will also cascade delete any connected edges.")) {
            KeenAPI.del(`/workspaces/${KeenStore.activeWorkspace}/nodes/${node.id || node.value}`)
                .then(() => selectWorkspace(KeenStore.activeWorkspace))
                .catch(() => showSnackbar('Nodes', 'Failed to delete node.', 'error', 5000));
        }
    };
    contextMenuItems.appendChild(deleteItem);

    contextMenu.style.left = `${x}px`;
    contextMenu.style.top = `${y}px`;
    contextMenu.classList.remove('hidden');
}

// --- Entity resolution (node merging) ---
// merge_nodes() on the backend (managers.py) is whole-node precedence, not
// field-level: the canonical node always wins metadata conflicts, absorbed
// nodes only fill keys canonical lacks. The preview below mirrors that fold
// exactly so there's no surprise between what's shown and what the server does.

let mergeCandidateNodes = [];

function parseNodeMeta(node) {
    if (!node || !node.metadata) return {};
    try {
        const meta = typeof node.metadata === 'string' ? JSON.parse(node.metadata) : node.metadata;
        return (meta && typeof meta === 'object') ? meta : {};
    } catch (e) {
        return {};
    }
}

export function openMergeNodesModal(selectedNodeIds) {
    mergeCandidateNodes = selectedNodeIds
        .map(id => KeenStore.currentNodes.find(n => String(n.id) === String(id) || n.value === id))
        .filter(Boolean);

    if (mergeCandidateNodes.length < 2) {
        showSnackbar('Merge', 'Select at least two nodes to merge.', 'error', 4000);
        return;
    }

    mergeNodesList.innerHTML = '';
    mergeCandidateNodes.forEach((node, i) => {
        const row = document.createElement('label');
        row.style.cssText = 'display: flex; align-items: center; gap: 8px; padding: 8px; border: 1px solid var(--border-color); border-radius: 6px; cursor: pointer;';
        row.innerHTML = `
            <input type="radio" name="merge-canonical" value="${node.id}" ${i === 0 ? 'checked' : ''}>
            <span class="badge">${node.type}</span>
            <span style="word-break: break-all;">${node.label || node.value}</span>
        `;
        mergeNodesList.appendChild(row);
    });

    mergeNodesList.querySelectorAll('input[name="merge-canonical"]').forEach(input => {
        input.addEventListener('change', renderMergePreview);
    });

    renderMergePreview();
    modalMergeNodes.classList.add('active');
}

function renderMergePreview() {
    const checked = mergeNodesList.querySelector('input[name="merge-canonical"]:checked');
    const canonicalNode = checked
        ? mergeCandidateNodes.find(n => String(n.id) === String(checked.value))
        : null;

    if (!canonicalNode) {
        mergePreview.textContent = '';
        return;
    }

    const absorbedNodes = mergeCandidateNodes.filter(n => n !== canonicalNode);
    let merged = parseNodeMeta(canonicalNode);
    const mergedFrom = Array.isArray(merged.merged_from) ? [...merged.merged_from] : [];
    for (const absorbed of absorbedNodes) {
        merged = { ...parseNodeMeta(absorbed), ...merged };
        mergedFrom.push(absorbed.label || absorbed.value);
    }
    merged = { ...merged, merged_from: mergedFrom };

    mergePreview.textContent = JSON.stringify(merged, null, 2);
}

export function getMergeSelection() {
    const checked = mergeNodesList.querySelector('input[name="merge-canonical"]:checked');
    if (!checked) return null;
    const canonicalId = checked.value;
    const absorbedIds = mergeCandidateNodes
        .filter(n => String(n.id) !== String(canonicalId))
        .map(n => n.id);
    if (absorbedIds.length === 0) return null;
    return { canonicalId: Number(canonicalId), absorbedIds: absorbedIds.map(Number) };
}
