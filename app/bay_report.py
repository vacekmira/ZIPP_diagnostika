from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import APP_VERSION
from .i18n import translator
from .plan import register_pdf_fonts, svg_drawing


@dataclass(frozen=True)
class FontProfile:
    body: float
    small: float
    heading: float
    subheading: float
    table_header: float
    diagram_scale: float
    cell_padding: float


FONT_PROFILES = {
    "small": FontProfile(9.5, 8.5, 21, 13, 9, 1.0, 5),
    "normal": FontProfile(11, 9.5, 24, 15, 10.5, 1.16, 6),
    "larger": FontProfile(13, 11, 27, 17, 12, 1.30, 7),
    "large": FontProfile(15, 12.5, 30, 19, 14, 1.45, 8),
}


def get_font_profile(name: str) -> FontProfile:
    try:
        return FONT_PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown PDF font profile: {name}") from exc


def _paragraph(value, style: ParagraphStyle) -> Paragraph:
    text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(text, style)


def bay_report_rows(bay: dict, language: str = "cs") -> list[list[str]]:
    """Return display data while preserving actual L/P booleans verbatim."""
    tr = translator(language)
    pair_members: dict[int, list[dict]] = {}
    for truss in bay["trusses"]:
        if truss.get("pair_id"):
            pair_members.setdefault(truss["pair_id"], []).append(truss)
    rows: list[list[str]] = []
    for truss in sorted(bay["trusses"], key=lambda item: item["position"]):
        status = "-"
        if truss["excluded"]:
            reason = tr(f'reason.{truss["exclusion_reason"]}')
            status = f'{tr("state.excluded")} - {reason}'
        pair_text = "-"
        if truss.get("pair_id"):
            peers = [item["label"] for item in pair_members.get(truss["pair_id"], []) if item["id"] != truss["id"]]
            pair_text = f'{tr("report.paired_with")} {peers[0]}' if peers else tr("pair")
        rows.append([
            truss["label"],
            tr(f'type.{truss["type"]}'),
            tr("state.done") if truss["left_done"] else tr("state.pending"),
            tr("state.done") if truss["right_done"] else tr("state.pending"),
            status,
            pair_text,
            truss.get("exclusion_note") or "-",
        ])
    return rows


