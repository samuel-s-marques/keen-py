/*
 * World View: plot every node carrying stix2 latitude/longitude on a Leaflet
 * map. Reads from KeenStore.currentNodes (the same node list the Graph/Nodes/
 * Edges tabs already populate) -- no separate REST endpoint needed, since the
 * existing GET /nodes response already includes full metadata.
 */

let worldMap = null;
let markerLayer = null;

function ensureMap() {
    if (worldMap) return worldMap;

    worldMap = L.map('world-map-canvas', { worldCopyJump: true }).setView([20, 0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(worldMap);
    markerLayer = L.layerGroup().addTo(worldMap);

    return worldMap;
}

function geolocatedNodes() {
    return (KeenStore.currentNodes || []).filter(n => {
        const stix2 = n.metadata && n.metadata.stix2;
        return stix2
            && typeof stix2.latitude === 'number'
            && typeof stix2.longitude === 'number';
    });
}

export function refreshWorldMap() {
    const canvas = document.getElementById('world-map-canvas');
    if (!canvas) return;
    const map = ensureMap();
    markerLayer.clearLayers();

    const nodes = geolocatedNodes();
    const emptyEl = document.getElementById('world-map-empty');
    if (emptyEl) emptyEl.style.display = nodes.length ? 'none' : 'flex';
    if (!nodes.length) return;

    const bounds = [];
    nodes.forEach(n => {
        const { latitude, longitude } = n.metadata.stix2;
        const label = n.label || n.value || n.type;
        L.marker([latitude, longitude])
            .bindPopup(`<strong>${n.type}</strong><br>${label}`)
            .addTo(markerLayer);
        bounds.push([latitude, longitude]);
    });

    if (bounds.length === 1) {
        map.setView(bounds[0], 10);
    } else {
        map.fitBounds(bounds, { padding: [30, 30] });
    }
}

export function invalidateWorldMapSize() {
    if (worldMap) {
        // Leaflet computes tile layout from the container's size at init time;
        // a map created (or resized) while its tab is hidden ends up with a
        // stale/zero size until told to recompute.
        setTimeout(() => worldMap.invalidateSize(), 0);
    }
}
