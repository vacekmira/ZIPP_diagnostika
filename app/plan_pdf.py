from __future__ import annotations

import io
from dataclasses import dataclass

from reportlab.lib.pagesizes import A0, A1, A2, A3, A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from . import APP_VERSION
from .domain import bay_code
from .i18n import normalize_language, translator
from .plan import (
    BAY_DEPTH,
    _stroke,
    _truss_annotation,
    build_plan_geometry,
    register_pdf_fonts,
)


PAPER_SIZES = {"A4": A4, "A3": A3, "A2": A2, "A1": A1, "A0": A0}
PAPER_ORDER = tuple(PAPER_SIZES)
ORIENTATIONS = ("landscape", "portrait")
FONT_SIZES = (7, 9, 10, 12, 14)
AUTO_FONT_SIZES = (12, 10, 9, 7)


class ExportLayoutError(ValueError):
    def __init__(self, message: str, recommendations: list[str], reasons: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.recommendations = recommendations
        self.reasons = reasons or []

    def as_detail(self) -> dict:
        return {
            "message": self.message,
            "recommendations": self.recommendations,
            "reasons": self.reasons,
        }


@dataclass(frozen=True)
class PlanPdfLayout:
    paper_size: str
    orientation: str
    page_width: float
    page_height: float
    font_size: float
    requested_font_size: str
    margin: float
    header_height: float
    legend_height: float
    plot_top: float
    plot_bottom: float
    object_left: float
    object_right: float
    model_scale: float
    bay_scale: float
    title_lines: tuple[str, ...]


def _string_width(value: str, font_size: float, font_name: str = "ZippSans") -> float:
    return pdfmetrics.stringWidth(value, font_name, font_size)


def _break_token(token: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    parts: list[str] = []
    current = ""
    for char in token:
        candidate = current + char
        if current and _string_width(candidate, font_size, font_name) > max_width:
            parts.append(current)
            current = char
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts or [token]


def wrap_pdf_text(
    value: str,
    font_name: str,
    font_size: float,
    max_width: float,
) -> list[str]:
    """Wrap text by measured glyph width, including long labels without spaces."""
    if max_width <= 0:
        return [value]
    words: list[str] = []
    for word in value.split() or [value]:
        if _string_width(word, font_size, font_name) <= max_width:
            words.append(word)
        else:
            words.extend(_break_token(word, font_name, font_size, max_width))
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and _string_width(candidate, font_size, font_name) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [value]


def _truss_text(truss: dict, tr) -> str:
    annotation = _truss_annotation(truss, tr)
    return f'{truss["label"]}{" - " + annotation if annotation else ""}'


def _candidate_layout(
    project: dict,
    language: str,
    paper_size: str,
    font_size: int,
    orientation: str,
) -> tuple[PlanPdfLayout | None, list[str]]:
    register_pdf_fonts()
    tr = translator(language)
    page_width, page_height = (
        landscape(PAPER_SIZES[paper_size])
        if orientation == "landscape"
        else PAPER_SIZES[paper_size]
    )
    base = float(font_size)
    margin = max(18.0, base * 1.55)
    title_size = max(16.0, base * 1.65)
    title_lines = wrap_pdf_text(project["name"], "ZippSansBold", title_size, page_width - 2 * margin)
    reasons: list[str] = []
    if len(title_lines) > 2:
        reasons.append("Název zakázky vyžaduje více než dva řádky.")

    header_height = max(54.0, len(title_lines) * title_size * 1.18 + base * 2.2)
    legend_height = max(76.0, base * 6.9 + 18.0)
    right_reserve = max(112.0, min(220.0, page_width * 0.17))
    plot_top = page_height - margin - header_height
    plot_bottom = margin + legend_height
    available_height = plot_top - plot_bottom
    object_right = page_width - margin - right_reserve

    geometry = build_plan_geometry(project)
    bay_count = max(len(geometry.bays), 1)
    model_span = max(geometry.right - geometry.left, 1.0)
    # Reserve cap-height space for wrapped labels at the leftmost truss.
    # The geometry itself may reach the margin, but physical text must not.
    left_inset = margin + base * 1.9
    available_width = object_right - left_inset
    model_scale = available_width / model_span
    bay_scale = available_height / (bay_count * BAY_DEPTH)
    if model_scale <= 0 or bay_scale <= 0:
        reasons.append("Pro půdorys nezbyla využitelná plocha.")
        model_scale = 0.001
        bay_scale = 0.001
    object_left = object_right - model_span * model_scale
    bay_height = BAY_DEPTH * bay_scale
    if bay_height < base * 7.0:
        reasons.append("Výška lodí nestačí pro čitelné popisy vazníků.")

    name_x = object_right + base * 2.65
    boundary_circle_x = page_width - margin - max(9.0, base * 0.9)
    bay_name_width = boundary_circle_x - max(15.0, base * 1.2) - name_x
    for bay_geometry in geometry.bays:
        name_lines = wrap_pdf_text(bay_geometry.bay["name"], "ZippSansBold", base, bay_name_width)
        if len(name_lines) > 4:
            reasons.append(f'Název lodě „{bay_geometry.bay["name"]}“ se nevejde do pravého popisu.')
        trusses = sorted(bay_geometry.bay["trusses"], key=lambda item: item["position"])
        max_label_width = max(bay_height - base * 2.5, base * 2.5)
        columns: dict[int, float] = {}
        for truss in trusses:
            lines = wrap_pdf_text(_truss_text(truss, tr), "ZippSansBold", base, max_label_width)
            if len(lines) > 3:
                reasons.append(f'Popis vazníku „{truss["label"]}“ vyžaduje více než tři řádky.')
            # A rotated glyph's occupied column is close to its cap height,
            # not to the full point size/leading. Keep a small safety margin
            # while allowing real dilation gaps on larger paper sizes.
            columns[truss["id"]] = max(1, len(lines)) * base * 0.78
        for previous, current in zip(trusses, trusses[1:]):
            distance = abs(
                bay_geometry.distance_by_id[current["id"]]
                - bay_geometry.distance_by_id[previous["id"]]
            ) * model_scale
            explicit_pair = (
                previous.get("pair_id") is not None
                and previous.get("pair_id") == current.get("pair_id")
            )
            # Wrapped labels of an explicit pair are placed away from the
            # narrow inner gap. Their center lines still need a cap-height gap.
            required = (
                base * 0.72
                if explicit_pair
                else (columns[previous["id"]] + columns[current["id"]]) / 2 + base * 0.12
            )
            if distance + 0.01 < required:
                reasons.append(
                    f'Popisy vazníků „{previous["label"]}“ a „{current["label"]}“ by se překrývaly.'
                )
                break

    layout = PlanPdfLayout(
        paper_size=paper_size,
        orientation=orientation,
        page_width=page_width,
        page_height=page_height,
        font_size=base,
        requested_font_size=str(font_size),
        margin=margin,
        header_height=header_height,
        legend_height=legend_height,
        plot_top=plot_top,
        plot_bottom=plot_bottom,
        object_left=object_left,
        object_right=object_right,
        model_scale=model_scale,
        bay_scale=bay_scale,
        title_lines=tuple(title_lines),
    )
    return (None, reasons) if reasons else (layout, [])


def _recommendations(
    project: dict,
    language: str,
    paper_size: str,
    font_size: int,
    orientation: str,
) -> list[str]:
    language = normalize_language(language)
    recommendations: list[str] = []
    smaller = [size for size in reversed(FONT_SIZES) if size < font_size]
    for size in smaller:
        layout, _ = _candidate_layout(project, language, paper_size, size, orientation)
        if layout:
            recommendations.append(
                f"Použijte {paper_size} / {orientation.title()} / {size} pt."
                if language == "cs" else f"Použite {paper_size} / {orientation.title()} / {size} pt."
            )
            break
    if orientation == "portrait":
        layout, _ = _candidate_layout(project, language, paper_size, font_size, "landscape")
        if layout:
            recommendations.append(
                f"Použijte {paper_size} / Landscape / {font_size} pt."
                if language == "cs" else f"Použite {paper_size} / Landscape / {font_size} pt."
            )
    start = PAPER_ORDER.index(paper_size)
    for candidate_paper in PAPER_ORDER[start + 1:]:
        layout, _ = _candidate_layout(project, language, candidate_paper, font_size, orientation)
        if layout:
            recommendations.append(
                f"Použijte {candidate_paper} / {orientation.title()} / {font_size} pt." if language == "cs"
                else f"Použite {candidate_paper} / {orientation.title()} / {font_size} pt."
            )
            break
    if not recommendations:
        recommendations.append(
            "Zvolte větší formát, menší písmo nebo zkraťte mimořádně dlouhá označení."
            if language == "cs"
            else "Zvoľte väčší formát, menšie písmo alebo skráťte mimoriadne dlhé označenia."
        )
    return recommendations


def resolve_plan_pdf_layout(
    project: dict,
    language: str = "cs",
    page_size: str = "A3",
    font_size: str = "auto",
    orientation: str = "landscape",
) -> PlanPdfLayout:
    language = normalize_language(language)
    paper_size = page_size.upper()
    if paper_size not in PAPER_SIZES:
        raise ValueError(f"Unsupported paper size: {page_size}")
    normalized_orientation = orientation.lower()
    if normalized_orientation not in ORIENTATIONS:
        raise ValueError(f"Unsupported orientation: {orientation}")
    requested = str(font_size).lower()
    if requested == "auto":
        collected_reasons: list[str] = []
        for size in AUTO_FONT_SIZES:
            layout, reasons = _candidate_layout(project, language, paper_size, size, normalized_orientation)
            if layout:
                return PlanPdfLayout(**{**layout.__dict__, "requested_font_size": "auto"})
            collected_reasons = reasons
        message = (
            f"Zakázku nelze na {paper_size} / {normalized_orientation.title()} bezpečně umístit na jednu stranu ani s 7 pt."
            if language == "cs"
            else f"Zákazku nemožno na {paper_size} / {normalized_orientation.title()} bezpečne umiestniť na jednu stranu ani so 7 pt."
        )
        raise ExportLayoutError(
            message,
            _recommendations(project, language, paper_size, 7, normalized_orientation),
            collected_reasons,
        )
    try:
        numeric_size = int(requested)
    except ValueError as exc:
        raise ValueError(f"Unsupported font size: {font_size}") from exc
    if numeric_size not in FONT_SIZES:
        raise ValueError(f"Unsupported font size: {font_size}")
    layout, reasons = _candidate_layout(project, language, paper_size, numeric_size, normalized_orientation)
    if layout:
        return layout
    message = (
        f"Zvolená kombinace {paper_size} / {normalized_orientation.title()} / {numeric_size} pt se nevejde na jednu stranu."
        if language == "cs"
        else f"Zvolená kombinácia {paper_size} / {normalized_orientation.title()} / {numeric_size} pt sa nezmestí na jednu stranu."
    )
    raise ExportLayoutError(
        message,
        _recommendations(project, language, paper_size, numeric_size, normalized_orientation),
        reasons,
    )


def _set_stroke(pdf: canvas.Canvas, color: str, dash: str, width: float) -> None:
    pdf.setStrokeColor(color)
    pdf.setLineWidth(width)
    pdf.setDash([float(value) for value in dash.split()] if dash else [])


def _draw_rotated_lines(
    pdf: canvas.Canvas,
    lines: list[str],
    x: float,
    center_y: float,
    font_size: float,
    column_direction: int = 0,
) -> None:
    for index, line in enumerate(lines):
        if column_direction:
            offset = column_direction * index * font_size * 0.88
        else:
            offset = (index - (len(lines) - 1) / 2) * font_size * 1.08
        width = _string_width(line, font_size, "ZippSansBold")
        pdf.saveState()
        pdf.translate(x + offset, center_y - width / 2)
        pdf.rotate(90)
        pdf.setFont("ZippSansBold", font_size)
        pdf.setFillColor("#17201e")
        pdf.drawString(0, 0, line)
        pdf.restoreState()


def _draw_centered_lines(
    pdf: canvas.Canvas,
    lines: list[str],
    x: float,
    center_y: float,
    font_name: str,
    font_size: float,
) -> None:
    leading = font_size * 1.22
    first_y = center_y + ((len(lines) - 1) * leading) / 2 - font_size * 0.32
    pdf.setFont(font_name, font_size)
    pdf.setFillColor("#17201e")
    for index, line in enumerate(lines):
        pdf.drawString(x, first_y - index * leading, line)


def _draw_legend(pdf: canvas.Canvas, layout: PlanPdfLayout, tr) -> None:
    base = layout.font_size
    x0 = layout.margin
    title_y = layout.plot_bottom - base * 1.15
    pdf.setFillColor("#17201e")
    pdf.setFont("ZippSansBold", base)
    pdf.drawString(x0, title_y, tr("plan.legend"))
    entries = [
        ("#384844", "", tr("type.normal")),
        ("#17201e", "", tr("type.gable")),
        ("#9a6500", "6 3", tr("type.dilation")),
        ("#c43b35", "12 5 2 5", tr("reason.crack")),
        ("#2166b1", "9 5", tr("reason.leak")),
        ("#6c7471", "2 5", tr("plan.other")),
        ("#9a6500", "pair", tr("pair")),
    ]
    column_width = (layout.page_width - 2 * layout.margin) / 3
    row_height = base * 1.65
    first_y = title_y - base * 1.75
    for index, (color, dash, label) in enumerate(entries):
        column = index % 3
        row = index // 3
        x = x0 + column * column_width
        y = first_y - row * row_height
        pdf.setStrokeColor(color)
        pdf.setLineWidth(max(1.6, base * 0.18))
        if dash == "pair":
            marker_width = base * 3.4
            path = pdf.beginPath()
            path.moveTo(x, y - base * 0.35)
            path.lineTo(x, y + base * 0.35)
            path.lineTo(x + marker_width, y + base * 0.35)
            path.lineTo(x + marker_width, y - base * 0.35)
            pdf.drawPath(path, stroke=1, fill=0)
        else:
            pdf.setDash([float(value) for value in dash.split()] if dash else [])
            pdf.line(x, y, x + base * 3.4, y)
        pdf.setDash([])
        pdf.setFont("ZippSans", base)
        pdf.setFillColor("#17201e")
        pdf.drawString(x + base * 4.1, y - base * 0.32, label)


def render_full_plan_pdf(
    project: dict,
    language: str = "cs",
    page_size: str = "A3",
    font_size: str = "auto",
    orientation: str = "landscape",
) -> bytes:
    language = normalize_language(language)
    tr = translator(language)
    register_pdf_fonts()
    layout = resolve_plan_pdf_layout(project, language, page_size, font_size, orientation)
    geometry = build_plan_geometry(project)
    output = io.BytesIO()
    pdf = canvas.Canvas(
        output,
        pagesize=(layout.page_width, layout.page_height),
        pageCompression=1,
    )
    pdf.setTitle(f'{project["name"]} - {APP_VERSION}')
    pdf.setAuthor("ZIPP Diagnostika")
    pdf.setSubject(APP_VERSION)
    pdf.setCreator(f"ZIPP Diagnostika {APP_VERSION}")

    title_size = max(16.0, layout.font_size * 1.65)
    title_y = layout.page_height - layout.margin - title_size
    pdf.setFillColor("#17201e")
    pdf.setFont("ZippSansBold", title_size)
    for index, line in enumerate(layout.title_lines):
        pdf.drawString(layout.margin, title_y - index * title_size * 1.18, line)
    subtitle_y = title_y - len(layout.title_lines) * title_size * 1.18 - layout.font_size * 0.2
    pdf.setFillColor("#63706c")
    pdf.setFont("ZippSans", layout.font_size)
    pdf.drawString(layout.margin, subtitle_y, f'{tr("plan.title")} - {APP_VERSION}')

    bay_y: dict[int, tuple[float, float, float]] = {}
    boundaries: dict[int, float] = {}
    for index, bay_geometry in enumerate(geometry.bays):
        top = layout.plot_top - index * BAY_DEPTH * layout.bay_scale
        bottom = top - BAY_DEPTH * layout.bay_scale
        center = (top + bottom) / 2
        bay_y[bay_geometry.bay["id"]] = (top, bottom, center)
        boundaries[bay_geometry.bay["position"]] = top
        boundaries[bay_geometry.bay["position"] - 1] = bottom

    circle_x = layout.page_width - layout.margin - max(9.0, layout.font_size * 0.9)
    circle_radius = max(8.0, layout.font_size * 0.82)
    axis_left = layout.object_left - layout.font_size * 0.45
    axis_right = layout.object_right + layout.font_size * 1.15
    for boundary_index, y in sorted(boundaries.items()):
        pdf.setStrokeColor("#7d8985")
        pdf.setLineWidth(1.0)
        pdf.setDash([10, 5, 1.5, 5])
        pdf.line(axis_left, y, axis_right, y)
        pdf.setDash([])
        pdf.setFillColor("#ffffff")
        pdf.setStrokeColor("#3254c7")
        pdf.circle(circle_x, y, circle_radius, stroke=1, fill=1)
        pdf.setFillColor("#3254c7")
        pdf.setFont("ZippSansBold", layout.font_size)
        pdf.drawCentredString(circle_x, y - layout.font_size * 0.33, bay_code(boundary_index + 1))

    for bay_geometry in geometry.bays:
        bay = bay_geometry.bay
        top, bottom, center = bay_y[bay["id"]]
        name_x = layout.object_right + layout.font_size * 2.65
        name_width = circle_x - max(15.0, layout.font_size * 1.2) - name_x
        name_lines = wrap_pdf_text(bay["name"], "ZippSansBold", layout.font_size, name_width)
        _draw_centered_lines(pdf, name_lines, name_x, center, "ZippSansBold", layout.font_size)
        pdf.setFillColor("#3254c7")
        pdf.setFont("ZippSansBold", layout.font_size)
        pdf.drawString(layout.object_right + layout.font_size * 0.75, top - layout.font_size * 1.35, "P")
        pdf.drawString(layout.object_right + layout.font_size * 0.75, bottom + layout.font_size * 0.35, "L")

        trusses = sorted(bay["trusses"], key=lambda item: item["position"])
        pair_direction: dict[int, int] = {}
        pair_members: dict[int, list[dict]] = {}
        for truss in trusses:
            if truss.get("pair_id"):
                pair_members.setdefault(truss["pair_id"], []).append(truss)
        for members in pair_members.values():
            if len(members) == 2:
                by_position = sorted(members, key=lambda item: item["position"])
                pair_direction[by_position[0]["id"]] = 1
                pair_direction[by_position[1]["id"]] = -1
        x_by_id: dict[int, float] = {}
        label_width = max((top - bottom) - layout.font_size * 2.5, layout.font_size * 2.5)
        marker_radius = max(2.8, min(5.0, layout.font_size * 0.35))
        for truss in trusses:
            x = layout.object_right - bay_geometry.distance_by_id[truss["id"]] * layout.model_scale
            x_by_id[truss["id"]] = x
            color, dash, source_width = _stroke(truss)
            _set_stroke(pdf, color, dash, max(1.1, source_width * 0.72))
            pdf.line(x, top, x, bottom)
            if truss["type"] == "gable":
                pdf.setDash([])
                pdf.setLineWidth(1.1)
                pdf.line(x + max(2.5, layout.font_size * 0.28), top, x + max(2.5, layout.font_size * 0.28), bottom)
            lines = wrap_pdf_text(_truss_text(truss, tr), "ZippSansBold", layout.font_size, label_width)
            _draw_rotated_lines(
                pdf,
                lines,
                x - layout.font_size * 0.22,
                center,
                layout.font_size,
                pair_direction.get(truss["id"], 0),
            )
            for y, done in ((top - marker_radius - 1.2, truss["right_done"]), (bottom + marker_radius + 1.2, truss["left_done"])):
                pdf.setFillColor("#28715c" if done else "#ffffff")
                pdf.setStrokeColor("#28715c")
                pdf.setLineWidth(1.0)
                pdf.circle(x, y, marker_radius, stroke=1, fill=1)

        for pair_id, members in pair_members.items():
            if len(members) != 2:
                continue
            x1, x2 = sorted((x_by_id[members[0]["id"]], x_by_id[members[1]["id"]]))
            bracket_y = top - layout.font_size * 2.15
            pdf.setStrokeColor("#9a6500")
            pdf.setLineWidth(max(1.2, layout.font_size * 0.14))
            pdf.setDash([])
            path = pdf.beginPath()
            path.moveTo(x1, top - layout.font_size * 0.75)
            path.lineTo(x1, bracket_y)
            path.lineTo(x2, bracket_y)
            path.lineTo(x2, top - layout.font_size * 0.75)
            pdf.drawPath(path, stroke=1, fill=0)
            # The bracket plus the legend is the graphical pair marking.
            # Repeating a horizontal caption inside every narrow pair would
            # collide with the physical-size vertical labels on small paper.

    _draw_legend(pdf, layout, tr)
    footer_size = max(7.0, layout.font_size * 0.72)
    pdf.setFont("ZippSans", footer_size)
    pdf.setFillColor("#63706c")
    pdf.drawString(layout.margin, layout.margin * 0.45, f"ZIPP Diagnostika - {APP_VERSION}")
    pdf.drawCentredString(
        layout.page_width / 2,
        layout.margin * 0.45,
        f'L = {tr("plan.left")} - P = {tr("plan.right")}',
    )
    pdf.drawRightString(layout.page_width - layout.margin, layout.margin * 0.45, "1/1")
    pdf.showPage()
    pdf.save()
    return output.getvalue()
