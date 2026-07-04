import json


def _cell(value) -> str:
    """Escape a value for safe inclusion in a Markdown table cell (pipes and newlines
    would otherwise break the table layout)."""
    return str(value).replace("\\", "\\\\").replace("\n", " ").replace("|", "\\|")


def export_to_markdown(
    workspace_name: str,
    nodes: list,
    edges: list,
    path: str,
    suggestions: list = [],
    analysis: str | None = None,
) -> None:
    lines = []
    lines.append(f"# Keen Intelligence Report: {workspace_name}")
    lines.append("")
    lines.append("## Overview")
    lines.append(f"- **Total Nodes:** {len(nodes)}")
    lines.append(f"- **Total Relationships:** {len(edges)}")
    lines.append("")

    nodes_by_type = {}
    for n in nodes:
        t = n["type"]
        nodes_by_type.setdefault(t, []).append(n)

    lines.append("## Intelligence Graph Nodes")
    lines.append("")
    for n_type, n_list in sorted(nodes_by_type.items()):
        lines.append(f"### {n_type.capitalize()} ({len(n_list)})")
        lines.append("")
        lines.append("| Value | Created At | Extra Details |")
        lines.append("|-------|------------|---------------|")
        for n in sorted(n_list, key=lambda x: x["value"]):
            val = _cell(n["value"])
            ts = _cell(n.get("timestamp", "-"))

            meta = {}
            if n.get("metadata"):
                try:
                    meta = (
                        json.loads(n["metadata"])
                        if isinstance(n["metadata"], str)
                        else n["metadata"]
                    )
                except Exception:
                    pass

            meta_details = []
            if isinstance(meta, dict):
                for k, v in meta.items():
                    if k in ["stix2", "misp"]:
                        continue
                    meta_details.append(f"{k}: {v}")

            meta_str = ", ".join(meta_details) if meta_details else "-"
            meta_str = _cell(meta_str)
            lines.append(f"| {val} | {ts} | {meta_str} |")
        lines.append("")

    lines.append("## Intelligence Graph Relationships")
    lines.append("")
    if edges:
        lines.append("| Source | Relationship | Target |")
        lines.append("|--------|--------------|--------|")

        node_id_to_val = {n["id"]: n["value"] for n in nodes}
        for e in edges:
            src_val = _cell(node_id_to_val.get(e["source_id"], f"ID {e['source_id']}"))
            tgt_val = _cell(node_id_to_val.get(e["target_id"], f"ID {e['target_id']}"))
            rel = _cell(e["relationship"])
            lines.append(f"| {src_val} | {rel} | {tgt_val} |")
    else:
        lines.append("*No relationships documented in this workspace.*")

    lines.append("")

    # Append AI Analysis if present
    if analysis:
        lines.append("## AI Case Analysis & Synthesis")
        lines.append("")
        lines.append(analysis)
        lines.append("")

    # Append AI Suggestions if present
    if suggestions:
        active_suggestions = [s for s in suggestions if s.get("status") != "dismissed"]
        if active_suggestions:
            lines.append("## AI Thinking Partner Insights")
            lines.append("")
            lines.append("| Suggestion | Type | Status | Feedback |")
            lines.append("|------------|------|--------|----------|")
            for s in active_suggestions:
                text = _cell(s.get("suggestion_text", ""))
                pivot = s.get("pivot_type", "-")
                if s.get("module_name"):
                    pivot = f"{pivot} ({s['module_name'].split('/')[-1]})"
                pivot = _cell(pivot)
                status = _cell(s.get("status", "pending").capitalize())
                feedback = _cell(s.get("feedback", "-") or "-")
                lines.append(f"| {text} | {pivot} | {status} | {feedback} |")
            lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
