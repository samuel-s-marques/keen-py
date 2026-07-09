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
} from "./dom.js";
import { showSnackbar } from "./notifications.js";
import { selectWorkspace } from "./workspaces.js";
import {
    NODE_TO_VALIDATOR_MAP,
    buildModuleDropdown,
    runModuleImmediately,
    runMagicChainingImmediately,
} from "./modules.js";
import { openEditEdgeModal, openEditNodeModal } from "./modals.js";

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

export function drawGraph(nodes, edges) {
    let allHavePositions = nodes.length > 0;
    KeenStore.lastSelection = { nodes: [], edges: [] };

    const visNodes = nodes.map(n => {
        let icon = ''; // fa-circle default
        let color = '#8b92a5';

        if (n.type.includes('email')) { icon = ''; color = '#0072ff'; }
        else if (n.type.includes('domain')) { icon = ''; color = '#00f0ff'; }
        else if (n.type.includes('ip')) { icon = ''; color = '#ff00ff'; }
        else if (n.type.includes('phone')) { icon = ''; color = '#00e676'; }
        else if (n.type.includes('person')) { icon = ''; color = '#ff6f61'; }
        else if (n.type.includes('user-account')) { icon = ''; color = '#ab47bc'; }
        else if (n.type.includes('organization')) { icon = ''; color = '#ffb300'; }
        else if (n.type.includes('url')) { icon = ''; color = '#26c6da'; }
        else if (n.type.includes('breach')) { icon = ''; color = '#ff5252'; }
        else if (n.type.includes('service')) { icon = ''; color = '#ffa726'; }

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

    const minimapVisNodes = visNodes.map(n => ({
        ...n,
        icon: n.icon ? { ...n.icon, size: 12 } : undefined,
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
                    const promises = data.nodes.map(id => KeenAPI.del(`/workspaces/${KeenStore.activeWorkspace}/nodes/${id}`));
                    Promise.all(promises).then(() => {
                        callback(data);
                        selectWorkspace(KeenStore.activeWorkspace);
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
                    const promises = data.edges.map(id => KeenAPI.del(`/workspaces/${KeenStore.activeWorkspace}/edges/${id}`));
                    Promise.all(promises).then(() => {
                        callback(data);
                        selectWorkspace(KeenStore.activeWorkspace);
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
                    KeenAPI.post(`/workspaces/${KeenStore.activeWorkspace}/edges`, {
                            source_id: String(edgeData.from),
                            target_id: String(edgeData.to),
                            relationship: rel
                        }).then(res => {
                        if (res.ok) {
                            callback(edgeData);
                            selectWorkspace(KeenStore.activeWorkspace);
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
            contextMenu.classList.add('hidden');
        }
    });

    function updateSelectionDisplay(selectedNodeIds, selectedEdgeIds) {
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

            infoContent.innerHTML = html;

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
                KeenAPI.del(`/workspaces/${KeenStore.activeWorkspace}/edges/${edgeId}`)
                    .then(() => selectWorkspace(KeenStore.activeWorkspace))
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
                .catch(() => alert("Failed to delete node."));
        }
    };
    contextMenuItems.appendChild(deleteItem);

    contextMenu.style.left = `${x}px`;
    contextMenu.style.top = `${y}px`;
    contextMenu.classList.remove('hidden');
}
