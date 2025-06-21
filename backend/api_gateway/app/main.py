from fastapi import FastAPI
from app.api.routers import auth, groups
from app.api import websockets  # Import the new websockets module
from app.core.arq_client import init_arq_pool, close_arq_pool
from shared.app.core.logging import setup_logging

setup_logging()

app = FastAPI(title="Synapse API Gateway", version="0.1.0")


@app.on_event("startup")
async def on_startup() -> None:
    await init_arq_pool()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await close_arq_pool()


app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(groups.router, prefix="/groups", tags=["Chat Groups"])
app.include_router(
    websockets.router, tags=["WebSockets"]
)  # Include the WebSocket router


@app.get("/health", tags=["Status"])
def health_check():
    return {"status": "ok"}
