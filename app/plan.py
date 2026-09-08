from __future__ import annotations

import io
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from threading import Lock

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from svglib.fonts import register_font as register_svg_font
from svglib.svglib import svg2rlg

from . import APP_VERSION
from .access import ACCESS_METHODS, height_text
from .domain import bay_code
from .export_options import ExportOptions
from .i18n import translator


TRUSS_SPACING = 72
DILATION_INTERNAL_SPACING = 28
BAY_DEPTH = 176
MARGIN_LEFT = 112
MARGIN_RIGHT = 245
HEADER_HEIGHT = 88
LEGEND_HEIGHT = 150
FONT_DIRECTORY = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_REGISTRATION_LOCK = Lock()
_FONTS_READY = False


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
    distance_by_id: dict[int, float]


@dataclass(frozen=True)
class PlanGeometry:
    width: float
    height: float
    left: float
    right: float
    bays: tuple[BayGeometry, ...]
    boundaries: tuple[BoundaryGeometry, ...]


def _truss_distances(bay: dict) -> dict[int, float]:
    """Return right-to-left drawing distances based only on persisted data."""
    visible = sorted(bay["trusses"], key=lambda item: item["position"])
    if not visible:
        return {}
    distances = {visible[0]["id"]: 0.0}
    distance = 0.0
    for previous, current in zip(visible, visible[1:]):
        position_delta = max(current["position"] - previous["position"], 1)
        explicit_pair = (
            position_delta == 1
            and previous.get("pair_id") is not None
            and previous.get("pair_id") == current.get("pair_id")
        )
        distance += DILATION_INTERNAL_SPACING if explicit_pair else TRUSS_SPACING * position_delta
        distances[current["id"]] = distance
    return distances


