import re

from sqlalchemy import select

from app.bay_report import bay_report_rows
from app.domain import default_truss_label
from app.models import AuditLog, Bay, Project, Truss
from app.plan import build_plan_geometry


def create_project(client, *, bays=1, trusses=5, name="Alpha 3 hala"):
    response = client.post("/api/projects", json={
        "name": name,
        "bay_count": bays,
        "default_truss_count": trusses,
        "note": "Data musí zůstat",
        "technician_name": "Tester",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_new_single_bay_uses_v_labels_and_resize_keeps_scheme(client, db):
    project = create_project(client, bays=1, trusses=4)
    bay = project["bays"][0]
    assert [item["label"] for item in bay["trusses"]] == ["V1", "V2", "V3", "V4"]
    stored = db.get(Project, project["id"])
    assert stored.labeling_scheme == "single_v"

    first = bay["trusses"][0]
    assert client.patch(f"/api/trusses/{first['id']}/label", json={
        "label": "V-103A", "technician_name": "Tester", "expected_version": first["version"],
    }).status_code == 200
    resized = client.post(f"/api/bays/{bay['id']}/resize", json={
        "truss_count": 6, "technician_name": "Tester", "confirm": False,
    }).json()
    assert [item["label"] for item in resized["trusses"]] == ["V-103A", "V2", "V3", "V4", "V5", "V6"]


def test_single_v_project_can_gain_later_bay_without_relabeling_first_bay(client, db):
    project = create_project(client, bays=1, trusses=3)
    first_labels = [item["label"] for item in project["bays"][0]["trusses"]]
    stored = db.get(Project, project["id"])
    added = Bay(project_id=stored.id, position=2, name="Loď B")
    db.add(added)
    db.flush()
    db.add_all([
        Truss(
            bay_id=added.id,
            position=position,
            label=default_truss_label(stored.labeling_scheme, added.position, position),
        )
        for position in range(1, 4)
    ])
    db.commit()
    state = client.get(f"/api/projects/{stored.id}").json()
    assert [item["label"] for item in state["bays"][0]["trusses"]] == first_labels == ["V1", "V2", "V3"]
    assert [item["label"] for item in state["bays"][1]["trusses"]] == ["B1", "B2", "B3"]


def test_three_bays_share_exact_boundaries_and_position_one_is_right(client):
    project = create_project(client, bays=3, trusses=5)
    geometry = build_plan_geometry(project)
    by_position = {item.bay["position"]: item for item in geometry.bays}
    assert by_position[1].top == by_position[2].bottom
    assert by_position[2].top == by_position[3].bottom
    assert by_position[1].center > by_position[2].center > by_position[3].center
    assert len(geometry.boundaries) == 4

    svg = client.get(f"/api/projects/{project['id']}/plan.svg").text
    assert svg.count("data-boundary-index=") == 4
    bay_a = re.search(r'<g data-bay-id="[^"]+" data-bay-position="1".*?</g>', svg).group(0)
    x1 = float(re.search(r'data-position="1" x1="([^"]+)"', bay_a).group(1))
    x2 = float(re.search(r'data-position="2" x1="([^"]+)"', bay_a).group(1))
    assert x1 > x2


def test_database_types_pairs_and_actual_sides_drive_svg_and_report(client):
    project = create_project(client, bays=1, trusses=6)
    bay = project["bays"][0]
    v1, v2, v3, v4, v5, _ = bay["trusses"]
    gable = client.patch(f"/api/trusses/{v1['id']}/type", json={
        "type": "gable", "technician_name": "Tester", "expected_version": v1["version"],
    }).json()
    pair = client.post(f"/api/bays/{bay['id']}/dilation-pairs", json={
        "technician_name": "Tester", "truss_a_id": v3["id"], "truss_b_id": v4["id"],
        "expected_version_a": v3["version"], "expected_version_b": v4["version"],
    }).json()
    left = client.put(f"/api/trusses/{v5['id']}/diagnostics/left", json={
        "done": True, "technician_name": "Tester", "expected_version": v5["version"],
    }).json()
    client.post(f"/api/trusses/{v5['id']}/exclude", json={
        "reason": "crack", "note": "Kontrola trhliny", "technician_name": "Tester",
        "expected_version": left["version"],
    })

    state = client.get(f"/api/projects/{project['id']}").json()
    current_bay = state["bays"][0]
    svg = client.get(f"/api/projects/{project['id']}/plan.svg").text
    assert f'data-gable-for="{gable["id"]}"' in svg
    assert f'data-pair-id="{pair["id"]}"' in svg
    assert svg.count("data-pair-id=") == 1
    rows = bay_report_rows(current_bay, "cs")
    excluded_row = next(row for row in rows if row[0] == "V5")
    assert excluded_row[2] == "Provedeno"
    assert excluded_row[3] == "Neprovedeno"
    assert excluded_row[4] == "Vyřazeno - Trhlina"
    pair_rows = [row for row in rows if row[0] in {"V3", "V4"}]
    assert all(row[1] == "Dilatační" and row[5] != "-" for row in pair_rows)
