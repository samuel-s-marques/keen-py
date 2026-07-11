/*
 * Cytoscape.js graph renderer -- the opt-in alternative to vis-network
 * (graph.js). Behind the `KeenStore.graphEngine` toggle so vis-network
 * stays the default until this has real-world mileage.
 *
 * Mirrors just enough of vis.Network's method surface on KeenStore.network
 * (setSelection, focus, setSize, redraw, fit, updateSelectionDisplay,
 * destroy, disableEditMode) for the rest of the app -- main.js, layout.js,
 * workspaces.js, the merge-nodes UI -- to keep working unchanged regardless
 * of which engine drew the graph. Everything else (layouts, minimap, context
 * menu, position save) is internal to this module and talks to the
 * Cytoscape instance directly.
 */
import { networkCanvas, contextMenu } from "./dom.js";
import { showSnackbar } from "./notifications.js";
import { selectWorkspace } from "./workspaces.js";
import { getNodeStyle } from "./graph-styles.js";
import { showContextMenu, renderSelectionSummary } from "./graph.js";

// cytoscape/cytoscape-fcose/dagre/cytoscape-dagre load as classic <script>
// globals (see index.html) -- register the layout extensions once, here,
// rather than at every drawGraphCytoscape() call.
if (typeof cytoscape !== 'undefined' && typeof cytoscapeFcose !== 'undefined') {
    cytoscape.use(cytoscapeFcose);
}
if (typeof cytoscape !== 'undefined' && typeof cytoscapeDagre !== 'undefined') {
    cytoscape.use(cytoscapeDagre);
}

// Higher = closer to the center in Cytoscape's concentric layout, matching
// "center = organizations, outer ring = subdomains, outer-most ring =
// IP addresses" grouping.
const CONCENTRIC_TIER = [
    ['organization', 3],
    ['person', 3],
    ['domain', 2],
    ['url', 2],
];

function concentricLevel(type) {
    const t = type || '';
    for (const [needle, level] of CONCENTRIC_TIER) {
        if (t.includes(needle)) return level;
    }
    return 1;
}

// Shared spacing tuning for fcose so isolated close-together nodes and
// their labels don't visually merge -- the fcose defaults are tuned for
// small/sparse graphs and cluster too tightly on a typical case graph.
const FCOSE_SPACING = {
    nodeRepulsion: 9000,
    idealEdgeLength: 100,
    nodeSeparation: 100,
    nodeDimensionsIncludeLabels: true,
    packComponents: true,
};

let cy = null;
let minimapCy = null;
let groupByTypeActive = false;
let edgeDrawSourceId = null;

function isLightTheme() {
    return document.documentElement.getAttribute('data-theme') === 'light';
}

// Cytoscape requires every element id -- nodes AND edges together -- to be
// unique in one shared namespace. Nodes and edges come from separate `nodes`/
// `edge` DB tables with independently auto-incrementing primary keys, so a
// node #7 and an edge #7 both existing (increasingly likely as a case grows)
// collide once passed through unprefixed. Namespace each id by element kind
// to make that structurally impossible, and keep the raw id in its own field
// (`rawId`) since the rest of the app (KeenStore.currentNodes/currentEdges,
// selection tracking, context menu, merge modal, position save) all key off
// the raw un-prefixed id, not Cytoscape's internal one.
const NODE_ID_PREFIX = 'n:';
const EDGE_ID_PREFIX = 'e:';