def render_bay_report_pdf(
    project: dict,
    bay: dict,
    language: str = "cs",
    created_at: datetime | None = None,
    font_profile: str = "normal",
) -> bytes:
    """Create a read-only localized report from current serialized DB state."""
    register_pdf_fonts()
    tr = translator(language)
    profile = get_font_profile(font_profile)
    created_at = created_at or datetime.now().astimezone()
    output = io.BytesIO()
    page_size = landscape(A3)
    document = SimpleDocTemplate(
        output,
        pagesize=page_size,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f'{tr("report.title")} - {project["name"]} - {bay["name"]}',
        author="ZIPP Diagnostika",
        subject=APP_VERSION,
    )

    body = ParagraphStyle(
        "ZippBody", fontName="ZippSans", fontSize=profile.body, leading=profile.body * 1.32,
        textColor=colors.HexColor("#17201e"),
    )
    small = ParagraphStyle(
        "ZippSmall", parent=body, fontSize=profile.small, leading=profile.small * 1.28,
        textColor=colors.HexColor("#63706c"),
    )
    heading = ParagraphStyle(
        "ZippHeading", parent=body, fontName="ZippSansBold", fontSize=profile.heading,
        leading=profile.heading * 1.18,
    )
    subheading = ParagraphStyle(
        "ZippSubheading", parent=body, fontName="ZippSansBold", fontSize=profile.subheading,
        leading=profile.subheading * 1.22, spaceBefore=7 * mm, spaceAfter=3 * mm,
    )
    table_header = ParagraphStyle(
        "ZippTableHeader", parent=body, fontName="ZippSansBold", fontSize=profile.table_header,
        leading=profile.table_header * 1.18, textColor=colors.white,
    )
    footer_size = max(7, profile.small - 1)
    footer_left = ParagraphStyle("ZippFooterLeft", parent=small, fontSize=footer_size)
    footer_right = ParagraphStyle("ZippFooterRight", parent=small, fontSize=footer_size, alignment=TA_RIGHT)

    progress = bay["progress"]
    bay_label = tr("report.bay")
    bay_name = bay["name"]
    conventional_prefix = f"{bay_label} "
    bay_value = bay_name[len(conventional_prefix):] if bay_name.casefold().startswith(conventional_prefix.casefold()) else bay_name
    summary_rows = [
        (tr("report.total_trusses"), len(bay["trusses"])),
        (tr("report.required_sides"), progress["required"]),
        (tr("report.completed_sides"), progress["completed"]),
        (tr("report.remaining_sides"), progress["remaining"]),
        (tr("report.completion"), f'{progress["percent"]} %'),
        (tr("report.excluded_trusses"), progress["excluded"]),
    ]
    summary_data = [[_paragraph(label, body), _paragraph(value, body)] for label, value in summary_rows]
    summary = Table(summary_data, colWidths=[62 * mm, 22 * mm], hAlign="LEFT")
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f2f5f2")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5cf")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d8dfdb")),
        ("FONTNAME", (0, 0), (0, -1), "ZippSansBold"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    story = [
        _paragraph(tr("report.title"), small),
        _paragraph(project["name"], heading),
        Spacer(1, 2 * mm),
        _paragraph(f'{bay_label}: {bay_value}', body),
        _paragraph(f'{tr("report.created_at")}: {created_at.strftime("%Y-%m-%d %H:%M %Z")}', small),
        _paragraph(f'{tr("app.version")} {APP_VERSION}', small),
        _paragraph(tr("report.summary"), subheading),
        summary,
        _paragraph(tr("report.diagram"), subheading),
    ]

    drawing = svg_drawing(project, language, {bay["id"]}, profile.diagram_scale)
    available_width = page_size[0] - document.leftMargin - document.rightMargin
    max_height = 76 * mm
    scale = min(available_width / drawing.width, max_height / drawing.height, 1)
    drawing.scale(scale, scale)
    drawing.width *= scale
    drawing.height *= scale
    story.append(drawing)
    if font_profile == "large":
        # The largest profile deliberately starts the table on a fresh page;
        # otherwise its heading can be orphaned below the diagram.
        story.append(PageBreak())
    story.append(_paragraph(tr("report.truss_detail"), subheading))

    headers = [
        tr("report.truss"), tr("report.type"), tr("report.left"), tr("report.right"),
        tr("report.status"), tr("report.pair"), tr("report.note"),
    ]
    rows = [[_paragraph(value, table_header) for value in headers]]
    for values in bay_report_rows(bay, language):
        rows.append([_paragraph(value, body) for value in values])

    column_widths = [31, 34, 30, 30, 49, 45, 135]
    if profile.body >= FONT_PROFILES["larger"].body:
        # Give the L/P columns enough room for full Czech and Slovak status
        # words at the two accessibility-oriented sizes.
        column_widths = [31, 36, 42, 42, 45, 45, 113]
    table = Table(
        rows,
        repeatRows=1,
        colWidths=[width * mm for width in column_widths],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123a32")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5cf")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8f6")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), profile.cell_padding),
        ("RIGHTPADDING", (0, 0), (-1, -1), profile.cell_padding),
        ("TOPPADDING", (0, 0), (-1, -1), profile.cell_padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), profile.cell_padding),
    ]))
    story.append(table)

    def footer(pdf_canvas, doc):
        pdf_canvas.saveState()
        footer_data = [[
            _paragraph(f'ZIPP Diagnostika - {project["name"]} - {bay["name"]}', footer_left),
            _paragraph(f'{tr("report.page")} {doc.page}', footer_right),
        ]]
        footer_table = Table(footer_data, colWidths=[available_width * 0.8, available_width * 0.2])
        footer_table.wrapOn(pdf_canvas, available_width, 10 * mm)
        footer_table.drawOn(pdf_canvas, document.leftMargin, 5 * mm)
        pdf_canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
