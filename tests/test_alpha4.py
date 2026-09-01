from pathlib import Path

from sqlalchemy import func, select

from app import APP_VERSION
from app.bay_report import FONT_PROFILES
from app.models import (
    AuditLog,
    Bay,
    DilationPair,
    DilationPairMember,
    Project,
    ProjectDeletionLog,
    Truss,
)
from app.plan import (
    DILATION_INTERNAL_SPACING,
    TRUSS_SPACING,
    _pdf_projects,
    build_plan_geometry,
)


ROOT = Path(__file__).resolve().parents[1]


def create_project(client, *, bays=2, trusses=8, name="Hala Alpha 4"):
    response = client.post("/api/projects", json={
        "name": name,
        "bay_count": bays,
        "default_truss_count": trusses,
        "note": "Dlouhá poznámka s českými a slovenskými znaky: příliš žluťoučký kôň.",
        "technician_name": "Tester",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_alpha4_features_are_preserved_in_current_release(client):
    assert APP_VERSION == "Alpha 7"
    assert client.get("/health").json()["version"] == "Alpha 7"
    assert "Alpha 7" in client.get("/login").text or "Alpha 7" in client.get("/").text
    assert "Alpha 7" in (ROOT / "README.md").read_text(encoding="utf-8").splitlines()[0]
    assert 'version = "0.7.0a7"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "zipp-diagnostics:alpha7" in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert not (ROOT / "app/static/alpha2.css").exists()
    assert (ROOT / "app/static/alpha7.css").is_file()


def test_font_profiles_have_larger_default_and_all_pdf_variants_work(client):
    project = create_project(
        client,
        bays=1,
        trusses=8,
        name="Výrobní hala Alpha 4 – mimořádně dlouhý český a slovenský název zákazky",
    )
    bay = project["bays"][0]
    bay_id = bay["id"]
    assert client.patch(f"/api/bays/{bay_id}", json={
        "name": "Loď A – severní montážní část / severná montážna časť", "technician_name": "Tester",
    }).status_code == 200
    trusses = bay["trusses"]
    assert client.patch(f"/api/trusses/{trusses[0]['id']}/label", json={
        "label": "V-103A – ŽLUŤOUČKÝ KÔŇ", "technician_name": "Tester",
        "expected_version": trusses[0]["version"],
    }).status_code == 200
    assert client.patch(f"/api/trusses/{trusses[1]['id']}/type", json={
        "type": "gable", "technician_name": "Tester", "expected_version": trusses[1]["version"],
    }).status_code == 200
    assert client.post(f"/api/bays/{bay_id}/dilation-pairs", json={
        "technician_name": "Tester", "truss_a_id": trusses[2]["id"], "truss_b_id": trusses[3]["id"],
        "expected_version_a": trusses[2]["version"], "expected_version_b": trusses[3]["version"],
    }).status_code == 201
    assert client.post(f"/api/trusses/{trusses[4]['id']}/exclude", json={
        "reason": "crack", "note": "Dlouhá poznámka s diakritikou: příliš žluťoučký kôň.",
        "technician_name": "Tester", "expected_version": trusses[4]["version"],
    }).status_code == 200
    assert FONT_PROFILES["10"].body == 10
    assert FONT_PROFILES["7"].body < FONT_PROFILES["10"].body < FONT_PROFILES["12"].body < FONT_PROFILES["14"].body
    for profile in FONT_PROFILES:
        response = client.get(f"/api/bays/{bay_id}/report.pdf?font_size={profile}&lang=cs")
        assert response.status_code == 200, response.text
        assert response.content.startswith(b"%PDF") and len(response.content) > 5_000
        assert response.headers["cache-control"] == "no-store"
    assert client.get(f"/api/bays/{bay_id}/report.pdf?font_size=large&lang=sk").status_code == 200
    assert client.get(f"/api/bays/{bay_id}/report.pdf?font_size=unknown").status_code == 422
    page = client.get(f"/bays/{bay_id}").text
    assert "data-export-dialog" in page and 'value="auto" selected' in page
    script = client.get("/static/app.js").text
    assert 'zipp.exportOptions' in script and 'font_size' in script


def _truss(position, pair_id=None, truss_type="normal"):
    return {
        "id": position,
        "position": position,
        "label": f"A{position}",
        "type": truss_type,
        "left_done": False,
        "right_done": False,
        "excluded": False,
        "exclusion_reason": None,
        "pair_id": pair_id,
    }


def test_explicit_dilation_pair_has_small_internal_gap_only():
    trusses = [_truss(position) for position in range(1, 9)]
    trusses[3]["pair_id"] = trusses[4]["pair_id"] = 77
    trusses[3]["type"] = trusses[4]["type"] = "dilation"
    project = {"name": "Geometrie", "bays": [{"id": 1, "position": 1, "name": "Loď A", "trusses": trusses}]}
    distances = build_plan_geometry(project).bays[0].distance_by_id
    assert distances[4] - distances[3] == TRUSS_SPACING
    assert distances[5] - distances[4] == DILATION_INTERNAL_SPACING
    assert distances[6] - distances[5] == TRUSS_SPACING
    assert DILATION_INTERNAL_SPACING < TRUSS_SPACING

    no_pair = [_truss(position, truss_type="dilation" if position in {4, 5} else "normal") for position in range(1, 9)]
    plain = {"name": "Bez páru", "bays": [{"id": 2, "position": 1, "name": "Loď A", "trusses": no_pair}]}
    plain_distances = build_plan_geometry(plain).bays[0].distance_by_id
    assert plain_distances[5] - plain_distances[4] == TRUSS_SPACING


def test_current_full_project_compatibility_helper_never_splits_project():
    trusses = [_truss(position) for position in range(1, 21)]
    trusses[17]["pair_id"] = trusses[18]["pair_id"] = 9
    project = {"name": "Stránkování", "bays": [{"id": 1, "position": 1, "name": "Loď A", "trusses": trusses}]}
    pages = _pdf_projects(project)
    assert len(pages) == 1
    assert [item["position"] for item in pages[0]["bays"][0]["trusses"]] == list(range(1, 21))


def test_project_rename_is_visible_audited_and_realtime_on_existing_channels(client, db):
    project = create_project(client)
    project_id = project["id"]
    original_bay_ids = [item["id"] for item in project["bays"]]
    original_truss_ids = [item["id"] for bay in project["bays"] for item in bay["trusses"]]
    html = client.get(f"/projects/{project_id}").text
    assert "data-open-project-rename" in html and "data-project-rename-dialog" in html

    with (
        client.websocket_connect(f"/ws/projects/{project_id}") as project_socket,
        client.websocket_connect("/ws/projects") as list_socket,
    ):
        assert project_socket.receive_json()["type"] == "connected"
        assert list_socket.receive_json()["type"] == "connected"
        response = client.patch(f"/api/projects/{project_id}/name", json={
            "name": "Přejmenovaná hala", "technician_name": "Tester",
        })
        assert response.status_code == 200
        assert project_socket.receive_json()["type"] == "project.renamed"
        assert list_socket.receive_json()["type"] == "project.renamed"

    state = client.get(f"/api/projects/{project_id}").json()
    assert state["id"] == project_id and state["name"] == "Přejmenovaná hala"
    assert [item["id"] for item in state["bays"]] == original_bay_ids
    assert [item["id"] for bay in state["bays"] for item in bay["trusses"]] == original_truss_ids
    assert db.scalar(select(func.count(AuditLog.id)).where(
        AuditLog.project_id == project_id, AuditLog.action == "project.name.changed"
    )) == 1


def test_permanent_delete_requires_name_is_atomic_and_realtime(client, db):
    project = create_project(client, bays=2, trusses=5, name="Hala ke smazání")
    kept = create_project(client, bays=1, trusses=2, name="Hala, která zůstane")
    project_id = project["id"]
    first_bay = project["bays"][0]
    trusses = first_bay["trusses"]
    done = client.put(f"/api/trusses/{trusses[0]['id']}/diagnostics/left", json={
        "done": True, "technician_name": "Tester", "expected_version": trusses[0]["version"],
    }).json()
    client.post(f"/api/trusses/{trusses[0]['id']}/exclude", json={
        "reason": "leak", "note": None, "technician_name": "Tester", "expected_version": done["version"],
    })
    client.post(f"/api/bays/{first_bay['id']}/dilation-pairs", json={
        "technician_name": "Tester", "truss_a_id": trusses[2]["id"], "truss_b_id": trusses[3]["id"],
        "expected_version_a": trusses[2]["version"], "expected_version_b": trusses[3]["version"],
    })
    html = client.get(f"/projects/{project_id}").text
    assert "data-project-delete-dialog" in html and "data-confirm-project-delete disabled" in html
    wrong = client.request("DELETE", f"/api/projects/{project_id}", json={
        "confirmation_name": "Jiná hala", "technician_name": "Tester",
    })
    assert wrong.status_code == 422
    assert client.get(f"/api/projects/{project_id}").status_code == 200

    with (
        client.websocket_connect(f"/ws/projects/{project_id}") as project_socket,
        client.websocket_connect("/ws/projects") as list_socket,
    ):
        project_socket.receive_json()
        list_socket.receive_json()
        deleted = client.request("DELETE", f"/api/projects/{project_id}", json={
            "confirmation_name": "Hala ke smazání", "technician_name": "Tester",
        })
        assert deleted.status_code == 200, deleted.text
        assert project_socket.receive_json()["type"] == "project.deleted"
        assert list_socket.receive_json()["type"] == "project.deleted"

    db.expire_all()
    assert db.get(Project, project_id) is None
    assert db.get(Project, kept["id"]) is not None
    assert db.scalar(select(func.count(Project.id))) == 1
    assert db.scalar(select(func.count(Bay.id))) == 1
    assert db.scalar(select(func.count(Truss.id))) == 2
    assert db.scalar(select(func.count(DilationPair.id))) == 0
    assert db.scalar(select(func.count(DilationPairMember.id))) == 0
    assert db.scalar(select(func.count(AuditLog.id))) == 1
    tombstone = db.scalar(select(ProjectDeletionLog).where(ProjectDeletionLog.project_id == project_id))
    assert tombstone and tombstone.project_name == "Hala ke smazání" and tombstone.action == "project.deleted"
    assert client.get(f"/projects/{project_id}").status_code == 404
    assert client.get(f"/api/projects/{project_id}/plan.svg").status_code == 404
    assert client.get(f"/api/projects/{project_id}/plan.pdf").status_code == 404
    assert client.get(f"/api/bays/{first_bay['id']}/report.pdf").status_code == 404
    assert client.get(f"/trusses/{trusses[0]['id']}").status_code == 404
