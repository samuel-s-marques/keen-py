# Timeline Management

Case investigations involve stories that unfold over time. Static graphs show relationships, but they do not show **when** changes occurred. Keen's **Dynamic Event Timeline** adds temporal context to your investigations, allowing you to visualize how the "Chain of Events" evolves chronologically.

As you perform OSINT queries, run enrichment modules, or add findings manually, Keen automatically records the exact discovery timestamp for every node and edge.

---

## The Timeline Interface

When you select a workspace with at least two unique event timestamps, the **Event Timeline** container slides up at the bottom of the **Graph Map** panel.

The timeline interface consists of the following elements:

1. **Play / Pause Button:** Click to animate the chronological evolution of your graph automatically.
2. **Timeline Slider:** Scrub manually to step through events one-by-one.
3. **Time Labels:** Displays the start time (oldest event) on the left and end time (newest event) on the right.
4. **Active Time Display:** Shows the exact timestamp corresponding to the current slider position.
5. **Visibility Stats:** Shows how many nodes are currently visible relative to the total size of the graph (e.g. `12 / 18 nodes visible`).
6. **Playback Speed Selector:** Adjusts the auto-play speed (0.5x, 1.0x, 2.0x).

---

## How It Works

### Step-Based Event Mapping (Event Mode)
Rather than using a linear date slider—which would cause large empty time gaps where nothing changed—Keen maps the slider steps directly to the **sorted unique timestamps** of all events in your workspace. 

Every tick on the slider represents a real event (e.g. a node discovery or a relationship drawn). This ensures a highly responsive, continuous visual flow with no dead space.

### Edge Visibility Safety
To maintain visual integrity, an edge (relationship) is only rendered on the graph if **both** its source and target nodes are currently visible at the selected step. This prevents floating, disconnected edges.

### Real-Time Update Synchronization
When background enrichment modules run or Magic Chaining discovers new nodes, the timeline automatically updates in the background. 
- If you are looking at the **complete graph** (slider at the end), the timeline automatically expands and renders new findings in real-time.
- If you are **scrubbing or playing** an older segment, the timeline preserves your active scrubbing time index so your focus is never disrupted, while still incorporating the new events in the underlying track.

---

## Advanced: Database Schema & Compatibility

Workspaces are standard SQLite databases (`.keen` files). Timestamps are stored directly in the schema:
- **Nodes:** `nodes.timestamp DATETIME DEFAULT CURRENT_TIMESTAMP`
- **Edges:** `edge.timestamp DATETIME DEFAULT CURRENT_TIMESTAMP`

### Backward Compatibility & Fallbacks
For older workspaces created before the timeline feature was introduced:
1. **Self-Healing Migration:** Upon opening an older workspace, Keen automatically executes a schema migration to add the `timestamp` column to the `edge` table.
2. **Edge Fallback Logic:** If an edge has a null or missing timestamp, Keen calculates a fallback timestamp equal to the `MAX` of its source and target node timestamps. The relationship will automatically appear on the timeline as soon as both nodes become visible.
