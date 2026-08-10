from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from app.api.auth import router as auth_router
from app.api.backups import router as backups_router
from app.api.catalog import router as catalog_router
from app.api.collection import router as collection_router
from app.api.equivalence import router as equivalence_router
from app.api.inventory import router as inventory_router
from app.api.matches import router as matches_router
from app.api.overrides import router as overrides_router
from app.api.recommendations import router as recommendations_router
from app.api.settings import router as settings_router
from app.config import Settings, get_settings
from app.db import get_session, upgrade_database


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
    if session_factory is not None:

        def get_injected_session() -> Iterator[Session]:
            with session_factory() as session:
                yield session

        app.dependency_overrides[get_session] = get_injected_session
    app.include_router(auth_router)
    app.include_router(backups_router)
    app.include_router(catalog_router)
    app.include_router(collection_router)
    app.include_router(inventory_router)
    app.include_router(matches_router)
    app.include_router(overrides_router)
    app.include_router(equivalence_router)
    app.include_router(recommendations_router)
    app.include_router(settings_router)

    @app.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
