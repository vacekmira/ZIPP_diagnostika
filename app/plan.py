from __future__ import annotations

import io
from copy import deepcopy
from dataclasses import dataclass
from html import escape
from pathlib import Path

from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg

from .domain import bay_code
from .i18n import translator


TRUSS_SPACING = 72
BAY_DEPTH = 176
MARGIN_LEFT = 112
MARGIN_RIGHT = 245
HEADER_HEIGHT = 88
LEGEND_HEIGHT = 150
PDF_TRUSSES_PER_PAGE = 18


@dataclass(frozen=True)
class BoundaryGeometry:
    index: int
    label: str
    y: float


@dataclass(frozen=True)
class BayGeometry:
    bay: dict
    top: float
    bottom: float
    center: float


@dataclass(frozen=True)
class PlanGeometry:
    width: float
    height: float
    left: float
    right: float
    bays: tuple[BayGeometry, ...]
    boundaries: tuple[BoundaryGeometry, ...]
    first_position: int


def build_plan_geometry(project: dict, bay_ids: set[int] | None = None) -> PlanGeometry:
    """Build one continuous hall geometry shared by SVG and every PDF output."""
    selected = [bay for bay in project["bays"] if bay_ids is None or bay["id"] in bay_ids]
    display_bays = sorted(selected, key=lambda item: item["position"], reverse=True)
    positions = [
        truss["position"]
        for bay in display_bays
        for truss in bay["trusses"]
    ]
    first_position = min(positions, default=1)
    last_position = max(positions, default=first_position)
    position_span = max(last_position - first_position + 1, 1)
    width = max(960, MARGIN_LEFT + MARGIN_RIGHT + (position_span - 1) * TRUSS_SPACING)
    right = width - MARGIN_RIGHT
    left = right - (position_span - 1) * TRUSS_SPACING
    object_top = HEADER_HEIGHT

    bay_geometry: list[BayGeometry] = []
    boundaries: dict[int, BoundaryGeometry] = {}
    for display_index, bay in enumerate(display_bays):
        top = object_top + display_index * BAY_DEPTH
        bottom = top + BAY_DEPTH
        geometry = BayGeometry(bay=bay, top=top, bottom=bottom, center=(top + bottom) / 2)
        bay_geometry.append(geometry)
        # A bay at position 1 lies between boundary A (index 0) and B (index 1).
        boundaries[bay["position"]] = BoundaryGeometry(
            index=bay["position"], label=bay_code(bay["position"] + 1), y=top
        )
        boundaries[bay["position"] - 1] = BoundaryGeometry(
            index=bay["position"] - 1, label=bay_code(bay["position"]), y=bottom
        )

    count = max(len(display_bays), 1)
    height = object_top + count * BAY_DEPTH + LEGEND_HEIGHT
    return PlanGeometry(
        width=width,
        height=height,
        left=left,
        right=right,
        bays=tuple(bay_geometry),
        boundaries=tuple(sorted(boundaries.values(), key=lambda item: item.y)),
        first_position=first_position,
    )


def _stroke(truss: dict) -> tuple[str, str, float]:
    if truss["excluded"]:
        return {
            "crack": ("#c43b35", "12 5 2 5", 3.3),
            "leak": ("#2166b1", "9 5", 3.3),
            "other": ("#6c7471", "2 5", 3.3),
        }.get(truss["exclusion_reason"], ("#6c7471", "2 5", 3.3))
    if truss["type"] == "dilation":
        return "#9a6500", "6 3", 2.7
    if truss["type"] == "gable":
        return "#17201e", "", 3.8
    return "#384844", "", 2.0


def _truss_annotation(truss: dict, tr) -> str:
    if truss["excluded"]:
        return tr(f"reason.{truss['exclusion_reason']}").upper()
    if truss["type"] == "gable":
        return tr("type.gable").upper()
    if truss["type"] == "dilation":
        return tr("type.dilation").upper()
    return ""


