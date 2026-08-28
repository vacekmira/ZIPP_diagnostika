"""Live multi-client WebSocket stability test against a running Uvicorn server."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from urllib.parse import urlparse

import httpx
import websockets


def cookie_header(client: httpx.AsyncClient) -> str:
    return "; ".join(f"{key}={value}" for key, value in client.cookies.items())


async def run(base_url: str, password: str, duration: int) -> None:
    async with (
        httpx.AsyncClient(base_url=base_url, follow_redirects=False, timeout=15) as first_http,
        httpx.AsyncClient(base_url=base_url, follow_redirects=False, timeout=15) as second_http,
    ):
        for client in (first_http, second_http):
            response = await client.post("/login", data={"password": password, "next": "/"})
            if response.status_code != 303:
                raise RuntimeError(f"Přihlášení selhalo: {response.status_code} {response.text[:200]}")
        response = await first_http.post("/api/projects", json={
            "name": f"Stability {int(time.time())}", "bay_count": 2, "default_truss_count": 8,
            "note": "Automatický live test", "technician_name": "Stability A",
        })
        response.raise_for_status()
        project = response.json()
        parsed = urlparse(base_url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = f"{ws_scheme}://{parsed.netloc}/ws/projects/{project['id']}"

        async with (
            websockets.connect(ws_url, additional_headers={"Cookie": cookie_header(first_http)}, ping_interval=20, ping_timeout=20) as first_ws,
            websockets.connect(ws_url, additional_headers={"Cookie": cookie_header(second_http)}, ping_interval=20, ping_timeout=20) as second_ws,
        ):
            for websocket in (first_ws, second_ws):
                connected = json.loads(await asyncio.wait_for(websocket.recv(), 10))
                assert connected["type"] == "connected"

            async def expect(event_type: str) -> list[dict]:
                events = []
                for websocket in (first_ws, second_ws):
                    raw = await asyncio.wait_for(websocket.recv(), 10)
                    event = json.loads(raw)
                    if event.get("type") != event_type:
                        raise AssertionError(f"Očekáváno {event_type}, přijato {event}")
                    events.append(event)
                return events

            async def request(method: str, url: str, payload: dict, event_type: str) -> dict:
                changed = await first_http.request(method, url, json=payload)
                changed.raise_for_status()
                await expect(event_type)
                return changed.json()

            bay_a, bay_b = project["bays"]
            await request("PATCH", f"/api/bays/{bay_b['id']}", {
                "name": "Stability druhá loď", "technician_name": "Stability B",
            }, "bay.updated")
            trusses = bay_a["trusses"]
            trusses[0] = await request("PATCH", f"/api/trusses/{trusses[0]['id']}/type", {
                "type": "gable", "technician_name": "Stability A", "expected_version": trusses[0]["version"],
            }, "truss.updated")
            pair = await request("POST", f"/api/bays/{bay_a['id']}/dilation-pairs", {
                "technician_name": "Stability A", "truss_a_id": trusses[1]["id"], "truss_b_id": trusses[2]["id"],
                "expected_version_a": trusses[1]["version"], "expected_version_b": trusses[2]["version"],
            }, "dilation_pair.created")
            trusses[1], trusses[2] = pair["members"]
            trusses[3] = await request("POST", f"/api/trusses/{trusses[3]['id']}/exclude", {
                "reason": "crack", "note": None, "technician_name": "Stability B", "expected_version": trusses[3]["version"],
            }, "truss.excluded")
            trusses[3] = await request("POST", f"/api/trusses/{trusses[3]['id']}/restore", {
                "technician_name": "Stability B", "expected_version": trusses[3]["version"],
            }, "truss.restored")
            removed = await request("POST", f"/api/dilation-pairs/{pair['id']}/remove", {
                "technician_name": "Stability A", "type_a": "normal", "type_b": "normal",
                "expected_version_a": trusses[1]["version"], "expected_version_b": trusses[2]["version"],
            }, "dilation_pair.removed")
            trusses[1], trusses[2] = removed["members"]

            idle = min(45, max(5, duration // 8))
            await asyncio.sleep(idle)
            for websocket in (first_ws, second_ws):
                await websocket.send("ping")
                assert await asyncio.wait_for(websocket.recv(), 10) == "pong"

            deadline = time.monotonic() + max(1, duration - idle)
            operations = 0
            done = trusses[0]["left_done"]
            while time.monotonic() < deadline:
                done = not done
                trusses[0] = await request("PUT", f"/api/trusses/{trusses[0]['id']}/diagnostics/left", {
                    "done": done, "technician_name": "Stability A", "expected_version": trusses[0]["version"],
                }, "truss.updated")
                state = await second_http.get(f"/api/projects/{project['id']}")
                state.raise_for_status()
                svg = await second_http.get(f"/api/projects/{project['id']}/plan.svg?lang=sk")
                svg.raise_for_status()
                assert trusses[0]["label"] in svg.text and "Pôdorys objektu" in svg.text
                operations += 1
                await asyncio.sleep(min(5, max(0, deadline - time.monotonic())))
            print(json.dumps({"status": "live_stability_ok", "duration_seconds": duration,
                              "operations": operations, "project_id": project["id"]}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--password", required=True)
    parser.add_argument("--seconds", type=int, default=600)
    args = parser.parse_args()
    asyncio.run(run(args.base_url, args.password, args.seconds))


if __name__ == "__main__":
    main()
