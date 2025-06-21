import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from redis.asyncio import Redis

from app.core.arq_client import get_arq_pool  # Re-using the pool for Redis connection
from app.core.security import get_current_user  # We can also secure websockets
from shared.app.models.chat import User

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, group_id: str):
        await websocket.accept()
        if group_id not in self.active_connections:
            self.active_connections[group_id] = []
        self.active_connections[group_id].append(websocket)

    def disconnect(self, websocket: WebSocket, group_id: str):
        if group_id in self.active_connections:
            self.active_connections[group_id].remove(websocket)

    async def broadcast_to_group(self, group_id: str, message: str):
        if group_id in self.active_connections:
            for connection in self.active_connections[group_id]:
                await connection.send_text(message)


manager = ConnectionManager()


async def redis_listener(redis: Redis, group_id: str):
    """Listens to a Redis channel and broadcasts messages."""
    channel = f"group:{group_id}"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message:
                await manager.broadcast_to_group(
                    group_id, message["data"].decode("utf-8")
                )
            await asyncio.sleep(0.01)  # Prevent busy-waiting
    except asyncio.CancelledError:
        await pubsub.unsubscribe(channel)


@router.websocket("/ws/{group_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    group_id: str,
    # current_user: User = Depends(get_current_user) # TODO: Figure out WS authentication
    redis: Redis = Depends(get_arq_pool),
):
    # TODO (Phase 4): Implement robust WebSocket authentication.
    # This is tricky as headers are not sent per message.
    # A common pattern is to send the token as the first message.

    await manager.connect(websocket, group_id)
    listener_task = asyncio.create_task(redis_listener(redis, group_id))

    try:
        while True:
            # We keep the connection alive by waiting for data.
            # The client can send pings, or we can implement a server-side ping.
            await websocket.receive_text()
    except WebSocketDisconnect:
        listener_task.cancel()
        manager.disconnect(websocket, group_id)
