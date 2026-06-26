import json


def export_to_markdown(
    workspace_name: str, nodes: list, edges: list, path: str
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
            val = n["value"]
            ts = n.get("timestamp", "-")

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
            meta_str = meta_str.replace("|", "\\|")
            lines.append(f"| {val} | {ts} | {meta_str} |")
        lines.append("")

    lines.append("## Intelligence Graph Relationships")
    lines.append("")
    if edges:
        lines.append("| Source | Relationship | Target |")
        lines.append("|--------|--------------|--------|")

        node_id_to_val = {n["id"]: n["value"] for n in nodes}
        for e in edges:
            src_val = node_id_to_val.get(e["source_id"], f"ID {e['source_id']}")
            tgt_val = node_id_to_val.get(e["target_id"], f"ID {e['target_id']}")
            rel = e["relationship"]
            lines.append(f"| {src_val} | {rel} | {tgt_val} |")
    else:
        lines.append("*No relationships documented in this workspace.*")

    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
