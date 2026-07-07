import datetime
import html as _html_lib
import json
import re


def _esc(value) -> str:
    """HTML-escape a raw value before interpolating it into the exported report,
    preventing stored-XSS from attacker-controlled node/edge/metadata values."""
    return _html_lib.escape(str(value), quote=True)


def md_to_html(md_text: str) -> str:
    if not md_text:
        return ""
    # Escape HTML special characters to prevent injection/broken layout
    html = md_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Convert bold **text**
    html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html)
    # Convert italic *text*
    html = re.sub(r"\*(.*?)\*", r"<em>\1</em>", html)

    # Convert headers (###, ##, #)
    html = re.sub(
        r"^### (.*?)$",
        r"<h4 style='color: var(--accent-cyan); margin-top: 12px; margin-bottom: 8px;'>\1</h4>",
        html,
        flags=re.MULTILINE,
    )
    html = re.sub(
        r"^## (.*?)$",
        r"<h3 style='color: #fff; margin-top: 16px; margin-bottom: 10px;'>\1</h3>",
        html,
        flags=re.MULTILINE,
    )
    html = re.sub(
        r"^# (.*?)$",
        r"<h2 style='color: #fff; margin-top: 20px; margin-bottom: 12px;'>\1</h2>",
        html,
        flags=re.MULTILINE,
    )

    # Convert bullet points * or -
    html = re.sub(r"^[*-] (.*?)$", r"<li>\1</li>", html, flags=re.MULTILINE)

    # Convert newlines to <br/>
    html = html.replace("\n", "<br/>")
    return html


