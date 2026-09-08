from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.bay_report import render_bay_report_pdf
from app.export_options import ExportOptions
from app.plan import render_plan_pdf


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "tmp" / "pdfs" / "alpha9-matrix"
FINAL = ROOT / "output" / "pdf"


def progress(trusses: list[dict]) -> dict:
    completed = required = excluded = 0
    for truss in trusses:
        done = int(truss["left_done"]) + int(truss["right_done"])
        completed += done
        required += done if truss["excluded"] else 2
        excluded += int(truss["excluded"])
    remaining = required - completed
    return {
        "completed": completed,
        "required": required,
        "remaining": remaining,
        "excluded": excluded,
        "percent": 100 if required == 0 else round(completed * 100 / required),
    }


def reference_project() -> dict:
    bays = []
    truss_id = 1
    for bay_position, code in enumerate(("A", "B", "C"), start=1):
        trusses = []
        for position in range(1, 25):
            pair_id = 100 + bay_position if position in (5, 6) else None
            truss_type = "dilation" if pair_id else ("gable" if position in (1, 24) else "normal")
            excluded = bay_position == 1 and position in (3, 8)
            reason = "leak" if position == 3 else ("crack" if position == 8 else None)
            label = f"{code}{position}"
            if bay_position == 1 and position == 8:
                label = "A8 - ŽĎÁR"
            trusses.append({
                "id": truss_id,
                "bay_id": bay_position,
                "position": position,
                "label": label,
                "type": truss_type,
                "type_label": truss_type,
                "left_done": position % 3 == 0 and not excluded,
                "right_done": position % 4 == 0 and not excluded,
                "left_access": ("N", "K", "Ž", "L", "J")[(position - 1) % 5],
                "right_access": ("J", "L", "N", "Ž", "K")[(position - 1) % 5],
                "access_note": "Přístup přes žeriavovou dráhu, kôň a ľalia." if position == 3 else None,
                "excluded": excluded,
                "exclusion_reason": reason,
                "exclusion_reason_label": reason,
                "exclusion_note": "Příliš žluťoučký kůň, kôň a ľalia." if excluded else None,
                "version": 1,
                "pair_id": pair_id,
            })
            truss_id += 1
        name = {1: "Loď A - jižní část", 2: "Loď B - žeriavová dráha", 3: "Loď C - severní část"}[bay_position]
        bays.append({
            "id": bay_position,
            "project_id": 1,
            "position": bay_position,
            "name": name,
            "height_m": 12.25 if bay_position == 2 else None,
            "progress": progress(trusses),
            "trusses": trusses,
        })
    return {
        "id": 1,
        "name": "Hala Žďár – zkouška",
        "default_height_m": 8.5,
        "note": "Česká a slovenská vizuální matice Alpha 9.",
        "archived": False,
        "revision": 5,
        "progress": progress([truss for bay in bays for truss in bay["trusses"]]),
        "bays": bays,
    }


def main() -> None:
    MATRIX.mkdir(parents=True, exist_ok=True)
    FINAL.mkdir(parents=True, exist_ok=True)
    project = reference_project()
    cases = (
        ("full-A4-landscape-auto.pdf", "A4", "landscape", "auto"),
        ("full-A3-landscape-10.pdf", "A3", "landscape", "10"),
        ("full-A2-portrait-14.pdf", "A2", "portrait", "14"),
    )
    for filename, paper, orientation, font in cases:
        options = ExportOptions(page_size=paper, orientation=orientation, font_size=font, show_access=True)
        data = render_plan_pdf(project, "cs", options=options)
        (MATRIX / filename).write_bytes(data)
        if filename == "full-A2-portrait-14.pdf":
            (FINAL / "zipp-alpha9-reference-A2-portrait-14.pdf").write_bytes(data)
    created_at = datetime(2026, 9, 8, 10, 30).astimezone()
    (MATRIX / "bay-A4-landscape-7pt-cs.pdf").write_bytes(
        render_bay_report_pdf(
            project,
            project["bays"][0],
            "cs",
            created_at,
            options=ExportOptions("A4", "landscape", "7", True),
        )
    )
    (MATRIX / "bay-A2-portrait-14pt-sk.pdf").write_bytes(
        render_bay_report_pdf(
            project,
            project["bays"][1],
            "sk",
            created_at,
            options=ExportOptions("A2", "portrait", "14", True),
        )
    )


if __name__ == "__main__":
    main()
