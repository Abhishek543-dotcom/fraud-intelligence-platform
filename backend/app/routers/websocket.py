import asyncio
import json
import time
from datetime import datetime

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = structlog.get_logger()
router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections with rate limiting."""

    def __init__(self, max_connections: int = 100, max_messages_per_second: int = 10):
        self.active_connections: list[WebSocket] = []
        self.max_connections = max_connections
        self.max_messages_per_second = max_messages_per_second
        self._message_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)

    async def connect(self, websocket: WebSocket) -> bool:
        if len(self.active_connections) >= self.max_connections:
            await websocket.close(code=1013, reason="Max connections reached")
            return False
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("ws_connected", total=len(self.active_connections))
        return True

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("ws_disconnected", total=len(self.active_connections))

    async def broadcast(self, message: dict) -> None:
        """Broadcast message to all connected clients."""
        if not self.active_connections:
            return

        data = json.dumps(message)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def enqueue(self, message: dict) -> None:
        """Add message to broadcast queue."""
        try:
            self._message_queue.put_nowait(message)
        except asyncio.QueueFull:
            pass  # Drop message if queue is full

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)


manager = ConnectionManager()


@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """WebSocket endpoint for real-time fraud alert streaming."""
    connected = await manager.connect(websocket)
    if not connected:
        return

    heartbeat_interval = 30
    last_heartbeat = time.time()

    try:
        while True:
            # Non-blocking check for client messages (ping/pong)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "data": {"timestamp": datetime.utcnow().isoformat()},
                    }))
            except asyncio.TimeoutError:
                pass
            except json.JSONDecodeError:
                pass

            # Send heartbeat
            now = time.time()
            if now - last_heartbeat >= heartbeat_interval:
                await websocket.send_text(json.dumps({
                    "type": "heartbeat",
                    "data": {"timestamp": datetime.utcnow().isoformat()},
                }))
                last_heartbeat = now

            # Drain broadcast queue
            messages_sent = 0
            while messages_sent < manager.max_messages_per_second:
                try:
                    msg = manager._message_queue.get_nowait()
                    await websocket.send_text(json.dumps(msg))
                    messages_sent += 1
                except asyncio.QueueEmpty:
                    break

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("ws_error", error=str(e))
        manager.disconnect(websocket)
