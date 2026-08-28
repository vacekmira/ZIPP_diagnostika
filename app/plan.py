from __future__ import annotations

import io
from copy import deepcopy
from html import escape
from pathlib import Path

from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg

from .i18n import translator


TRUSS_SPACING = 72
BAY_HEIGHT = 176
MARGIN_X = 112
HEADER_HEIGHT = 88
LEGEND_HEIGHT = 150


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


def render_plan_svg(project: dict, language: str = "cs") -> str:
    tr = translator(language)
    bays = sorted(project["bays"], key=lambda item: item["position"], reverse=True)
    max_count = max((len(bay["trusses"]) for bay in bays), default=1)
    width = max(960, MARGIN_X * 2 + max_count * TRUSS_SPACING)
    height = HEADER_HEIGHT + max(len(bays), 1) * BAY_HEIGHT + LEGEND_HEIGHT
    right = width - MARGIN_X
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<style>text{font-family:ZippSans,"DejaVu Sans",Arial,sans-serif;fill:#17201e}.small{font-size:12px}.label{font-size:13px;font-weight:700}.bay{font-size:16px;font-weight:700}.muted{fill:#63706c}.axis{stroke:#7d8985;stroke-width:1.4;stroke-dasharray:14 7 2 7}.pair{stroke:#9a6500;stroke-width:2.2;fill:none}.legend-text{font-size:12px}</style>',
        f'<title id="title">{escape(tr("plan.title"))} - {escape(project["name"])}</title>',
        f'<desc id="desc">{escape(tr("plan.description"))}</desc>',
        '<rect width="100%" height="100%" fill="#fff"/>',
        f'<text x="{MARGIN_X}" y="34" font-size="24" font-weight="700">{escape(project["name"])}</text>',
        f'<text x="{MARGIN_X}" y="57" class="small muted">{escape(tr("plan.title"))}</text>',
    ]
    for bay_index, bay in enumerate(bays):
        top = HEADER_HEIGHT + bay_index * BAY_HEIGHT + 22
        bottom = top + 116
        center = (top + bottom) / 2
        parts += [
            f'<text x="20" y="{center}" class="bay" transform="rotate(-90 20 {center})">{escape(bay["name"])}</text>',
            f'<line x1="{MARGIN_X-18}" y1="{top}" x2="{right+18}" y2="{top}" class="axis"/>',
            f'<line x1="{MARGIN_X-18}" y1="{bottom}" x2="{right+18}" y2="{bottom}" class="axis"/>',
            f'<text x="{right+35}" y="{top+4}" class="label" style="fill:#3254c7">P</text>',
            f'<text x="{right+35}" y="{bottom+4}" class="label" style="fill:#3254c7">L</text>',
        ]
        visible = sorted(bay["trusses"], key=lambda item: item["position"])
        x_by_id: dict[int, float] = {}
        for visual_index, truss in enumerate(visible):
            x = right - visual_index * TRUSS_SPACING
            x_by_id[truss["id"]] = x
            color, dash, line_width = _stroke(truss)
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            parts.append(f'<line x1="{x}" y1="{top}" x2="{x}" y2="{bottom}" stroke="{color}" stroke-width="{line_width}"{dash_attr}/>' )
            if truss["type"] == "gable":
                parts.append(f'<line x1="{x+5}" y1="{top}" x2="{x+5}" y2="{bottom}" stroke="{color}" stroke-width="1.6"/>')
            symbol = ""
            if truss["excluded"]:
                symbol = {"crack": "!", "leak": "≈", "other": "J"}.get(truss["exclusion_reason"], "J")
            elif truss["type"] == "gable": symbol = "Š"
            elif truss["type"] == "dilation": symbol = "D"
            text = f'{truss["label"]}{" · " + symbol if symbol else ""}'
            parts.append(f'<text x="{x-7}" y="{center+38}" class="label" transform="rotate(-90 {x-7} {center+38})">{escape(text)}</text>')
            for y, done, side in ((top, truss["right_done"], "P"), (bottom, truss["left_done"], "L")):
                fill = "#28715c" if done else "#fff"
                parts.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{fill}" stroke="#28715c" stroke-width="1.5"><title>{side}: {escape(tr("state.done") if done else tr("state.pending"))}</title></circle>')
        pair_groups: dict[int, list[dict]] = {}
        for truss in visible:
            if truss.get("pair_id"):
                pair_groups.setdefault(truss["pair_id"], []).append(truss)
        for pair_id, members in pair_groups.items():
            if len(members) != 2:
                continue
            x1, x2 = sorted((x_by_id[members[0]["id"]], x_by_id[members[1]["id"]]))
            bracket_y = top - 13
            parts.append(f'<path d="M{x1},{top-2} V{bracket_y} H{x2} V{top-2}" class="pair"/>')
            parts.append(f'<text x="{(x1+x2)/2}" y="{bracket_y-4}" text-anchor="middle" class="small" style="fill:#7b5200">{escape(tr("pair"))}</text>')
    legend_y = height - 104
    legend = [
        ("#384844", "", tr("type.normal")), ("#17201e", "", tr("type.gable")),
        ("#9a6500", "6 3", tr("type.dilation")), ("#c43b35", "12 5 2 5", tr("reason.crack")),
        ("#2166b1", "9 5", tr("reason.leak")), ("#6c7471", "2 5", tr("plan.other")),
        ("#9a6500", "pair", tr("pair")),
    ]
    parts.append(f'<text x="{MARGIN_X}" y="{legend_y-25}" class="label">{escape(tr("plan.legend"))}</text>')
    for index, (color, dash, label) in enumerate(legend):
        x = MARGIN_X + (index % 3) * 250
        y = legend_y + (index // 3) * 31
        if dash == "pair":
            marker = f'<path d="M{x},{y+5} V{y-5} H{x+38} V{y+5}" stroke="{color}" stroke-width="2.2" fill="none"/>'
        else:
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            marker = f'<line x1="{x}" y1="{y}" x2="{x+38}" y2="{y}" stroke="{color}" stroke-width="3"{dash_attr}/>'
        parts.append(f'{marker}<text x="{x+48}" y="{y+4}" class="legend-text">{escape(label)}</text>')
    parts.append(f'<text x="{right-120}" y="{height-16}" class="small muted">L = {escape(tr("plan.left"))} · P = {escape(tr("plan.right"))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _sliced_project(project: dict, bay: dict, trusses: list[dict], suffix: str = "") -> dict:
    result = deepcopy(project)
    result["name"] = project["name"] + suffix
    selected = deepcopy(bay)
    selected["trusses"] = deepcopy(trusses)
    result["bays"] = [selected]
    return result


def _pdf_projects(project: dict) -> list[dict]:
    max_count = max((len(item["trusses"]) for item in project["bays"]), default=0)
    if len(project["bays"]) <= 3 and max_count <= 15:
        return [project]
    pages: list[dict] = []
    for bay in project["bays"]:
        ordered = sorted(bay["trusses"], key=lambda item: item["position"])
        for start in range(0, len(ordered), 18):
            chunk = ordered[start:start+18]
            suffix = "" if len(ordered) <= 18 else f" · {bay['name']} · {chunk[0]['position']}-{chunk[-1]['position']}"
            pages.append(_sliced_project(project, bay, chunk, suffix))
    return pages or [project]


def render_plan_pdf(project: dict, language: str = "cs") -> bytes:
    font_candidates = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    )
    if "ZippSans" not in pdfmetrics.getRegisteredFontNames():
        font_path = next((path for path in font_candidates if path.is_file()), None)
        if font_path is None:
            raise RuntimeError("Chybí Unicode font pro PDF. Nainstalujte fonts-dejavu-core.")
        pdfmetrics.registerFont(TTFont("ZippSans", str(font_path)))
    page_size = landscape(A3)
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=page_size, pageCompression=1)
    page_projects = _pdf_projects(project)
    for page_number, page_project in enumerate(page_projects, start=1):
        drawing = svg2rlg(io.BytesIO(render_plan_svg(page_project, language).encode("utf-8")))
        if drawing is None:
            raise RuntimeError("SVG se nepodařilo převést do PDF.")
        available_w, available_h = page_size[0] - 42, page_size[1] - 42
        scale = min(available_w / drawing.width, available_h / drawing.height)
        drawing.scale(scale, scale)
        x = (page_size[0] - drawing.width * scale) / 2
        y = (page_size[1] - drawing.height * scale) / 2
        from reportlab.graphics import renderPDF
        renderPDF.draw(drawing, pdf, x, y)
        pdf.setFont("ZippSans", 8)
        pdf.drawRightString(page_size[0] - 18, 12, f"{page_number}/{len(page_projects)}")
        pdf.showPage()
    pdf.save()
    return output.getvalue()
