from fastapi import FastAPI

app = FastAPI(
    title="Synapse API Gateway",
    version="0.1.0"
)

@app.get("/health", tags=["Status"])
def health_check():
    """Check if the service is running."""
    return {"status": "ok"}

# We will add routers for /auth, /groups, etc. here in Phase 1