from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import APP_VERSION
from .access import height_text
from .export_options import ExportOptions
from .i18n import translator
from .plan import build_plan_geometry, register_pdf_fonts, svg_drawing


@dataclass(frozen=True)
class FontProfile:
    body: float
    small: float
    heading: float
    subheading: float
    table_header: float
    diagram_text: float
    cell_padding: float


FONT_PROFILES = {
    "7": FontProfile(7, 7, 18, 12, 7, 7, 4),
    "9": FontProfile(9, 8, 21, 13, 9, 9, 5),
    "10": FontProfile(10, 9, 23, 14, 10, 10, 6),
    "12": FontProfile(12, 10.5, 26, 16, 12, 12, 7),
    "14": FontProfile(14, 12, 29, 18, 14, 14, 8),
}

FONT_PROFILE_ALIASES = {
    "auto": "10",
    # Backward-compatible API values from Alpha 4-6.
    "small": "7",
    "normal": "10",
    "larger": "12",
    "large": "14",
}


def get_font_profile(name: str) -> FontProfile:
    resolved = FONT_PROFILE_ALIASES.get(name, name)
    try:
        return FONT_PROFILES[resolved]
    except KeyError as exc:
        raise ValueError(f"Unknown PDF font profile: {name}") from exc


def _paragraph(value, style: ParagraphStyle) -> Paragraph:
    text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(text, style)


def bay_report_rows(bay: dict, language: str = "cs", show_access: bool = False) -> list[list[str]]:
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
        if show_access:
            rows[-1][2] += f' / {truss.get("left_access") or "-"}'
            rows[-1][3] += f' / {truss.get("right_access") or "-"}'
            if truss.get("access_note"):
                rows[-1][-1] += f'\n{tr("access.note")}: {truss["access_note"]}'
    return rows


def render_bay_report_pdf(
    project: dict,
    bay: dict,
    language: str = "cs",
    created_at: datetime | None = None,
    font_profile: str = "auto",
    options: ExportOptions | None = None,
) -> bytes:
    """Create a read-only localized report from current serialized DB state."""
    register_pdf_fonts()
    tr = translator(language)
    options = options or ExportOptions(font_size=font_profile)
    profile = get_font_profile(options.font_size)
    created_at = created_at or datetime.now().astimezone()
    output = io.BytesIO()
    page_size = options.page_dimensions
    document = SimpleDocTemplate(
        output,
        pagesize=page_size,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f'{tr("report.title")} - {project["name"]} - {bay["name"]}',
        author="ZIPP Diagnostika",
        subject=tr("report.title"),
    )
    available_width = page_size[0] - document.leftMargin - document.rightMargin

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
        leading=profile.subheading * 1.22, spaceBefore=7 * mm, spaceAfter=3 * mm, keepWithNext=True,
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
    summary_label_width = min(62 * mm, available_width * 0.72)
    summary = Table(
        summary_data,
        colWidths=[summary_label_width, min(22 * mm, available_width - summary_label_width)],
        hAlign="LEFT",
    )
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
        _paragraph(tr("report.summary"), subheading),
        summary,
        _paragraph(tr("report.diagram"), subheading),
    ]
    if options.show_access:
        story.insert(4, _paragraph(height_text(project, bay, tr), body))

    max_height = (document.height - 50) if options.show_access else min(76 * mm, document.height * 0.34)
    geometry = build_plan_geometry(project, {bay["id"]}, options.show_access)
    scale = min(available_width / geometry.width, max_height / geometry.height, 1)
    if options.show_access:
        # Geometry reserves physical space for all text, including the access
        # legend. Iterate because the source font compensates for PDF scaling.
        for _ in range(40):
            geometry = build_plan_geometry(project, {bay["id"]}, True, profile.diagram_text / scale)
            new_scale = min(available_width / geometry.width, max_height / geometry.height, 1)
            if abs(new_scale - scale) < 0.000001:
                break
            scale = new_scale
        from .plan_pdf import ExportLayoutError
        source_size = profile.diagram_text / scale
        legend_right = 112 + 3 * max(250, source_size * 15)
        if geometry.height * scale > max_height + 0.5 or legend_right > geometry.width + 0.5:
            raise ExportLayoutError(
                "Schéma s přístupy se při zvoleném písmu nevejde na stránku.",
                ["Zvolte větší formát papíru nebo menší písmo."],
            )
    # svglib scales geometry and text together. Compensate before conversion so
    # the label/L-P/legend base size after fitting is the requested physical pt.
    drawing = svg_drawing(
        project,
        language,
        {bay["id"]},
        base_font_size=profile.diagram_text / scale,
        show_access=options.show_access,
    )
    drawing.scale(scale, scale)
    drawing.width *= scale
    drawing.height *= scale
    story.append(drawing)
    if profile.body >= 14:
        # The largest profile deliberately starts the table on a fresh page;
        # otherwise its heading can be orphaned below the diagram.
        story.append(PageBreak())
    story.append(_paragraph(tr("report.truss_detail"), subheading))

    headers = [
        tr("report.truss"), tr("report.type"), tr("report.left"), tr("report.right"),
        tr("report.status"), tr("report.pair"), tr("report.note"),
    ]
    rows = [[_paragraph(value, table_header) for value in headers]]
    for values in bay_report_rows(bay, language, options.show_access):
        rows.append([_paragraph(value, body) for value in values])

    column_widths = [31, 34, 30, 30, 49, 45, 135]
    if profile.body >= FONT_PROFILES["12"].body:
        # Give the L/P columns enough room for full Czech and Slovak status
        # words at the two accessibility-oriented sizes.
        column_widths = [31, 36, 42, 42, 45, 45, 113]
    base_widths = column_widths
    total_width = sum(base_widths)
    table = Table(
        rows,
        repeatRows=1,
        colWidths=[available_width * width / total_width for width in base_widths],
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
            _paragraph(f'ZIPP Diagnostika - {APP_VERSION}', footer_left),
            _paragraph(f'{project["name"]} - {bay["name"]}', footer_left),
            _paragraph(f'{tr("report.page")} {doc.page}', footer_right),
        ]]
        footer_table = Table(
            footer_data,
            colWidths=[available_width * 0.32, available_width * 0.48, available_width * 0.2],
        )
        footer_table.wrapOn(pdf_canvas, available_width, 10 * mm)
        footer_table.drawOn(pdf_canvas, document.leftMargin, 5 * mm)
        pdf_canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
