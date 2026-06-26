from typing import Any
import json
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


def export_to_pdf(workspace_name: str, nodes: list, edges: list, path: str) -> None:
    doc = SimpleDocTemplate(
        path,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    primary_color = colors.HexColor("#0f172a")
    secondary_color = colors.HexColor("#475569")
    accent_color = colors.HexColor("#0284c7")
    bg_light = colors.HexColor("#f8fafc")
    border_color = colors.HexColor("#e2e8f0")

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=primary_color,
        spaceAfter=15,
    )

    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=12,
        leading=14,
        textColor=secondary_color,
        spaceAfter=30,
    )

    h1_style = ParagraphStyle(
        "SectionH1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=primary_color,
        spaceBefore=15,
        spaceAfter=10,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        "SectionH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=accent_color,
        spaceBefore=12,
        spaceAfter=8,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=primary_color,
    )

    body_bold_style = ParagraphStyle(
        "ReportBodyBold", parent=body_style, fontName="Helvetica-Bold"
    )

    body_secondary_style = ParagraphStyle(
        "ReportBodySecondary", parent=body_style, textColor=secondary_color
    )

    code_style = ParagraphStyle(
        "ReportCode",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=9,
        leading=11,
        textColor=primary_color,
    )

    story: list[Any] = []

    # Header
    story.append(Paragraph("Keen Intelligence Report", title_style))
    story.append(Paragraph(f"Workspace: {workspace_name}", subtitle_style))
    story.append(Spacer(1, 0.25 * inch))

    # Summary
    story.append(Paragraph("Executive Summary", h1_style))
    summary_text = (
        f"This report presents an intelligence summary generated from the Keen workspace <b>{workspace_name}</b>. "
        f"The workspace contains a structured intelligence graph consisting of a total of <b>{len(nodes)}</b> entities (nodes) and "
        f"<b>{len(edges)}</b> documented connections (relationships) between them. The details are categorized below."
    )
    story.append(Paragraph(summary_text, body_style))
    story.append(Spacer(1, 0.2 * inch))

    # Stats Table
    stats_data = [
        [
            Paragraph("<b>Metric</b>", body_bold_style),
            Paragraph("<b>Count / Value</b>", body_bold_style),
        ],
        [
            Paragraph("Total Identified Entities (Nodes)", body_style),
            Paragraph(str(len(nodes)), body_style),
        ],
        [
            Paragraph("Documented Relationships (Edges)", body_style),
            Paragraph(str(len(edges)), body_style),
        ],
        [
            Paragraph("Export Date", body_style),
            Paragraph(
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), body_style
            ),
        ],
    ]
    stats_table = Table(stats_data, colWidths=[3.5 * inch, 3.5 * inch])
    stats_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), bg_light),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, border_color),
                ("BOX", (0, 0), (-1, -1), 1, primary_color),
            ]
        )
    )
    story.append(stats_table)
    story.append(Spacer(1, 0.3 * inch))

    # Entities Section
    story.append(Paragraph("Intelligence Graph Entities", h1_style))

    nodes_by_type = {}
    for n in nodes:
        t = n["type"]
        nodes_by_type.setdefault(t, []).append(n)

    for n_type, n_list in sorted(nodes_by_type.items()):
        story.append(
            Paragraph(f"{n_type.capitalize()} Entities ({len(n_list)})", h2_style)
        )

        table_data = [
            [
                Paragraph("<b>Value</b>", body_bold_style),
                Paragraph("<b>Timestamp</b>", body_bold_style),
                Paragraph("<b>Details / Properties</b>", body_bold_style),
            ]
        ]

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

            meta_details = []
            if isinstance(meta, dict):
                for k, v in meta.items():
                    if k in ["stix2", "misp"]:
                        continue
                    meta_details.append(f"<b>{k}:</b> {v}")

            meta_text = ", ".join(meta_details) if meta_details else "-"

            table_data.append(
                [
                    Paragraph(n["value"], code_style),
                    Paragraph(n.get("timestamp", "-"), body_secondary_style),
                    Paragraph(meta_text, body_style),
                ]
            )

        node_table = Table(table_data, colWidths=[2.5 * inch, 1.5 * inch, 3.0 * inch])
        node_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), bg_light),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, border_color),
                    ("LINEBELOW", (0, 0), (-1, 0), 1.5, primary_color),
                ]
            )
        )
        story.append(node_table)
        story.append(Spacer(1, 0.25 * inch))

    story.append(PageBreak())

    # Relationships Section
    story.append(Paragraph("Intelligence Relationships", h1_style))
    story.append(
        Paragraph(
            "Below are the connections documented between the identified entities in this workspace:",
            body_style,
        )
    )
    story.append(Spacer(1, 0.15 * inch))

    if edges:
        node_id_to_val = {n["id"]: n["value"] for n in nodes}
        node_id_to_type = {n["id"]: n["type"] for n in nodes}

        edge_table_data = [
            [
                Paragraph("<b>Source Entity</b>", body_bold_style),
                Paragraph("<b>Relationship</b>", body_bold_style),
                Paragraph("<b>Target Entity</b>", body_bold_style),
            ]
        ]

        for e in edges:
            src_val = node_id_to_val.get(e["source_id"], f"ID {e['source_id']}")
            src_type = node_id_to_type.get(e["source_id"], "unknown")
            tgt_val = node_id_to_val.get(e["target_id"], f"ID {e['target_id']}")
            tgt_type = node_id_to_type.get(e["target_id"], "unknown")
            rel = e["relationship"]

            edge_table_data.append(
                [
                    Paragraph(
                        f"{src_val}<br/><font color='#64748b' size='8'>({src_type})</font>",
                        body_style,
                    ),
                    Paragraph(
                        f"<b>{rel}</b>",
                        ParagraphStyle(
                            "rel", parent=body_style, textColor=accent_color
                        ),
                    ),
                    Paragraph(
                        f"{tgt_val}<br/><font color='#64748b' size='8'>({tgt_type})</font>",
                        body_style,
                    ),
                ]
            )

        edge_table = Table(
            edge_table_data, colWidths=[2.7 * inch, 1.6 * inch, 2.7 * inch]
        )
        edge_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), bg_light),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, border_color),
                    ("LINEBELOW", (0, 0), (-1, 0), 1.5, primary_color),
                ]
            )
        )
        story.append(edge_table)
    else:
        story.append(
            Paragraph("<i>No relationships have been defined yet.</i>", body_style)
        )

    doc.build(story)