function buildElements(nodes, edges, { groupByType = false } = {}) {
    const groupIds = new Set();
    const nodeEls = nodes.map(n => {
        const { color } = getNodeStyle(n.type);
        const rawId = String(n.id || n.value);
        const fullLabel = n.label || n.value;
        const shortLabel = fullLabel.length > 20 ? fullLabel.substring(0, 18) + '...' : fullLabel;
        const el = {
            data: {
                id: NODE_ID_PREFIX + rawId,
                rawId,
                type: n.type,
                color,
                fullLabel,
                shortLabel,
                displayLabel: shortLabel,
                concentric: concentricLevel(n.type),
            },
        };
        if (groupByType) {
            const groupId = `group:${n.type}`;
            groupIds.add(groupId);
            el.data.parent = groupId;
        }
        if (n.x !== null && n.x !== undefined && n.y !== null && n.y !== undefined) {
            el.position = { x: n.x, y: n.y };
        }
        return el;
    });

    const groupEls = Array.from(groupIds).map(groupId => ({
        data: { id: groupId, displayLabel: groupId.replace('group:', ''), isGroup: true },
    }));

    const edgeEls = edges.map(e => {
        const rawId = String(e.id);
        return {
            data: {
                id: EDGE_ID_PREFIX + rawId,
                rawId,
                source: NODE_ID_PREFIX + String(e.source_id),
                target: NODE_ID_PREFIX + String(e.target_id),
                relationship: e.relationship,
                displayLabel: (e.relationship || '').replace(/[_-]/g, ' '),
            },
        };
    });

    return [...groupEls, ...nodeEls, ...edgeEls];
}

function buildStyle() {
    const light = isLightTheme();
    const textColor = light ? '#1a1c23' : '#f0f2f8';
    // Cytoscape's style-value parser rejects 8-digit hex (RRGGBBAA) colors --
    // unlike vis-network/CSS4, it only accepts hex3/hex6/rgb()/rgba()/hsl(),
    // so the same translucent edge color needs rgba() form here.
    const edgeColor = light ? 'rgba(26, 28, 35, 0.33)' : 'rgba(139, 146, 165, 0.53)';
    const bgColor = light ? '#ffffff' : '#111318';
    return [
        {
            selector: 'node',
            style: {
                'background-color': 'data(color)',
                'label': 'data(displayLabel)',
                'color': textColor,
                'font-size': 10,
                'text-valign': 'bottom',
                'text-margin-y': 6,
                'width': 26,
                'height': 26,
                'border-width': 2,
                'border-color': light ? 'rgba(0,0,0,0.15)' : 'rgba(255,255,255,0.15)',
            },
        },
        {
            selector: 'node:selected',
            style: {
                'border-width': 3,
                'border-color': '#00f0ff',
            },
        },
        {
            selector: 'node[?isGroup]',
            style: {
                'background-opacity': 0.12,
                'border-width': 1,
                'border-style': 'dashed',
                'border-color': light ? 'rgba(0,0,0,0.3)' : 'rgba(255,255,255,0.3)',
                'label': 'data(displayLabel)',
                'text-valign': 'top',
                'text-halign': 'center',
                'font-size': 12,
                'color': textColor,
                'shape': 'round-rectangle',
            },
        },
        {
            selector: 'edge',
            style: {
                'width': 1.5,
                'line-color': edgeColor,
                'target-arrow-color': edgeColor,
                'target-arrow-shape': 'triangle',
                'arrow-scale': 0.8,
                // 'bezier' auto-bundles multiple edges between the same node
                // pair, curving them apart -- but the default separation is
                // subtle, so bump control-point-step-size to make it visible
                // rather than have them still read as one overlapping line.
                'curve-style': 'bezier',
                'control-point-step-size': 40,
                'label': 'data(displayLabel)',
                'font-size': 9,
                'color': textColor,
                'text-rotation': 'autorotate',
                'text-background-color': bgColor,
                'text-background-opacity': 0.7,
                'text-background-padding': 1,
            },
        },
        {
            selector: 'edge:selected',
            style: {
                'width': 3,
                'line-color': '#ff00ff',
                'target-arrow-color': '#ff00ff',
            },
        },
    ];
}

function savePositions() {
    if (!KeenStore.activeWorkspace || !cy) return;
    const positions = {};
    cy.nodes().not('[?isGroup]').forEach(n => {
        positions[n.data('rawId')] = n.position();
    });
    KeenAPI.post(`/workspaces/${KeenStore.activeWorkspace}/nodes/positions`, { positions });
}

