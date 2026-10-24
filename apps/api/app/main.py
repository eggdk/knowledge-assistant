"""HTTP entry point for the knowledge-assistant backend."""

from fastapi import FastAPI

from app.api_routes import router as knowledge_base_router

app = FastAPI(title="Knowledge Assistant API")
app.include_router(knowledge_base_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Confirm that the API process can receive and answer a request."""
    return {"status": "ok"}
