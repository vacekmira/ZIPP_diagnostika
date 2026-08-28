import os
import time

import pytest


@pytest.mark.stability
@pytest.mark.skipif(os.getenv("RUN_STABILITY") != "1", reason="Spusťte s RUN_STABILITY=1")
def test_two_clients_stay_connected_and_receive_every_change(client, project):
    """10-minute by default; STABILITY_SECONDS may shorten it for development."""
    duration = int(os.getenv("STABILITY_SECONDS", "600"))
    truss = project["bays"][0]["trusses"][0]
    version = truss["version"]
    done = False
    deadline = time.monotonic() + duration
    next_change = time.monotonic()
    with (
        client.websocket_connect(f"/ws/projects/{project['id']}") as first,
        client.websocket_connect(f"/ws/projects/{project['id']}") as second,
    ):
        assert first.receive_json()["type"] == "connected"
        assert second.receive_json()["type"] == "connected"
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now < next_change:
                time.sleep(min(0.25, next_change - now))
                continue
            done = not done
            response = client.put(f"/api/trusses/{truss['id']}/diagnostics/left", json={
                "done": done, "technician_name": "Stability", "expected_version": version,
            })
            assert response.status_code == 200, response.text
            version = response.json()["version"]
            for websocket in (first, second):
                event = websocket.receive_json()
                assert event["type"] == "truss.updated"
                assert event["truss"]["version"] == version
                assert event["truss"]["left_done"] is done
                websocket.send_text("ping")
                assert websocket.receive_text() == "pong"
            next_change = now + 5
