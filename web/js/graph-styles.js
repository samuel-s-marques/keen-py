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
