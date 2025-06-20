from fastapi import FastAPI
from app.api.routers import auth, groups
from app.api import websockets # Import the new websockets module

app = FastAPI(title="Synapse API Gateway", version="0.1.0")

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(groups.router, prefix="/groups", tags=["Chat Groups"])
app.include_router(websockets.router, tags=["WebSockets"]) # Include the WebSocket router

@app.get("/health", tags=["Status"])
def health_check():
    return {"status": "ok"}