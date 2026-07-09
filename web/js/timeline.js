/*
 * Graph timeline: derive timestamps, slider filtering, and playback.
 */
import { drawGraph } from "./graph.js";

export function getEdgeTimestamp(edge) {
    if (edge.timestamp) return edge.timestamp;
    const sourceNode = KeenStore.currentNodes.find(n => n.id === edge.source_id);
    const targetNode = KeenStore.currentNodes.find(n => n.id === edge.target_id);
    const t1 = sourceNode ? sourceNode.timestamp : null;
    const t2 = targetNode ? targetNode.timestamp : null;
    if (!t1 && !t2) return null;
    if (!t1) return t2;
    if (!t2) return t1;
    return t1 > t2 ? t1 : t2;
}

export function initTimeline() {
    const timelineContainer = document.getElementById('graph-timeline');
    const slider = document.getElementById('timeline-slider');
    const startTimeSpan = document.getElementById('timeline-start-time');
    const endTimeSpan = document.getElementById('timeline-end-time');

    if (!timelineContainer || !slider) return;

    // Remember previous state to handle real-time updates seamlessly
    const prevActiveTime = KeenStore.timelineTimestamps.length > 0 ? KeenStore.timelineTimestamps[parseInt(slider.value, 10)] : null;
    const wasAtEnd = KeenStore.timelineTimestamps.length > 0 && parseInt(slider.value, 10) === KeenStore.timelineTimestamps.length - 1;

    // Gather all timestamps
    const tsSet = new Set();
    KeenStore.currentNodes.forEach(n => { if (n.timestamp) tsSet.add(n.timestamp); });
    KeenStore.currentEdges.forEach(e => {
        const ts = getEdgeTimestamp(e);
        if (ts) tsSet.add(ts);
    });

    KeenStore.timelineTimestamps = Array.from(tsSet).sort();

    // If not enough data, hide timeline
    if (KeenStore.timelineTimestamps.length < 2) {
        timelineContainer.style.display = 'none';
        const minimapEl = document.getElementById('graph-minimap');
        if (minimapEl) minimapEl.style.bottom = '16px';
        if (KeenStore.isTimelinePlaying) {
            toggleTimelinePlay(false);
        }
        drawGraph(KeenStore.currentNodes, KeenStore.currentEdges);
        return;
    }

    // Show timeline
    timelineContainer.style.display = 'flex';
    const minimapEl = document.getElementById('graph-minimap');
    if (minimapEl) minimapEl.style.bottom = '96px';

    // Setup slider bounds
    slider.min = 0;
    slider.max = KeenStore.timelineTimestamps.length - 1;

    // Smart position preservation
    if (wasAtEnd || prevActiveTime === null) {
        slider.value = KeenStore.timelineTimestamps.length - 1;
    } else {
        let bestIdx = 0;
        let minDiff = Infinity;
        const prevDate = new Date(prevActiveTime.replace(' ', 'T') + 'Z').getTime();

        KeenStore.timelineTimestamps.forEach((ts, idx) => {
            const d = new Date(ts.replace(' ', 'T') + 'Z').getTime();
            const diff = Math.abs(d - prevDate);
            if (diff < minDiff) {
                minDiff = diff;
                bestIdx = idx;
            }
        });
        slider.value = bestIdx;
    }

    // Format dates for display
    const formatDate = (tsStr) => {
        if (!tsStr) return '-';
        try {
            const d = new Date(tsStr.replace(' ', 'T') + 'Z');
            if (isNaN(d.getTime())) return tsStr;
            return d.toLocaleString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            });
        } catch (e) {
            return tsStr;
        }
    };

    startTimeSpan.textContent = formatDate(KeenStore.timelineTimestamps[0]);
    endTimeSpan.textContent = formatDate(KeenStore.timelineTimestamps[KeenStore.timelineTimestamps.length - 1]);

    updateTimelineFilter();
}

export function updateTimelineFilter() {
    const slider = document.getElementById('timeline-slider');
    const currentTimeSpan = document.getElementById('timeline-current-time');
    const statsSpan = document.getElementById('timeline-stats');

    if (!slider || KeenStore.timelineTimestamps.length < 2) return;

    const idx = parseInt(slider.value, 10);
    const activeTime = KeenStore.timelineTimestamps[idx];

    const formatDate = (tsStr) => {
        if (!tsStr) return '-';
        try {
            const d = new Date(tsStr.replace(' ', 'T') + 'Z');
            if (isNaN(d.getTime())) return tsStr;
            return d.toLocaleString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            });
        } catch (e) {
            return tsStr;
        }
    };

    currentTimeSpan.textContent = formatDate(activeTime);

    // Filter nodes
    const filteredNodes = KeenStore.currentNodes.filter(n => !n.timestamp || n.timestamp <= activeTime);
    const visibleNodeIds = new Set(filteredNodes.map(n => n.id || n.value));

    // Filter edges: must be <= activeTime AND both source and target must be visible
    const filteredEdges = KeenStore.currentEdges.filter(e => {
        const ts = getEdgeTimestamp(e);
        const isTimeMatch = !ts || ts <= activeTime;
        const areNodesVisible = visibleNodeIds.has(e.source_id) && visibleNodeIds.has(e.target_id);
        return isTimeMatch && areNodesVisible;
    });

    // Update stats
    statsSpan.textContent = `${filteredNodes.length} / ${KeenStore.currentNodes.length} nodes visible`;

    // Update the live graph
    drawGraph(filteredNodes, filteredEdges);
}

export function toggleTimelinePlay(forceState) {
    const btn = document.getElementById('btn-timeline-play');
    const slider = document.getElementById('timeline-slider');
    const speedSelect = document.getElementById('timeline-speed');

    if (!btn || !slider) return;

    const nextState = forceState !== undefined ? forceState : !KeenStore.isTimelinePlaying;

    if (nextState) {
        KeenStore.isTimelinePlaying = true;
        btn.innerHTML = '<i class="fa-solid fa-pause"></i>';
        btn.title = 'Pause Timeline';

        if (parseInt(slider.value, 10) >= KeenStore.timelineTimestamps.length - 1) {
            slider.value = 0;
            updateTimelineFilter();
        }

        const interval = parseInt(speedSelect ? speedSelect.value : '1000', 10);

        KeenStore.timelineTimer = setInterval(() => {
            const val = parseInt(slider.value, 10);
            if (val < KeenStore.timelineTimestamps.length - 1) {
                slider.value = val + 1;
                updateTimelineFilter();
            } else {
                toggleTimelinePlay(false);
            }
        }, interval);
    } else {
        KeenStore.isTimelinePlaying = false;
        btn.innerHTML = '<i class="fa-solid fa-play"></i>';
        btn.title = 'Play Timeline';
        if (KeenStore.timelineTimer) {
            clearInterval(KeenStore.timelineTimer);
            KeenStore.timelineTimer = null;
        }
    }
}
