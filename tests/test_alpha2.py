import pytest
from starlette.websockets import WebSocketDisconnect

from app.auth import set_password
from app.models import AppSettings


def create_project(client, *, bays=1, trusses=7, name="Hala Žilina"):
    response = client.post("/api/projects", json={
        "name": name, "bay_count": bays, "default_truss_count": trusses,
        "note": "Uživatelská data", "technician_name": "Tester",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_business_pages_api_and_websocket_require_authentication(client, project):
    client.cookies.clear()
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/api/projects").status_code == 401
    assert client.get(f"/api/projects/{project['id']}/plan.svg").status_code == 401
    assert client.get(f"/api/projects/{project['id']}/plan.pdf").status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/favicon.ico").status_code == 204
    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect(f"/ws/projects/{project['id']}"):
            pass
    assert rejected.value.code == 4401


def test_bad_and_good_password_and_session_invalidation(client, db, project):
    client.cookies.clear()
    assert client.post("/login", data={"password": "bad-password", "next": "/"}).status_code == 401
    logged_in = client.post(
        "/login", data={"password": "test-password-123", "next": "/"}, follow_redirects=False,
    )
    assert logged_in.status_code == 303
    cookie = logged_in.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    password_hash = db.get(AppSettings, 1).password_hash
    assert password_hash.startswith("$argon2id$") and "test-password-123" not in password_hash
    assert client.get("/api/projects").status_code == 200

    with client.websocket_connect(f"/ws/projects/{project['id']}") as websocket:
        assert websocket.receive_json()["type"] == "connected"
        set_password(db, "new-password-456")
        websocket.send_text("ping")
        with pytest.raises(WebSocketDisconnect) as disconnected:
            websocket.receive_text()
        assert disconnected.value.code == 4401

    assert client.get("/api/projects").status_code == 401
    client.cookies.clear()
    assert client.post("/login", data={"password": "test-password-123"}).status_code == 401
    assert client.post(
        "/login", data={"password": "new-password-456"}, follow_redirects=False,
    ).status_code == 303


def test_czech_and_slovak_ui_keep_user_data_unchanged(client, project):
    client.cookies.set("zipp_language", "cs")
    czech = client.get("/").text
    assert "Aktivní zakázky" in czech and project["name"] in czech
    client.cookies.set("zipp_language", "sk")
    slovak = client.get("/").text
    assert 'lang="sk"' in slovak
    assert "Aktívne zákazky" in slovak and project["name"] in slovak
    assert "Pôdorys objektu" in client.get(f"/projects/{project['id']}/plan").text
    svg = client.get(f"/api/projects/{project['id']}/plan.svg?lang=sk").text
    assert "Pôdorys objektu" in svg and project["name"] in svg
    assert 'localStorage.setItem("zipp.language"' in client.get("/static/app.js").text
    client.cookies.set("zipp_language", "cs")
    assert "Aktivní zakázky" in client.get("/").text


def test_critical_default_labels_manual_label_and_plan_symbols(client):
    project = create_project(client, bays=3, trusses=7)
    assert [[truss["label"] for truss in bay["trusses"][:5]] for bay in project["bays"]] == [
        ["A1", "A2", "A3", "A4", "A5"],
        ["B1", "B2", "B3", "B4", "B5"],
        ["C1", "C2", "C3", "C4", "C5"],
    ]
    b3 = project["bays"][1]["trusses"][2]
    renamed = client.patch(f"/api/trusses/{b3['id']}/label", json={
        "label": "V-217", "technician_name": "Tester", "expected_version": b3["version"],
    }).json()
    assert renamed["id"] == b3["id"] and renamed["position"] == b3["position"] and renamed["label"] == "V-217"

    bay = client.get(f"/api/bays/{project['bays'][0]['id']}").json()
    a1, a2, a3, a4, a5, a6, a7 = bay["trusses"]
    assert client.patch(f"/api/trusses/{a2['id']}/type", json={
        "type": "gable", "technician_name": "Tester", "expected_version": a2["version"],
    }).status_code == 200
    pair = client.post(f"/api/bays/{bay['id']}/dilation-pairs", json={
        "technician_name": "Tester", "truss_a_id": a3["id"], "truss_b_id": a4["id"],
        "expected_version_a": a3["version"], "expected_version_b": a4["version"],
    })
    assert pair.status_code == 201
    for truss, reason, note in ((a5, "crack", None), (a6, "leak", None), (a7, "other", "Kontrola")):
        response = client.post(f"/api/trusses/{truss['id']}/exclude", json={
            "reason": reason, "note": note, "technician_name": "Tester", "expected_version": truss["version"],
        })
        assert response.status_code == 200, response.text

    renamed_bay = client.patch(f"/api/bays/{bay['id']}", json={"name": "Střední loď", "technician_name": "Tester"})
    assert renamed_bay.status_code == 200
    svg = client.get(f"/api/projects/{project['id']}/plan.svg?lang=cs").text
    for text in (
        "Střední loď", "V-217", "A1", "A2 - ŠTÍTOVÝ", "A3 - DILATAČNÍ",
        "A4 - DILATAČNÍ", "A5 - TRHLINA", "A6 - ZATEČENÝ", "A7 - JINÉ",
    ):
        assert text in svg
    for dash in ('stroke-dasharray="12 5 2 5"', 'stroke-dasharray="9 5"', 'stroke-dasharray="2 5"'):
        assert dash in svg
    assert 'class="pair"' in svg and "Dilatační dvojice" in svg
    assert ">P</text>" in svg and ">L</text>" in svg

    pdf = client.get(f"/api/projects/{project['id']}/plan.pdf?lang=cs")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF") and len(pdf.content) > 5_000


def test_plan_realtime_event_and_restore_changes_svg(client):
    project = create_project(client, bays=1, trusses=2, name="Realtime hala")
    truss = project["bays"][0]["trusses"][0]
    with client.websocket_connect(f"/ws/projects/{project['id']}") as websocket:
        assert websocket.receive_json()["type"] == "connected"
        excluded = client.post(f"/api/trusses/{truss['id']}/exclude", json={
            "reason": "crack", "note": None, "technician_name": "Tester", "expected_version": truss["version"],
        }).json()
        event = websocket.receive_json()
        assert event["type"] == "truss.excluded" and event["project_revision"]
        assert "V1 - TRHLINA" in client.get(f"/api/projects/{project['id']}/plan.svg").text
        restored = client.post(f"/api/trusses/{truss['id']}/restore", json={
            "technician_name": "Tester", "expected_version": excluded["version"],
        })
        assert restored.status_code == 200
        assert websocket.receive_json()["type"] == "truss.restored"
        assert "V1 - TRHLINA" not in client.get(f"/api/projects/{project['id']}/plan.svg").text
