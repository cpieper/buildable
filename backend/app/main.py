from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from app.api.auth import router as auth_router
from app.config import Settings, get_settings
from app.db import upgrade_database


def create_app(
    *,
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if session_factory is None:
            app_settings.data_dir.mkdir(parents=True, exist_ok=True)
            upgrade_database(app_settings.database_url)
        yield

    app = FastAPI(title="What2Build", version="0.1.0", lifespan=lifespan)
    app.state.settings = app_settings
    app.include_router(auth_router)

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
