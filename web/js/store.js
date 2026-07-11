/*
 * Keen frontend state store — one place for cross-cutting app state that used
 * to live as loose `let` variables inside the app.js closure.
 *
 * Exposed as `window.KeenStore` (classic script, loaded before app.js).
 * Intentionally tiny: a plain state object plus a minimal pub/sub so views can
 * react to changes without threading the values through every function.
 *
 *   KeenStore.activeWorkspace            // read
 *   KeenStore.setActiveWorkspace(name)   // write + notify subscribers
 *   KeenStore.subscribe("activeWorkspace", (val) => { ... })
 */
(function () {
    "use strict";

    const _listeners = {}; // key -> [fn, ...]

    function _emit(key, value) {
        (_listeners[key] || []).forEach(function (fn) {
            try {
                fn(value);
            } catch (e) {
                console.error("KeenStore listener error for '" + key + "':", e);
            }
        });
    }

    const store = {
        // --- state ---
        activeWorkspace: null,
        isConfigUnlocked: false,

        // Shared mutable app state (formerly loose `let`s in the app.js closure).
        // Feature modules read/write these as KeenStore.<name>.
        modulesData: {},
        graphEngine: 'cytoscape', // 'cytoscape' (default) or 'vis'
        network: null,
        nodesDataSet: null,
        edgesDataSet: null,
        currentWorkspace: null,
        lastSelection: { nodes: [], edges: [] },
        minimap: null,
        minimapNodesDataSet: null,
        minimapEdgesDataSet: null,
        configKeys: {},
        currentNodes: [],
        currentEdges: [],
        activeSockets: [],
        activeSocketsMap: new Map(),
        currentWorkspaces: [],
        timelineTimestamps: [],
        isTimelinePlaying: false,
        timelineTimer: null,
        aiPollingInterval: null,

        // --- mutators (notify subscribers) ---
        setActiveWorkspace: function (name) {
            this.activeWorkspace = name || null;
            _emit("activeWorkspace", this.activeWorkspace);
        },
        setConfigUnlocked: function (unlocked) {
            this.isConfigUnlocked = !!unlocked;
            _emit("isConfigUnlocked", this.isConfigUnlocked);
        },

        // --- subscription ---
        subscribe: function (key, fn) {
            (_listeners[key] = _listeners[key] || []).push(fn);
            return function unsubscribe() {
                const arr = _listeners[key] || [];
                const i = arr.indexOf(fn);
                if (i >= 0) arr.splice(i, 1);
            };
        },
    };

    window.KeenStore = store;
})();
