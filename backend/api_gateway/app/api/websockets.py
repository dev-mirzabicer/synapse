import asyncio
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException, HTTPException, Depends, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.arq_client import get_arq_pool
from app.core.security import get_user_from_token
from shared.app.db import get_db_session
from shared.app.models.chat import ChatGroup, User

router = APIRouter()

logger = structlog.get_logger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, group_id: str):
        await websocket.accept()
        if group_id not in self.active_connections:
            self.active_connections[group_id] = []
        self.active_connections[group_id].append(websocket)

    def disconnect(self, websocket: WebSocket, group_id: str):
        if group_id in self.active_connections:
            self.active_connections[group_id].remove(websocket)

    async def broadcast_to_group(self, group_id: str, message: str) -> None:
        for connection in self.active_connections.get(group_id, []):
            try:
                await connection.send_text(message)
            except RuntimeError:
                # Connection might already be closed; ignore
                pass


manager = ConnectionManager()


async def redis_listener(redis: Redis, group_id: str):
    """Listens to a Redis channel and broadcasts messages."""
    channel = f"group:{group_id}"
    try:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
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
    except Exception as e:
        await pubsub.unsubscribe(channel)
        raise HTTPException(status_code=500, detail=f"Redis listener error: {e}")


@router.websocket("/ws/{group_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    group_id: str,
    redis: Redis = Depends(get_arq_pool),
    db: async_sessionmaker = Depends(get_db_session),
):
    """WebSocket endpoint for streaming chat events to authorized clients."""

    token = websocket.query_params.get("token")
    if token is None:
        auth = websocket.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth[7:]

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        current_user = await get_user_from_token(token, db)
    except WebSocketException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with db() as session:
        group = await session.get(ChatGroup, group_id)
        if not group or group.owner_id != current_user.id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    try:
        await manager.connect(websocket, group_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to establish WebSocket: {e}")
    listener_task = asyncio.create_task(redis_listener(redis, group_id))
    logger.info("websocket.connected", user=current_user.email, group_id=group_id)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("websocket.disconnected", user=current_user.email)
    finally:
        listener_task.cancel()
        manager.disconnect(websocket, group_id)
