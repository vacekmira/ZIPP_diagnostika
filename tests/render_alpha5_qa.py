from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.bay_report import render_bay_report_pdf
from app.plan import render_plan_pdf


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "tmp" / "pdfs" / "alpha5-matrix"
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
            "progress": progress(trusses),
            "trusses": trusses,
        })
    return {
        "id": 1,
        "name": "Hala Žďár – zkouška",
        "note": "Česká a slovenská vizuální matice Alpha 5.",
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
        ("full-A4-auto.pdf", "A4", "auto"),
        ("full-A3-auto.pdf", "A3", "auto"),
        ("full-A3-12.pdf", "A3", "12"),
        ("full-A2-12.pdf", "A2", "12"),
        ("full-A1-14.pdf", "A1", "14"),
    )
    for filename, paper, font in cases:
        data = render_plan_pdf(project, "cs", page_size=paper, font_size=font)
        (MATRIX / filename).write_bytes(data)
        if filename == "full-A3-12.pdf":
            (FINAL / "zipp-alpha5-reference-A3-12.pdf").write_bytes(data)
    created_at = datetime(2026, 8, 31, 10, 30).astimezone()
    (MATRIX / "bay-A-normal-cs.pdf").write_bytes(
        render_bay_report_pdf(project, project["bays"][0], "cs", created_at, "normal")
    )
    (MATRIX / "bay-B-large-sk.pdf").write_bytes(
        render_bay_report_pdf(project, project["bays"][1], "sk", created_at, "large")
    )


if __name__ == "__main__":
    main()
