import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import WebSocket


logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class Connection:
    id: str
    websocket: WebSocket
    connected_at: datetime
    send_lock: asyncio.Lock


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, dict[str, Connection]] = defaultdict(dict)

    async def connect(self, project_id: int, websocket: WebSocket) -> Connection:
        await websocket.accept()
        connection = Connection(uuid4().hex[:12], websocket, datetime.now(timezone.utc), asyncio.Lock())
        self._connections[project_id][connection.id] = connection
        logger.info("WebSocket connected project=%s connection=%s clients=%s", project_id, connection.id,
                    len(self._connections[project_id]))
        return connection

    def disconnect(self, project_id: int, connection_id: str, *, code: int | None = None, reason: str = "") -> None:
        connections = self._connections.get(project_id)
        if not connections:
            return
        connections.pop(connection_id, None)
        logger.info("WebSocket disconnected project=%s connection=%s code=%s reason=%s clients=%s",
                    project_id, connection_id, code, reason[:160], len(connections))
        if not connections:
            self._connections.pop(project_id, None)

    async def broadcast(self, project_id: int, message: dict) -> None:
        connections = tuple(self._connections.get(project_id, {}).items())

        async def send(connection_id: str, connection: Connection) -> str | None:
            try:
                await asyncio.wait_for(self.send_json(connection, message), timeout=5)
                return None
            except Exception as exc:
                logger.warning("WebSocket broadcast failed project=%s connection=%s error=%s",
                               project_id, connection_id, type(exc).__name__)
                return connection_id

        dead = [item for item in await asyncio.gather(*(send(*item) for item in connections)) if item]
        for connection_id in dead:
            self.disconnect(project_id, connection_id, reason="broadcast_failed")

    async def send_json(self, connection: Connection, message: dict) -> None:
        async with connection.send_lock:
            await connection.websocket.send_json(message)

    async def send_text(self, connection: Connection, message: str) -> None:
        async with connection.send_lock:
            await connection.websocket.send_text(message)

    def client_count(self, project_id: int | None = None) -> int:
        if project_id is not None:
            return len(self._connections.get(project_id, {}))
        return sum(len(items) for items in self._connections.values())


manager = ConnectionManager()