function updateSelectionDisplay(selectedNodeIds, selectedEdgeIds) {
    renderSelectionSummary(selectedNodeIds, selectedEdgeIds);
    if (!cy) return;
    cy.nodes().not('[?isGroup]').forEach(n => {
        const isSelected = selectedNodeIds.includes(n.data('rawId'));
        n.data('displayLabel', isSelected ? n.data('fullLabel') : n.data('shortLabel'));
    });
}

function wireSelectionTracking() {
    cy.on('select unselect', () => {
        const nodes = cy.nodes(':selected').not('[?isGroup]').map(n => n.data('rawId'));
        const edges = cy.edges(':selected').map(e => e.data('rawId'));
        KeenStore.lastSelection = { nodes, edges };
        updateSelectionDisplay(nodes, edges);
    });
}

function wireContextMenu() {
    cy.on('cxttap', 'node', (evt) => {
        if (evt.target.data('isGroup')) return;
        evt.originalEvent.preventDefault();
        const nodeId = evt.target.data('rawId');
        const selectedNode = KeenStore.currentNodes.find(n => String(n.id) === nodeId || n.value === nodeId);
        if (selectedNode) showContextMenu(evt.originalEvent.pageX, evt.originalEvent.pageY, selectedNode, null);
    });
    cy.on('cxttap', 'edge', (evt) => {
        evt.originalEvent.preventDefault();
        showContextMenu(evt.originalEvent.pageX, evt.originalEvent.pageY, null, evt.target.data('rawId'));
    });
    cy.on('cxttap', (evt) => {
        if (evt.target === cy) contextMenu.classList.add('hidden');
    });
    cy.on('tap', (evt) => {
        // Cytoscape fires a generic 'tap' alongside 'cxttap' for the same
        // right-click gesture in some browsers -- without this guard, this
        // handler's unconditional hide would immediately undo the menu the
        // 'cxttap' handler above just opened.
        if (evt.originalEvent && evt.originalEvent.button === 2) return;
        contextMenu.classList.add('hidden');
        if (edgeDrawSourceId !== null && evt.target !== cy && !evt.target.data('isGroup') && evt.target.isNode && evt.target.isNode()) {
            const targetId = evt.target.data('rawId');
            if (targetId !== edgeDrawSourceId) {
                const rel = prompt("Enter relationship (e.g. resolves-to, belongs-to):");
                if (rel) {
                    KeenAPI.post(`/workspaces/${KeenStore.activeWorkspace}/edges`, {
                        source_id: edgeDrawSourceId,
                        target_id: targetId,
                        relationship: rel,
                    }).then(res => {
                        if (res.ok) selectWorkspace(KeenStore.activeWorkspace);
                    });
                }
            }
            exitEdgeDrawMode();
        }
    });
}

function exitEdgeDrawMode() {
    edgeDrawSourceId = null;
    const btnAddEdge = document.getElementById('btn-add-edge');
    if (btnAddEdge) btnAddEdge.classList.remove('active');
    networkCanvas.style.cursor = 'default';
}

