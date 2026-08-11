from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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
from app.db import SessionFactory, get_session, upgrade_database
from app.services.auth import PasswordStore


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
        if settings is None or app_settings.initial_password is not None:
            factory = session_factory or SessionFactory
            with factory() as session:
                password_store = PasswordStore(session)
                if password_store.session_binding() is None:
                    if not app_settings.initial_password:
                        raise RuntimeError(
                            "No shared password is configured. Set "
                            "BUILDABLE_INITIAL_PASSWORD before first startup."
                        )
                    password_store.set_password(app_settings.initial_password)
        yield

    app = FastAPI(title="Buildable", version="0.1.0", lifespan=lifespan)
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

    frontend_dir = app_settings.frontend_dir
    if frontend_dir is not None and frontend_dir.is_dir():
        assets_dir = frontend_dir / "_app"
        index_path = frontend_dir / "index.html"
        if assets_dir.is_dir():
            app.mount("/_app", StaticFiles(directory=assets_dir), name="frontend-assets")

        @app.middleware("http")
        async def cache_fingerprinted_assets(request: Request, call_next):
            response = await call_next(request)
            if request.url.path.startswith("/_app/") and response.status_code == 200:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

        if index_path.is_file():

            @app.get("/{path:path}", include_in_schema=False)
            def spa_fallback(path: str) -> FileResponse:
                if path == "api" or path.startswith("api/"):
                    raise HTTPException(status_code=404, detail="Not Found")
                return FileResponse(index_path, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