def export_to_html(
    workspace_name: str,
    nodes: list,
    edges: list,
    path: str,
    suggestions: list = [],
    analysis: str | None = None,
) -> None:
    nodes_by_type = {}
    for n in nodes:
        t = n["type"]
        nodes_by_type.setdefault(t, []).append(n)

    node_id_to_val = {n["id"]: n["value"] for n in nodes}
    node_id_to_type = {n["id"]: n["type"] for n in nodes}

    nodes_html = ""
    for n_type, n_list in sorted(nodes_by_type.items()):
        table_rows = ""
        for n in sorted(n_list, key=lambda x: x["value"]):
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

            meta_details = ""
            if isinstance(meta, dict):
                for k, v in meta.items():
                    if k in ["stix2", "misp"]:
                        continue
                    meta_details += f"<span class='meta-tag'><strong>{_esc(k)}:</strong> {_esc(v)}</span> "
            if not meta_details:
                meta_details = "<span class='meta-tag-empty'>No metadata</span>"

            table_rows += f"""
            <tr>
                <td><span class='node-val'>{_esc(n["value"])}</span></td>
                <td><span class='badge'>{_esc(n_type)}</span></td>
                <td>{_esc(n.get("timestamp", "-"))}</td>
                <td>{meta_details}</td>
            </tr>
            """

        nodes_html += f"""
        <div class="card" style="margin-top: 20px;">
            <div class="card-header">
                <h3>{n_type.capitalize()} Nodes ({len(n_list)})</h3>
            </div>
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>Value</th>
                            <th>Type</th>
                            <th>Timestamp</th>
                            <th>Metadata</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
            </div>
        </div>
        """

    edges_rows = ""
    for e in edges:
        src_val = node_id_to_val.get(e["source_id"], f"ID {e['source_id']}")
        src_type = node_id_to_type.get(e["source_id"], "unknown")
        tgt_val = node_id_to_val.get(e["target_id"], f"ID {e['target_id']}")
        tgt_type = node_id_to_type.get(e["target_id"], "unknown")
        rel = e["relationship"]

        edges_rows += f"""
        <tr>
            <td><span class='node-val'>{_esc(src_val)}</span> <span class='badge-small'>{_esc(src_type)}</span></td>
            <td><span class='rel-badge'>{_esc(rel)}</span></td>
            <td><span class='node-val'>{_esc(tgt_val)}</span> <span class='badge-small'>{_esc(tgt_type)}</span></td>
        </tr>
        """

    if not edges:
        edges_rows = "<tr><td colspan='3' class='empty-state'>No relationships found in this workspace.</td></tr>"

    edges_html = f"""
    <div class="card" style="margin-top: 20px;">
        <div class="card-header">
            <h3>Relationships ({len(edges)})</h3>
        </div>
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th>Source Node</th>
                        <th>Relationship</th>
                        <th>Target Node</th>
                    </tr>
                </thead>
                <tbody>
                    {edges_rows}
                </tbody>
            </table>
        </div>
    </div>
    """

    suggestions_html = ""
    if suggestions:
        active_suggestions = [s for s in suggestions if s.get("status") != "dismissed"]
        if active_suggestions:
            rows_html = ""
            for s in active_suggestions:
                text = _esc(s.get("suggestion_text", ""))
                pivot = _esc(s.get("pivot_type", "-"))
                if s.get("module_name"):
                    pivot = f"{pivot} ({_esc(s['module_name'].split('/')[-1])})"
                status = _esc(s.get("status", "pending").upper())
                feedback = _esc(s.get("feedback", "-") or "-")

                status_color = "var(--accent-cyan)"
                if status == "ACCEPTED":
                    status_color = "var(--success)"
                elif status == "REJECTED":
                    status_color = "#ff5252"

                rows_html += f"""
                <tr>
                    <td><span class='node-val' style='font-family: var(--font-main); font-size: 0.85rem; color: var(--text-primary);'>{text}</span></td>
                    <td><span class='badge' style='background: rgba(255, 0, 255, 0.1); color: var(--accent-magenta); border-color: rgba(255, 0, 255, 0.2);'>{pivot}</span></td>
                    <td><span class='badge' style='background: rgba(0, 0, 0, 0.2); color: {status_color}; border-color: {status_color}44;'>{status}</span></td>
                    <td style='color: var(--text-secondary); font-size: 0.85rem;'>{feedback}</td>
                </tr>
                """

            suggestions_html = f"""
            <div class="card" style="margin-top: 20px;">
                <div class="card-header" style="display: flex; align-items: center; gap: 10px;">
                    <i class="fa-solid fa-brain" style="color: var(--accent-cyan);"></i>
                    <h3>AI Thinking Partner Insights</h3>
                </div>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th style="width: 50%;">Recommendation</th>
                                <th>Pivot Action</th>
                                <th>Status</th>
                                <th>User Feedback</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
            """

    analysis_html = ""
    if analysis:
        formatted_analysis = md_to_html(analysis)
        analysis_html = f"""
        <div class="card" style="margin-top: 20px; border: 1px dashed rgba(0, 240, 255, 0.3); background: rgba(0, 240, 255, 0.02);">
            <div class="card-header" style="display: flex; align-items: center; gap: 10px; border-bottom: 1px dashed rgba(0, 240, 255, 0.2);">
                <i class="fa-solid fa-brain" style="color: var(--accent-cyan);"></i>
                <h3 style="color: var(--accent-cyan);">AI Case Analysis & Synthesis</h3>
            </div>
            <div style="padding: 20px 24px; line-height: 1.6; color: var(--text-primary);">
                {formatted_analysis}
            </div>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Keen Report - {_esc(workspace_name)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {{
            --bg-main: #090a0f;
            --bg-card: rgba(20, 22, 30, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f0f2f8;
            --text-secondary: #8b92a5;
            --accent-cyan: #00f0ff;
            --accent-blue: #0072ff;
            --success: #00e676;
            --font-main: 'Inter', sans-serif;
            --font-mono: 'Fira Code', monospace;
        }}
        
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            background-color: var(--bg-main);
            color: var(--text-primary);
            font-family: var(--font-main);
            padding: 40px 20px;
            background-image:
                radial-gradient(circle at 15% 50%, rgba(0, 114, 255, 0.08) 0%, transparent 50%),
                radial-gradient(circle at 85% 30%, rgba(0, 240, 255, 0.05) 0%, transparent 50%);
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        header {{
            margin-bottom: 40px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 24px;
        }}
        
        .header-title h1 {{
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #fff, var(--text-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        
        .header-title p {{
            color: var(--text-secondary);
            font-size: 0.95rem;
        }}
        
        .meta-info {{
            text-align: right;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }}
        
        .meta-info span {{
            display: block;
            margin-bottom: 4px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        
        .stat-icon {{
            width: 50px;
            height: 50px;
            border-radius: 10px;
            background: rgba(0, 240, 255, 0.1);
            color: var(--accent-cyan);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            border: 1px solid rgba(0, 240, 255, 0.2);
        }}
        
        .stat-info h3 {{
            font-size: 1.8rem;
            font-weight: 700;
            margin-bottom: 4px;
            color: #fff;
        }}
        
        .stat-info p {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .card {{
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 30px;
        }}
        
        .card-header {{
            padding: 20px 24px;
            border-bottom: 1px solid var(--border-color);
            background: rgba(0, 0, 0, 0.1);
        }}
        
        .card-header h3 {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #fff;
        }}
        
        .table-responsive {{
            width: 100%;
            overflow-x: auto;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
            text-align: left;
        }}
        
        th, td {{
            padding: 14px 24px;
            border-bottom: 1px solid var(--border-color);
            vertical-align: middle;
        }}
        
        th {{
            background: rgba(0, 0, 0, 0.2);
            color: var(--text-secondary);
            font-weight: 500;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        tr:last-child td {{
            border-bottom: none;
        }}
        
        tr:hover td {{
            background: rgba(255, 255, 255, 0.01);
        }}
        
        .node-val {{
            font-family: var(--font-mono);
            font-weight: 500;
            color: #fff;
        }}
        
        .badge {{
            background: rgba(0, 240, 255, 0.1);
            color: var(--accent-cyan);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            border: 1px solid rgba(0, 240, 255, 0.2);
            font-weight: 500;
            white-space: nowrap;
        }}
        
        .badge-small {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-secondary);
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.7rem;
            border: 1px solid var(--border-color);
            margin-left: 6px;
        }}
        
        .rel-badge {{
            background: rgba(255, 0, 255, 0.1);
            color: var(--accent-magenta, #ff00ff);
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            border: 1px solid rgba(255, 0, 255, 0.2);
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .meta-tag {{
            display: inline-block;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border-color);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            margin-right: 6px;
            margin-bottom: 6px;
            color: var(--text-secondary);
        }}
        
        .meta-tag strong {{
            color: var(--text-primary);
        }}
        
        .meta-tag-empty {{
            color: var(--text-secondary);
            font-style: italic;
            font-size: 0.8rem;
        }}
        
        .empty-state {{
            text-align: center;
            color: var(--text-secondary);
            font-style: italic;
            padding: 30px;
        }}
        
        footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid var(--border-color);
            text-align: center;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-title">
                <h1>{_esc(workspace_name)}</h1>
                <p>OSINT & Intelligence Gathering Workspace Report</p>
            </div>
            <div class="meta-info">
                <span><strong>Generated:</strong> {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
                <span><strong>Source Tool:</strong> Keen</span>
            </div>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon"><i class="fa-solid fa-circle-nodes"></i></div>
                <div class="stat-info">
                    <h3>{len(nodes)}</h3>
                    <p>Total Nodes</p>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon" style="background:rgba(255, 0, 255, 0.1); color:#ff00ff; border-color:rgba(255,0,255,0.2);"><i class="fa-solid fa-link"></i></div>
                <div class="stat-info">
                    <h3>{len(edges)}</h3>
                    <p>Relationships</p>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon" style="background:rgba(0, 230, 118, 0.1); color:#00e676; border-color:rgba(0,230,118,0.2);"><i class="fa-solid fa-folder"></i></div>
                <div class="stat-info">
                    <h3>{len(nodes_by_type)}</h3>
                    <p>Categories</p>
                </div>
            </div>
        </div>
        
        {nodes_html}
        
        {edges_html}
        
        {analysis_html}
        
        {suggestions_html}
        
        <footer>
            <p>Generated automatically by Keen. Confidential intelligence data.</p>
        </footer>
    </div>
</body>
</html>
"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