function wireToolbar() {
    const btnForce = document.getElementById('btn-layout-force');
    const btnHierarchical = document.getElementById('btn-layout-hierarchical');
    const btnCircle = document.getElementById('btn-layout-circle');
    const btnConcentric = document.getElementById('btn-layout-concentric');
    const btnGroupByType = document.getElementById('btn-group-by-type');
    const btnPhysics = document.getElementById('btn-toggle-physics');
    const btnAddEdge = document.getElementById('btn-add-edge');
    const btnFitScreen = document.getElementById('btn-fit-screen');
    const btnDeleteSelected = document.getElementById('btn-delete-selected');

    function clearLayoutButtons() {
        [btnForce, btnHierarchical, btnCircle, btnConcentric].forEach(b => b && b.classList.remove('active'));
    }

    function runLayout(opts) {
        cy.layout({ animate: true, animationDuration: 400, fit: true, ...opts }).run();
        setTimeout(savePositions, 500);
    }

    if (btnForce) btnForce.onclick = () => {
        clearLayoutButtons();
        btnForce.classList.add('active');
        runLayout({ name: 'fcose', randomize: false, ...FCOSE_SPACING });
    };
    if (btnHierarchical) btnHierarchical.onclick = () => {
        clearLayoutButtons();
        btnHierarchical.classList.add('active');
        runLayout({ name: 'dagre', rankDir: 'TB', nodeSep: 60, rankSep: 80, edgeSep: 30 });
    };
    if (btnCircle) btnCircle.onclick = () => {
        clearLayoutButtons();
        btnCircle.classList.add('active');
        runLayout({ name: 'circle', spacingFactor: 1.5, nodeDimensionsIncludeLabels: true });
    };
    if (btnConcentric) btnConcentric.onclick = () => {
        clearLayoutButtons();
        btnConcentric.classList.add('active');
        runLayout({
            name: 'concentric',
            concentric: (node) => node.data('concentric') || 1,
            levelWidth: () => 1,
            minNodeSpacing: 60,
            nodeDimensionsIncludeLabels: true,
        });
    };
    if (btnGroupByType) btnGroupByType.onclick = () => {
        groupByTypeActive = !groupByTypeActive;
        btnGroupByType.classList.toggle('active', groupByTypeActive);
        drawGraphCytoscape(KeenStore.currentNodes, KeenStore.currentEdges);
    };
    if (btnPhysics) btnPhysics.onclick = () => {
        // Cytoscape's force layouts are one-shot, not a continuous physics
        // simulation like vis-network -- "physics" here just re-runs fcose.
        runLayout({ name: 'fcose', randomize: false, ...FCOSE_SPACING });
    };
    if (btnFitScreen) btnFitScreen.onclick = () => cy.fit();
    if (btnAddEdge) btnAddEdge.onclick = () => {
        if (btnAddEdge.classList.contains('active')) {
            exitEdgeDrawMode();
        } else {
            btnAddEdge.classList.add('active');
            networkCanvas.style.cursor = 'crosshair';
            edgeDrawSourceId = null;
            // First click after entering the mode arms the source node; the
            // handler lives in wireContextMenu's 'tap' listener alongside the
            // rest of click-driven interaction, since Cytoscape has no
            // built-in drag-to-connect edit mode like vis-network's.
            cy.one('tap', 'node', (evt) => {
                if (!btnAddEdge.classList.contains('active') || evt.target.data('isGroup')) return;
                edgeDrawSourceId = evt.target.data('rawId');
            });
        }
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
                await Promise.all([
                    ...selectedNodes.map(id => KeenAPI.del(`/workspaces/${KeenStore.activeWorkspace}/nodes/${id}`)),
                    ...selectedEdges.map(id => KeenAPI.del(`/workspaces/${KeenStore.activeWorkspace}/edges/${id}`)),
                ]);
                KeenStore.lastSelection = { nodes: [], edges: [] };
                selectWorkspace(KeenStore.activeWorkspace);
                showSnackbar("Success", "Selected items deleted successfully.", "success");
            } catch (e) {
                showSnackbar("Error", "Failed to delete some items.", "error");
            }
        }
    };
}

