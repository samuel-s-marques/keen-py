import json


def export_to_json(workspace_name: str, nodes: list, edges: list, path: str) -> None:
    formatted_nodes = []
    for n in nodes:
        node_dict = dict(n)
        if node_dict.get("metadata") and isinstance(node_dict["metadata"], str):
            try:
                node_dict["metadata"] = json.loads(node_dict["metadata"])
            except Exception:
                pass
        formatted_nodes.append(node_dict)

    formatted_edges = []
    for e in edges:
        edge_dict = dict(e)
        if edge_dict.get("metadata") and isinstance(edge_dict["metadata"], str):
            try:
                edge_dict["metadata"] = json.loads(edge_dict["metadata"])
            except Exception:
                pass
        formatted_edges.append(edge_dict)

    data = {
        "workspace": workspace_name,
        "nodes": formatted_nodes,
        "edges": formatted_edges,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
