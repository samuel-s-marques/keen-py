"""Workspace-level timestamp-routine clustering analysis"""

import json
from datetime import datetime, timezone

# Weak signal by design: same-hour-of-day overlap alone is not strong
# evidence of shared identity, just a hint worth an operator's attention.
DEFAULT_CONFIDENCE = 0.3

# Skip creating a combinatorial edge-per-pair for clusters this large --
# report the cluster size instead of flooding the graph.
MAX_CLUSTER_SIZE_FOR_EDGES = 25

_TIMESTAMP_FORMATS = (
    "%Y:%m:%d %H:%M:%S",  # EXIF DateTimeOriginal
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)


def parse_timestamp(value: str) -> datetime | None:
    """Parse a timestamp string in any of the formats Keen's modules produce.

    Naive (no-tzinfo) values are assumed UTC. Returns ``None`` if none of
    the known formats match, so callers can skip that node rather than
    erroring out.
    """
    for fmt in _TIMESTAMP_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _collect_timestamped_nodes(workspace, metadata_key: str) -> list[dict]:
    """Scan every node in the workspace for a metadata timestamp field."""
    cursor = workspace.conn.cursor()
    cursor.execute("SELECT value, metadata FROM nodes")

    collected = []
    for row in cursor.fetchall():
        try:
            meta = json.loads(row["metadata"] or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        raw_ts = meta.get(metadata_key)
        if not raw_ts:
            continue
        parsed = parse_timestamp(str(raw_ts))
        if parsed is None:
            continue
        collected.append({"value": row["value"], "timestamp": parsed})

    return collected


def find_hour_of_day_clusters(
    workspace, metadata_key: str = "captured_at"
) -> list[dict]:
    """Group nodes carrying a timestamp metadata field by hour-of-day (UTC).

    Returns one entry per hour bucket with 2+ distinct nodes, sorted by
    cluster size (largest first).
    """
    nodes = _collect_timestamped_nodes(workspace, metadata_key)

    buckets: dict[int, set] = {}
    for entry in nodes:
        hour = entry["timestamp"].hour
        buckets.setdefault(hour, set()).add(entry["value"])

    clusters = [
        {"hour_utc": hour, "node_values": sorted(values), "count": len(values)}
        for hour, values in buckets.items()
        if len(values) >= 2
    ]
    return sorted(clusters, key=lambda c: c["count"], reverse=True)


def run_timestamp_clustering(
    workspace, metadata_key: str = "captured_at", create_edges: bool = True
) -> dict:
    """Run the full analysis: find clusters, optionally ingest suggestion edges.

    Returns a summary dict: ``{"clusters": [...], "edges_created": N,
    "skipped_oversized_clusters": N}``.
    """
    clusters = find_hour_of_day_clusters(workspace, metadata_key)

    edges_created = 0
    skipped_oversized = 0
    if create_edges:
        for cluster in clusters:
            values = cluster["node_values"]
            if len(values) > MAX_CLUSTER_SIZE_FOR_EDGES:
                skipped_oversized += 1
                continue
            for i in range(len(values)):
                for j in range(i + 1, len(values)):
                    source_id = workspace.get_node_id(values[i])
                    target_id = workspace.get_node_id(values[j])
                    if source_id and target_id:
                        workspace.add_edge(
                            source_id,
                            target_id,
                            "temporally-correlated-with",
                            metadata={
                                "hour_utc": cluster["hour_utc"],
                                "signal": "hour_of_day",
                            },
                            confidence=DEFAULT_CONFIDENCE,
                        )
                        edges_created += 1

    return {
        "clusters": clusters,
        "edges_created": edges_created,
        "skipped_oversized_clusters": skipped_oversized,
    }