function buildMinimap() {
    const minimapCanvas = document.getElementById('minimap-canvas');
    if (minimapCy) {
        minimapCy.destroy();
        minimapCy = null;
    }
    if (!minimapCanvas) return;

    minimapCy = cytoscape({
        container: minimapCanvas,
        elements: cy.elements().jsons(),
        style: buildStyle(),
        layout: { name: 'preset' },
        userPanningEnabled: false,
        userZoomingEnabled: false,
        boxSelectionEnabled: false,
        autoungrabify: true,
        autounselectify: true,
    });
    minimapCy.nodes().forEach(n => n.style({ label: '', width: 6, height: 6 }));
    minimapCy.edges().forEach(e => e.style({ label: '', width: 1 }));
    minimapCy.fit();

    let overlay = document.getElementById('cy-minimap-viewport');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'cy-minimap-viewport';
        overlay.style.cssText = 'position:absolute; border:2px solid rgba(0,240,255,0.8); pointer-events:none;';
        minimapCanvas.style.position = 'relative';
        minimapCanvas.appendChild(overlay);
    }

    function updateViewportRect() {
        if (!cy || !minimapCy) return;
        const ext = cy.extent(); // main viewport's bounding box, in model coords
        const mz = minimapCy.zoom();
        const mp = minimapCy.pan();
        const x1 = ext.x1 * mz + mp.x;
        const y1 = ext.y1 * mz + mp.y;
        const w = (ext.x2 - ext.x1) * mz;
        const h = (ext.y2 - ext.y1) * mz;
        overlay.style.left = `${x1}px`;
        overlay.style.top = `${y1}px`;
        overlay.style.width = `${Math.max(4, w)}px`;
        overlay.style.height = `${Math.max(4, h)}px`;
    }
    cy.on('pan zoom position', updateViewportRect);
    cy.on('layoutstop', updateViewportRect);
    setTimeout(updateViewportRect, 300);

    function handleMinimapNav(evt) {
        const rect = minimapCanvas.getBoundingClientRect();
        const x = evt.clientX - rect.left;
        const y = evt.clientY - rect.top;
        const mz = minimapCy.zoom();
        const mp = minimapCy.pan();
        const modelX = (x - mp.x) / mz;
        const modelY = (y - mp.y) / mz;
        cy.center({ position: { x: modelX, y: modelY } });
    }
    minimapCanvas.onclick = handleMinimapNav;
}

// Adapter exposing just the vis.Network methods the rest of the app calls on
// KeenStore.network regardless of which engine drew the graph -- see the
// module docstring for exactly which ones and why this list is short.
function makeAdapter() {
    return {
        setSelection({ nodes = [], edges = [] } = {}) {
            cy.elements().unselect();
            nodes.forEach(id => {
                const el = cy.getElementById(NODE_ID_PREFIX + String(id));
                if (el.length) el.select();
            });
            edges.forEach(id => {
                const el = cy.getElementById(EDGE_ID_PREFIX + String(id));
                if (el.length) el.select();
            });
        },
        focus(id) {
            const el = cy.getElementById(NODE_ID_PREFIX + String(id));
            if (el.length) cy.center(el);
        },
        setSize() {
            cy.resize();
        },
        redraw() {
            cy.resize();
        },
        fit() {
            cy.fit();
        },
        updateSelectionDisplay,
        destroy() {
            if (cy) {
                cy.destroy();
                cy = null;
            }
            if (minimapCy) {
                minimapCy.destroy();
                minimapCy = null;
            }
        },
        disableEditMode() {
            exitEdgeDrawMode();
        },
    };
}

export function drawGraphCytoscape(nodes, edges) {
    KeenStore.lastSelection = { nodes: [], edges: [] };

    if (cy) {
        cy.destroy();
        cy = null;
    }

    cy = cytoscape({
        container: networkCanvas,
        elements: buildElements(nodes, edges, { groupByType: groupByTypeActive }),
        style: buildStyle(),
        layout: nodes.some(n => n.x !== null && n.x !== undefined)
            ? { name: 'preset' }
            : { name: 'fcose', randomize: false, ...FCOSE_SPACING },
        wheelSensitivity: 0.2,
    });

    KeenStore.network = makeAdapter();

    wireSelectionTracking();
    wireContextMenu();
    wireToolbar();
    buildMinimap();

    cy.on('dragfree', 'node', () => savePositions());
    cy.on('layoutstop', () => savePositions());
}
