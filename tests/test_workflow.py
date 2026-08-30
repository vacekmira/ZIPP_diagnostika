from sqlalchemy import func, select

from app.models import AuditLog, DilationPair, Project, Truss


def test_project_creates_bays_and_default_labels(client, project):
    assert len(project["bays"]) == 2
    assert [bay["name"] for bay in project["bays"]] == ["Loď A", "Loď B"]
    assert [t["label"] for t in project["bays"][0]["trusses"]] == ["A1", "A2", "A3", "A4"]
    assert project["progress"] == {"completed": 0, "required": 16, "remaining": 16, "excluded": 0, "percent": 0}


def test_main_html_pages_render_without_external_dependencies(client, project):
    assert client.get("/").status_code == 200
    assert client.get(f"/projects/{project['id']}").status_code == 200
    assert client.get(f"/projects/{project['id']}/plan").status_code == 200
    bay_id = project["bays"][0]["id"]
    assert client.get(f"/bays/{bay_id}").status_code == 200
    assert client.get(f"/bays/{bay_id}/settings").status_code == 200
    truss_id = project["bays"][0]["trusses"][0]["id"]
    assert client.get(f"/trusses/{truss_id}").status_code == 200
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/alpha4.css").status_code == 200
    assert "https://" not in client.get("/static/app.css").text


def test_websocket_broadcasts_committed_change(client, project):
    truss = project["bays"][0]["trusses"][0]
    with client.websocket_connect(f"/ws/projects/{project['id']}") as websocket:
        assert websocket.receive_json()["type"] == "connected"
        changed = client.put(f"/api/trusses/{truss['id']}/diagnostics/left", json={
            "done": True, "technician_name": "Novák", "expected_version": truss["version"],
        })
        assert changed.status_code == 200
        event = websocket.receive_json()
        assert event["type"] == "truss.updated"
        assert event["truss"]["id"] == truss["id"]
        assert event["truss"]["left_done"] is True


def test_bay_name_and_text_label_preserve_identity_and_diagnostics(client, project, db):
    bay = project["bays"][0]
    truss = bay["trusses"][0]
    renamed = client.patch(f"/api/bays/{bay['id']}", json={"name": "Střední loď", "technician_name": "Novák"})
    assert renamed.status_code == 200
    done = client.put(f"/api/trusses/{truss['id']}/diagnostics/left", json={
        "done": True, "technician_name": "Novák", "expected_version": truss["version"],
    }).json()
    changed = client.patch(f"/api/trusses/{truss['id']}/label", json={
        "label": "V-103A", "technician_name": "Svoboda", "expected_version": done["version"],
    })
    assert changed.status_code == 200
    result = changed.json()
    assert result["id"] == truss["id"]
    assert result["position"] == truss["position"]
    assert result["label"] == "V-103A"
    assert result["left_done"] is True
    assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.truss_id == truss["id"])) == 2


def test_toggle_both_sides_and_optimistic_conflict(client, project):
    truss = project["bays"][0]["trusses"][0]
    left = client.put(f"/api/trusses/{truss['id']}/diagnostics/left", json={
        "done": True, "technician_name": "Novák", "expected_version": truss["version"],
    }).json()
    conflict = client.put(f"/api/trusses/{truss['id']}/diagnostics/right", json={
        "done": True, "technician_name": "Svoboda", "expected_version": truss["version"],
    })
    assert conflict.status_code == 409
    right = client.put(f"/api/trusses/{truss['id']}/diagnostics/right", json={
        "done": True, "technician_name": "Svoboda", "expected_version": left["version"],
    }).json()
    undone = client.put(f"/api/trusses/{truss['id']}/diagnostics/left", json={
        "done": False, "technician_name": "Novák", "expected_version": right["version"],
    }).json()
    assert undone["left_done"] is False and undone["right_done"] is True


def test_critical_exclusion_preserves_diagnostics_and_progress(client, project):
    truss = project["bays"][0]["trusses"][0]
    left = client.put(f"/api/trusses/{truss['id']}/diagnostics/left", json={
        "done": True, "technician_name": "Novák", "expected_version": truss["version"],
    }).json()
    excluded = client.post(f"/api/trusses/{truss['id']}/exclude", json={
        "reason": "crack", "note": None, "technician_name": "Novák", "expected_version": left["version"],
    }).json()
    assert excluded["left_done"] is True and excluded["right_done"] is False and excluded["excluded"] is True
    blocked = client.put(f"/api/trusses/{truss['id']}/diagnostics/right", json={
        "done": True, "technician_name": "Novák", "expected_version": excluded["version"],
    })
    assert blocked.status_code == 409
    state = client.get(f"/api/projects/{project['id']}").json()
    assert state["progress"]["required"] == 15
    assert state["progress"]["completed"] == 1
    restored = client.post(f"/api/trusses/{truss['id']}/restore", json={
        "technician_name": "Novák", "expected_version": excluded["version"],
    }).json()
    assert restored["left_done"] is True and restored["right_done"] is False and restored["excluded"] is False
    assert client.get(f"/api/projects/{project['id']}").json()["progress"]["required"] == 16


