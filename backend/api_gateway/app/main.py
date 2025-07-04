from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routers import auth, groups
from app.api.routers import system # Import the new system router
from app.api import websockets
from app.core.arq_client import init_arq_pool, close_arq_pool
from shared.app.core.logging import setup_logging

setup_logging()

app = FastAPI(title="Synapse API Gateway", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.on_event("startup")
async def on_startup() -> None:
    await init_arq_pool()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await close_arq_pool()


app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(groups.router, prefix="/groups", tags=["Chat Groups"])
app.include_router(system.router, prefix="/system", tags=["System Information"]) # Include system router
app.include_router(
    websockets.router, tags=["WebSockets"]
)


@app.get("/health", tags=["Status"])
def health_check():
    return {"status": "ok"}