def render_plan_svg(project: dict, language: str = "cs", bay_ids: set[int] | None = None) -> str:
    tr = translator(language)
    geometry = build_plan_geometry(project, bay_ids)
    right = geometry.right
    axis_left = geometry.left - 18
    axis_right = right + 18
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{geometry.width}" height="{geometry.height}" '
        f'viewBox="0 0 {geometry.width} {geometry.height}" role="img" aria-labelledby="title desc">',
        '<style>text{font-family:ZippSans,"DejaVu Sans",Arial,sans-serif;fill:#17201e}'
        '.small{font-size:12px}.label{font-size:13px;font-weight:700}.bay{font-size:16px;font-weight:700}'
        '.muted{fill:#63706c}.axis{stroke:#7d8985;stroke-width:1.4;stroke-dasharray:14 7 2 7}'
        '.pair{stroke:#9a6500;stroke-width:2.2;fill:none}.legend-text{font-size:12px}'
        '.boundary-circle{fill:#fff;stroke:#3254c7;stroke-width:1.4}.boundary-label{fill:#3254c7;font-size:13px;font-weight:700}</style>',
        f'<title id="title">{escape(tr("plan.title"))} - {escape(project["name"])}</title>',
        f'<desc id="desc">{escape(tr("plan.description"))}</desc>',
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<text x="{MARGIN_LEFT}" y="34" font-size="24" font-weight="700">{escape(project["name"])}</text>',
        f'<text x="{MARGIN_LEFT}" y="57" class="small muted">{escape(tr("plan.title"))}</text>',
    ]

    # Shared boundaries are emitted exactly once for the entire hall.
    for boundary in geometry.boundaries:
        parts += [
            f'<line data-boundary-index="{boundary.index}" x1="{axis_left}" y1="{boundary.y}" '
            f'x2="{axis_right}" y2="{boundary.y}" class="axis shared-boundary"/>',
            f'<circle cx="{right + 70}" cy="{boundary.y}" r="15" class="boundary-circle"/>',
            f'<text x="{right + 70}" y="{boundary.y + 4}" text-anchor="middle" '
            f'class="boundary-label">{escape(boundary.label)}</text>',
        ]

    for bay_geometry in geometry.bays:
        bay = bay_geometry.bay
        top, bottom, center = bay_geometry.top, bay_geometry.bottom, bay_geometry.center
        parts += [
            f'<g data-bay-id="{bay["id"]}" data-bay-position="{bay["position"]}" '
            f'data-top="{top}" data-bottom="{bottom}">',
            f'<text x="{right + 104}" y="{center + 5}" class="bay">{escape(bay["name"])}</text>',
            f'<text x="{right + 30}" y="{top + 21}" class="label" style="fill:#3254c7">P</text>',
            f'<text x="{right + 30}" y="{bottom - 9}" class="label" style="fill:#3254c7">L</text>',
        ]
        visible = sorted(bay["trusses"], key=lambda item: item["position"])
        x_by_id: dict[int, float] = {}
        for truss in visible:
            x = right - (truss["position"] - geometry.first_position) * TRUSS_SPACING
            x_by_id[truss["id"]] = x
            color, dash, line_width = _stroke(truss)
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            parts.append(
                f'<line data-truss-id="{truss["id"]}" data-position="{truss["position"]}" '
                f'x1="{x}" y1="{top}" x2="{x}" y2="{bottom}" stroke="{color}" '
                f'stroke-width="{line_width}"{dash_attr}/>'
            )
            if truss["type"] == "gable":
                parts.append(
                    f'<line data-gable-for="{truss["id"]}" x1="{x + 5}" y1="{top}" '
                    f'x2="{x + 5}" y2="{bottom}" stroke="{color}" stroke-width="1.6"/>'
                )
            annotation = _truss_annotation(truss, tr)
            text = f'{truss["label"]}{" - " + annotation if annotation else ""}'
            parts.append(
                f'<text x="{x - 7}" y="{center + 47}" class="label" '
                f'transform="rotate(-90 {x - 7} {center + 47})">{escape(text)}</text>'
            )
            # Markers sit just inside a bay, so independent L/P states at a
            # shared boundary never cover one another.
            for y, done, side in (
                (top + 7, truss["right_done"], "P"),
                (bottom - 7, truss["left_done"], "L"),
            ):
                fill = "#28715c" if done else "#fff"
                parts.append(
                    f'<circle data-truss-side="{side}" cx="{x}" cy="{y}" r="5" fill="{fill}" '
                    f'stroke="#28715c" stroke-width="1.5"><title>{side}: '
                    f'{escape(tr("state.done") if done else tr("state.pending"))}</title></circle>'
                )

        # A bracket is drawn only for a real persisted DilationPair.
        pair_groups: dict[int, list[dict]] = {}
        for truss in visible:
            if truss.get("pair_id"):
                pair_groups.setdefault(truss["pair_id"], []).append(truss)
        for pair_id, members in pair_groups.items():
            if len(members) != 2:
                continue
            x1, x2 = sorted((x_by_id[members[0]["id"]], x_by_id[members[1]["id"]]))
            bracket_y = top + 25
            parts.append(
                f'<path data-pair-id="{pair_id}" d="M{x1},{top + 12} V{bracket_y} H{x2} V{top + 12}" class="pair"/>'
            )
            parts.append(
                f'<text x="{(x1 + x2) / 2}" y="{bracket_y + 14}" text-anchor="middle" '
                f'class="small" style="fill:#7b5200">{escape(tr("pair"))}</text>'
            )
        parts.append("</g>")

    legend_y = geometry.height - 104
    legend = [
        ("#384844", "", tr("type.normal")),
        ("#17201e", "", tr("type.gable")),
        ("#9a6500", "6 3", tr("type.dilation")),
        ("#c43b35", "12 5 2 5", tr("reason.crack")),
        ("#2166b1", "9 5", tr("reason.leak")),
        ("#6c7471", "2 5", tr("plan.other")),
        ("#9a6500", "pair", tr("pair")),
    ]
    parts.append(f'<text x="{MARGIN_LEFT}" y="{legend_y - 25}" class="label">{escape(tr("plan.legend"))}</text>')
    for index, (color, dash, label) in enumerate(legend):
        x = MARGIN_LEFT + (index % 3) * 250
        y = legend_y + (index // 3) * 31
        if dash == "pair":
            marker = f'<path d="M{x},{y + 5} V{y - 5} H{x + 38} V{y + 5}" stroke="{color}" stroke-width="2.2" fill="none"/>'
        else:
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            marker = f'<line x1="{x}" y1="{y}" x2="{x + 38}" y2="{y}" stroke="{color}" stroke-width="3"{dash_attr}/>'
        parts.append(f'{marker}<text x="{x + 48}" y="{y + 4}" class="legend-text">{escape(label)}</text>')
    parts.append(
        f'<text x="{right - 120}" y="{geometry.height - 16}" class="small muted">'
        f'L = {escape(tr("plan.left"))} - P = {escape(tr("plan.right"))}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def register_pdf_fonts() -> None:
    regular_candidates = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    )
    bold_candidates = (
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    )
    if "ZippSans" not in pdfmetrics.getRegisteredFontNames():
        font_path = next((path for path in regular_candidates if path.is_file()), None)
        if font_path is None:
            raise RuntimeError("Chybí Unicode font pro PDF. Nainstalujte fonts-dejavu-core.")
        pdfmetrics.registerFont(TTFont("ZippSans", str(font_path)))
    if "ZippSansBold" not in pdfmetrics.getRegisteredFontNames():
        bold_path = next((path for path in bold_candidates if path.is_file()), None)
        if bold_path is None:
            pdfmetrics.registerFontFamily("ZippSans", normal="ZippSans", bold="ZippSans")
        else:
            pdfmetrics.registerFont(TTFont("ZippSansBold", str(bold_path)))
            pdfmetrics.registerFontFamily("ZippSans", normal="ZippSans", bold="ZippSansBold")


def svg_drawing(project: dict, language: str = "cs", bay_ids: set[int] | None = None):
    register_pdf_fonts()
    drawing = svg2rlg(io.BytesIO(render_plan_svg(project, language, bay_ids).encode("utf-8")))
    if drawing is None:
        raise RuntimeError("SVG se nepodařilo převést do PDF.")
    return drawing


def _pdf_projects(project: dict) -> list[dict]:
    positions = [truss["position"] for bay in project["bays"] for truss in bay["trusses"]]
    if not positions or max(positions) - min(positions) + 1 <= PDF_TRUSSES_PER_PAGE:
        return [project]
    pages: list[dict] = []
    first, last = min(positions), max(positions)
    for start in range(first, last + 1, PDF_TRUSSES_PER_PAGE):
        end = min(start + PDF_TRUSSES_PER_PAGE - 1, last)
        page = deepcopy(project)
        page["name"] = f'{project["name"]} - {start}-{end}'
        for bay in page["bays"]:
            bay["trusses"] = [truss for truss in bay["trusses"] if start <= truss["position"] <= end]
        pages.append(page)
    return pages


def render_plan_pdf(project: dict, language: str = "cs") -> bytes:
    register_pdf_fonts()
    page_size = landscape(A3)
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=page_size, pageCompression=1)
    page_projects = _pdf_projects(project)
    for page_number, page_project in enumerate(page_projects, start=1):
        drawing = svg_drawing(page_project, language)
        available_w, available_h = page_size[0] - 42, page_size[1] - 42
        scale = min(available_w / drawing.width, available_h / drawing.height)
        x = (page_size[0] - drawing.width * scale) / 2
        y = (page_size[1] - drawing.height * scale) / 2
        from reportlab.graphics import renderPDF

        pdf.saveState()
        pdf.translate(x, y)
        pdf.scale(scale, scale)
        renderPDF.draw(drawing, pdf, 0, 0)
        pdf.restoreState()
        pdf.setFont("ZippSans", 8)
        pdf.drawRightString(page_size[0] - 18, 12, f"{page_number}/{len(page_projects)}")
        pdf.showPage()
    pdf.save()
    return output.getvalue()