def build_plan_geometry(project: dict, bay_ids: set[int] | None = None, show_access: bool = False, base_font_size: float = 13) -> PlanGeometry:
    """Build one continuous hall geometry shared by SVG and every PDF output."""
    selected = [bay for bay in project["bays"] if bay_ids is None or bay["id"] in bay_ids]
    display_bays = sorted(selected, key=lambda item: item["position"], reverse=True)
    distances_by_bay = {bay["id"]: _truss_distances(bay) for bay in display_bays}
    horizontal_span = max(
        (max(distances.values(), default=0) for distances in distances_by_bay.values()),
        default=0,
    )
    width = max(960, MARGIN_LEFT + MARGIN_RIGHT + horizontal_span)
    right = width - MARGIN_RIGHT
    left = right - horizontal_span
    object_top = max(HEADER_HEIGHT, base_font_size * 5) if show_access else HEADER_HEIGHT
    bay_depth = max(BAY_DEPTH, base_font_size * 16) if show_access else BAY_DEPTH

    bay_geometry: list[BayGeometry] = []
    boundaries: dict[int, BoundaryGeometry] = {}
    for display_index, bay in enumerate(display_bays):
        top = object_top + display_index * bay_depth
        bottom = top + bay_depth
        geometry = BayGeometry(
            bay=bay,
            top=top,
            bottom=bottom,
            center=(top + bottom) / 2,
            distance_by_id=distances_by_bay[bay["id"]],
        )
        bay_geometry.append(geometry)
        # A bay at position 1 lies between boundary A (index 0) and B (index 1).
        boundaries[bay["position"]] = BoundaryGeometry(
            index=bay["position"], label=bay_code(bay["position"] + 1), y=top
        )
        boundaries[bay["position"] - 1] = BoundaryGeometry(
            index=bay["position"] - 1, label=bay_code(bay["position"]), y=bottom
        )

    count = max(len(display_bays), 1)
    legend_height = max(260, base_font_size * 13) if show_access else LEGEND_HEIGHT
    height = object_top + count * bay_depth + legend_height
    return PlanGeometry(
        width=width,
        height=height,
        left=left,
        right=right,
        bays=tuple(bay_geometry),
        boundaries=tuple(sorted(boundaries.values(), key=lambda item: item.y)),
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


def _wrapped_svg_text(
    value: str,
    x: float,
    center_y: float,
    css_class: str,
    max_chars: int = 17,
    line_height: float = 17,
) -> str:
    """Wrap long bay names into the fixed annotation margin without clipping."""
    words: list[str] = []
    for word in value.split():
        if len(word) <= max_chars:
            words.append(word)
        else:
            words.extend(word[index:index + max_chars] for index in range(0, len(word), max_chars))
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    lines = lines or [value]
    first_y = center_y - ((len(lines) - 1) * line_height) / 2 + 5
    spans = "".join(
        f'<tspan x="{x}" y="{first_y + index * line_height}">{escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return f'<text x="{x}" y="{first_y}" class="{css_class}">{spans}</text>'


def render_plan_svg(
    project: dict,
    language: str = "cs",
    bay_ids: set[int] | None = None,
    font_scale: float = 1.0,
    base_font_size: float | None = None,
    include_version: bool = True,
    show_access: bool = False,
) -> str:
    tr = translator(language)
    base_size = float(base_font_size) if base_font_size is not None else 13 * font_scale
    geometry = build_plan_geometry(project, bay_ids, show_access, base_size)
    right = geometry.right
    axis_left = geometry.left - 18
    axis_right = right + 18
    text_scale = base_size / 13
    title_size = 24 * text_scale
    title_width = geometry.width - MARGIN_LEFT - 30
    title_length = len(project["name"]) * title_size * 0.58
    title_fit = (
        f' textLength="{title_width}" lengthAdjust="spacingAndGlyphs"'
        if title_length > title_width else ""
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{geometry.width}" height="{geometry.height}" '
        f'viewBox="0 0 {geometry.width} {geometry.height}" role="img" aria-labelledby="title desc">',
        '<style>text{font-family:ZippSans,"DejaVu Sans",Arial,sans-serif;fill:#17201e}'
        f'.small{{font-size:{12 * text_scale:g}px}}.label{{font-size:{base_size:g}px;font-weight:700}}'
        f'.bay{{font-size:{16 * text_scale:g}px;font-weight:700}}'
        '.muted{fill:#63706c}.axis{stroke:#7d8985;stroke-width:1.4;stroke-dasharray:14 7 2 7}'
        f'.pair{{stroke:#9a6500;stroke-width:2.2;fill:none}}.legend-text{{font-size:{12 * text_scale:g}px}}'
        f'.boundary-circle{{fill:#fff;stroke:#3254c7;stroke-width:1.4}}'
        f'.boundary-label{{fill:#3254c7;font-size:{base_size:g}px;font-weight:700}}</style>',
        f'<title id="title">{escape(tr("plan.title"))} - {escape(project["name"])}</title>',
        f'<desc id="desc">{escape(tr("plan.description"))}</desc>',
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<text x="{MARGIN_LEFT}" y="34" font-size="{title_size:g}" font-weight="700"{title_fit}>'
        f'{escape(project["name"])}</text>',
        f'<text x="{MARGIN_LEFT}" y="57" class="small muted">{escape(tr("plan.title"))}'
        f'{" - " + escape(APP_VERSION) if include_version else ""}</text>',
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
            _wrapped_svg_text(bay["name"], right + (70 if show_access else 104), center, "bay",
                              max_chars=max(4, int(160 / (16 * text_scale * 0.62))) if show_access else 17,
                              line_height=17 * text_scale),
            f'<text x="{right + 30}" y="{top + 21}" class="label" style="fill:#3254c7">P</text>',
            f'<text x="{right + 30}" y="{bottom - 9}" class="label" style="fill:#3254c7">L</text>',
        ]
        visible = sorted(bay["trusses"], key=lambda item: item["position"])
        if show_access:
            parts.append(f'<text data-height-for="{bay["id"]}" x="{right + 70}" y="{bottom - 18}" class="small">{escape(height_text(project, bay, tr))}</text>')
        x_by_id: dict[int, float] = {}
        for truss in visible:
            x = right - bay_geometry.distance_by_id[truss["id"]]
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
            label_y = center if show_access else center + 47
            anchor = ' text-anchor="middle"' if show_access else ''
            parts.append(
                f'<text x="{x - 7}" y="{label_y}" class="label"{anchor} '
                f'transform="rotate(-90 {x - 7} {label_y})">{escape(text)}</text>'
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
            if show_access:
                for side, y in (("right", top + 48), ("left", bottom - 22)):
                    method = truss.get(f"{side}_access")
                    if method in ACCESS_METHODS:
                        parts.append(f'<text data-access-for="{truss["id"]}" data-access-side="{side}" x="{x + 7}" y="{y}" class="label" style="fill:#735014">{method}</text>')

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
            if not show_access:
                # Access mode keeps the bracket and its legend; repeating the
                # long pair caption here would cover the individual P codes.
                parts.append(
                    f'<text x="{(x1 + x2) / 2}" y="{bracket_y + 14}" text-anchor="middle" '
                    f'class="small" style="fill:#7b5200">{escape(tr("pair"))}</text>'
                )
        parts.append("</g>")

    legend_y = geometry.height - 104
    legend_column = 250
    legend_row = 31
    if show_access:
        legend_y = max((bay.bottom for bay in geometry.bays), default=HEADER_HEIGHT) + base_size * 3
        legend_column = max(250, base_size * 15)
        legend_row = max(31, base_size * 1.8)
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
        x = MARGIN_LEFT + (index % 3) * legend_column
        y = legend_y + (index // 3) * legend_row
        if dash == "pair":
            marker = f'<path d="M{x},{y + 5} V{y - 5} H{x + 38} V{y + 5}" stroke="{color}" stroke-width="2.2" fill="none"/>'
        else:
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            marker = f'<line x1="{x}" y1="{y}" x2="{x + 38}" y2="{y}" stroke="{color}" stroke-width="3"{dash_attr}/>'
        parts.append(f'{marker}<text x="{x + 48}" y="{y + 4}" class="legend-text">{escape(label)}</text>')
    if show_access:
        y0 = legend_y + legend_row * 2 + base_size * 2.5
        parts.append(f'<text data-access-legend="true" x="{MARGIN_LEFT}" y="{y0}" class="label">{escape(tr("access.legend"))}</text>')
        for index, method in enumerate(ACCESS_METHODS):
            x = MARGIN_LEFT + (index % 3) * legend_column
            y = y0 + legend_row + (index // 3) * legend_row
            parts.append(f'<text x="{x}" y="{y}" class="legend-text">{method} = {escape(tr("access." + method))}</text>')
    parts.append(
        f'<text x="{right - 120}" y="{geometry.height - 16}" class="small muted">'
        f'L = {escape(tr("plan.left"))} - P = {escape(tr("plan.right"))}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def register_pdf_fonts() -> None:
    """Register the application-owned Unicode font for every PDF renderer."""
    global _FONTS_READY
    if _FONTS_READY:
        return
    regular_path = FONT_DIRECTORY / "DejaVuSans.ttf"
    bold_path = FONT_DIRECTORY / "DejaVuSans-Bold.ttf"
    if not regular_path.is_file() or not bold_path.is_file():
        raise RuntimeError("V aplikaci chybí vložený Unicode font DejaVu Sans.")
    with _FONT_REGISTRATION_LOCK:
        if _FONTS_READY:
            return
        if "ZippSans" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("ZippSans", str(regular_path)))
        if "ZippSansBold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("ZippSansBold", str(bold_path)))
        pdfmetrics.registerFontFamily("ZippSans", normal="ZippSans", bold="ZippSansBold")
        # svglib keeps its own font map in addition to ReportLab's registry.
        # Without these exact mappings it silently falls back to Helvetica.
        register_svg_font("ZippSans", str(regular_path), rlgFontName="ZippSans")
        register_svg_font("ZippSans", str(bold_path), weight="bold", rlgFontName="ZippSansBold")
        register_svg_font("ZippSans", str(bold_path), weight="700", rlgFontName="ZippSansBold")
        _FONTS_READY = True


def svg_drawing(
    project: dict,
    language: str = "cs",
    bay_ids: set[int] | None = None,
    font_scale: float = 1.0,
    base_font_size: float | None = None,
    show_access: bool = False,
):
    register_pdf_fonts()
    # svglib treats a CSS fallback list as an unknown family and silently
    # replaces it with Helvetica.  Feed it the exact registered family so
    # Czech and Slovak glyphs remain embedded in bay-report diagrams.
    source = render_plan_svg(
        project,
        language,
        bay_ids,
        font_scale,
        base_font_size,
        include_version=False,
        show_access=show_access,
    ).replace(
        'font-family:ZippSans,"DejaVu Sans",Arial,sans-serif',
        "font-family:ZippSans",
    )
    # CSS px are converted at 96 dpi, while unitless SVG geometry is treated
    # as PDF points by svglib. Use pt for PDF-only font styles so requested
    # label/L-P/legend sizes are not silently reduced to 75%.
    source = re.sub(r'(font-size:[0-9.]+)px', r'\1pt', source)
    drawing = svg2rlg(io.BytesIO(source.encode("utf-8")))
    if drawing is None:
        raise RuntimeError("SVG se nepodařilo převést do PDF.")
    _force_embedded_unicode_fonts(drawing)
    return drawing


def _force_embedded_unicode_fonts(node, seen: set[int] | None = None) -> None:
    """Prevent svglib from leaving any SVG text on a non-Unicode PDF font."""
    seen = seen or set()
    identity = id(node)
    if identity in seen:
        return
    seen.add(identity)
    if hasattr(node, "fontName"):
        current = str(getattr(node, "fontName", ""))
        weight = str(getattr(node, "fontWeight", ""))
        bold = "bold" in current.casefold() or weight.casefold() in {"bold", "700", "800", "900"}
        node.fontName = "ZippSansBold" if bold else "ZippSans"
    for child in getattr(node, "contents", ()) or ():
        _force_embedded_unicode_fonts(child, seen)


def _pdf_projects(project: dict) -> list[dict]:
    """Compatibility helper: a full-project export is never split."""
    return [project]


def render_plan_pdf(
    project: dict,
    language: str = "cs",
    page_size: str = "A3",
    font_size: str = "auto",
    orientation: str = "landscape",
    options: ExportOptions | None = None,
) -> bytes:
    from .plan_pdf import render_full_plan_pdf

    return render_full_plan_pdf(
        project,
        language,
        page_size=page_size,
        font_size=font_size,
        orientation=orientation,
        options=options,
    )