def test_other_exclusion_requires_note(client, project):
    truss = project["bays"][0]["trusses"][0]
    response = client.post(f"/api/trusses/{truss['id']}/exclude", json={
        "reason": "other", "note": "", "technician_name": "Novák", "expected_version": truss["version"],
    })
    assert response.status_code == 422


def test_dilation_pair_is_explicit_adjacent_and_removed_atomically(client, project, db):
    bay = project["bays"][0]
    a, b, non_adjacent = bay["trusses"][1], bay["trusses"][2], bay["trusses"][3]
    invalid = client.post(f"/api/bays/{bay['id']}/dilation-pairs", json={
        "technician_name": "Novák", "truss_a_id": a["id"], "truss_b_id": non_adjacent["id"],
        "expected_version_a": a["version"], "expected_version_b": non_adjacent["version"],
    })
    assert invalid.status_code == 422
    created = client.post(f"/api/bays/{bay['id']}/dilation-pairs", json={
        "technician_name": "Novák", "truss_a_id": a["id"], "truss_b_id": b["id"],
        "expected_version_a": a["version"], "expected_version_b": b["version"],
    })
    assert created.status_code == 201, created.text
    pair = created.json()
    assert [member["type"] for member in pair["members"]] == ["dilation", "dilation"]
    assert db.scalar(select(func.count(DilationPair.id))) == 1
    single_change = client.patch(f"/api/trusses/{a['id']}/type", json={
        "type": "normal", "technician_name": "Novák", "expected_version": pair["members"][0]["version"],
    })
    assert single_change.status_code == 409
    removed = client.post(f"/api/dilation-pairs/{pair['id']}/remove", json={
        "technician_name": "Novák", "type_a": "normal", "type_b": "gable",
        "expected_version_a": pair["members"][0]["version"], "expected_version_b": pair["members"][1]["version"],
    })
    assert removed.status_code == 200, removed.text
    assert [item["type"] for item in removed.json()["members"]] == ["normal", "gable"]


def test_cross_bay_pair_rejected(client, project):
    a = project["bays"][0]["trusses"][0]
    b = project["bays"][1]["trusses"][1]
    response = client.post(f"/api/bays/{project['bays'][0]['id']}/dilation-pairs", json={
        "technician_name": "Novák", "truss_a_id": a["id"], "truss_b_id": b["id"],
        "expected_version_a": a["version"], "expected_version_b": b["version"],
    })
    assert response.status_code == 422


def test_duplicate_labels_allowed_and_reported(client, project):
    bay = project["bays"][0]
    a, b = bay["trusses"][:2]
    result = client.post(f"/api/bays/{bay['id']}/labels/bulk", json={"technician_name": "Novák", "items": [
        {"truss_id": a["id"], "label": "V17", "expected_version": a["version"]},
        {"truss_id": b["id"], "label": "v17", "expected_version": b["version"]},
    ]})
    assert result.status_code == 200
    state = client.get(f"/api/bays/{bay['id']}").json()
    assert state["trusses"][0]["duplicate_label"] is True
    assert state["trusses"][1]["duplicate_label"] is True


def test_resize_never_deletes_diagnostic_data(client, project, db):
    bay = project["bays"][0]
    last = bay["trusses"][-1]
    done = client.put(f"/api/trusses/{last['id']}/diagnostics/left", json={
        "done": True, "technician_name": "Novák", "expected_version": last["version"],
    }).json()
    preview = client.post(f"/api/bays/{bay['id']}/resize", json={
        "truss_count": 3, "confirm": False, "technician_name": "Novák",
    })
    assert preview.status_code == 409
    shrunk = client.post(f"/api/bays/{bay['id']}/resize", json={
        "truss_count": 3, "confirm": True, "technician_name": "Novák",
    })
    assert shrunk.status_code == 200
    stored = db.get(Truss, last["id"])
    assert stored is not None and stored.left_done is True and stored.retired_at is not None


def test_archive_is_read_only_and_reactivation_audited(client, project, db):
    archived = client.post(f"/api/projects/{project['id']}/archive", json={"technician_name": "Novák"})
    assert archived.status_code == 200
    truss = project["bays"][0]["trusses"][0]
    blocked = client.put(f"/api/trusses/{truss['id']}/diagnostics/left", json={
        "done": True, "technician_name": "Novák", "expected_version": truss["version"],
    })
    assert blocked.status_code == 409
    assert client.post(f"/api/projects/{project['id']}/reactivate", json={"technician_name": "Svoboda"}).status_code == 200
    assert db.get(Project, project["id"]).archived is False
    actions = db.scalars(select(AuditLog.action).where(AuditLog.project_id == project["id"])).all()
    assert "project.archived" in actions and "project.reactivated" in actions
