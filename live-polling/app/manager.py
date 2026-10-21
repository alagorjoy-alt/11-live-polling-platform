"""Tracks WebSocket clients per poll and broadcasts messages to them."""
import logging
from collections import defaultdict

from fastapi import WebSocket

log = logging.getLogger("polling.ws")


class ConnectionManager:
    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, poll_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.rooms[poll_id].add(ws)

    def disconnect(self, poll_id: str, ws: WebSocket) -> None:
        room = self.rooms.get(poll_id)
        if room is None:
            return
        room.discard(ws)
        if not room:
            self.rooms.pop(poll_id, None)

    async def broadcast(self, poll_id: str, message: dict) -> None:
        for ws in list(self.rooms.get(poll_id, ())):
            try:
                await ws.send_json(message)
            except Exception:  # dead socket: drop it, keep broadcasting to the rest
                log.info("dropping dead websocket for poll %s", poll_id)
                self.disconnect(poll_id, ws)

    @property
    def active_connections(self) -> int:
        return sum(len(v) for v in self.rooms.values())


manager = ConnectionManager()
