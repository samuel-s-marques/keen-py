/*
 * Node type -> {icon, color} lookup shared by both graph renderers
 * (vis-network in graph.js, Cytoscape.js in graph-cytoscape.js) so the two
 * engines stay visually consistent and the FontAwesome codepoints only live
 * in one place. Icons are written as \uXXXX escapes (not raw glyphs) so the
 * private-use-area FontAwesome codepoints survive any editor/encoding
 * round-trip unambiguously.
 */

const DEFAULT_STYLE = { icon: '', color: '#8b92a5' }; // fa-circle

const NODE_STYLE_RULES = [
    ['email', { icon: '', color: '#0072ff' }], // fa-envelope
    ['domain', { icon: '', color: '#00f0ff' }], // fa-globe
    ['ip', { icon: '', color: '#ff00ff' }], // fa-server
    ['phone', { icon: '', color: '#00e676' }], // fa-phone
    ['person', { icon: '', color: '#ff6f61' }], // fa-user
    ['user-account', { icon: '', color: '#ab47bc' }], // fa-id-badge
    ['organization', { icon: '', color: '#ffb300' }], // fa-building
    ['url', { icon: '', color: '#26c6da' }], // fa-link
    ['breach', { icon: '', color: '#ff5252' }], // fa-triangle-exclamation
    ['service', { icon: '', color: '#ffa726' }], // fa-server
];

export function getNodeStyle(type) {
    const t = type || '';
    for (const [needle, style] of NODE_STYLE_RULES) {
        if (t.includes(needle)) return style;
    }
    return DEFAULT_STYLE;
}

/**
 * URL to a media node's own stored image bytes, or null if this node isn't
 * an image with a retrievable attachment. Shared by both renderers so a
 * node showing hundreds of imported photos/avatars reads as thumbnails at a
 * glance instead of an undifferentiated wall of hash/id labels the operator
 * would otherwise have to click through one at a time.
 */
export function mediaImageUrl(node) {
    if (!node || node.type !== 'media' || !KeenStore.activeWorkspace) return null;
    const meta = (node.metadata && typeof node.metadata === 'object') ? node.metadata : {};
    if (meta.media_type !== 'image' || !meta.attachment_ref) return null;
    if (!node.id) return null;
    return `${KeenAPI.API_BASE}/workspaces/${KeenStore.activeWorkspace}/media/${node.id}/file`;
}
