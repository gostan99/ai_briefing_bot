"""FastAPI app entry point."""

from __future__ import annotations

from fastapi import FastAPI

from app.routers import subscriptions, webhooks


def create_app() -> FastAPI:
    """Build FastAPI application."""

    app = FastAPI(title="AI Briefing Bot", version="0.1.0")
    app.include_router(subscriptions.router)
    app.include_router(webhooks.router)

    @app.get("/healthz", tags=["health"])
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
