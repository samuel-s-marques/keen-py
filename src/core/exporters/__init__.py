from src.core.exporters.pdf import export_to_pdf
from src.core.exporters.html import export_to_html
from src.core.exporters.markdown import export_to_markdown
from src.core.exporters.json import export_to_json
from src.core.exporters.stix import export_to_stix


def export_workspace(
    workspace_name: str,
    export_type: str,
    nodes: list,
    edges: list,
    path: str,
    suggestions: list = [],
) -> None:
    export_type = export_type.lower()
    if export_type == "pdf":
        export_to_pdf(workspace_name, nodes, edges, path, suggestions=suggestions)
    elif export_type == "html":
        export_to_html(workspace_name, nodes, edges, path, suggestions=suggestions)
    elif export_type in ["markdown", "md"]:
        export_to_markdown(workspace_name, nodes, edges, path, suggestions=suggestions)
    elif export_type == "json":
        export_to_json(workspace_name, nodes, edges, path)
    elif export_type in ["stix2", "stix"]:
        export_to_stix(workspace_name, nodes, edges, path)
    else:
        raise ValueError(f"Unknown export type: {export_type}")
