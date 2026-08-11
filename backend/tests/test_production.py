from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import AppSetting
from app.services.auth import PASSWORD_HASH_KEY, PasswordStore


def test_static_spa_fallback_keeps_api_404s_as_json(
    tmp_path: Path, session_factory
) -> None:
    static_dir = tmp_path / "static"
    app_dir = static_dir / "_app"
    app_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<main>Buildable</main>")
    (app_dir / "app.js").write_text("console.log('app')")
    app = create_app(
        settings=Settings(
            database_url="sqlite://",
            data_dir=tmp_path / "data",
            frontend_dir=static_dir,
        ),
        session_factory=session_factory,
    )

    with TestClient(app) as client:
        asset = client.get("/_app/app.js")
        page = client.get("/buildable")
        api = client.get("/api/not-a-route")

    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert page.status_code == 200
    assert page.text == "<main>Buildable</main>"
    assert page.headers["cache-control"] == "no-cache"
    assert api.status_code == 404
    assert api.headers["content-type"].startswith("application/json")


def test_startup_bootstraps_initial_password_once(tmp_path: Path, session_factory) -> None:
    app = create_app(
        settings=Settings(
            database_url="sqlite://",
            data_dir=tmp_path / "data",
            initial_password="build-stuff",
        ),
        session_factory=session_factory,
    )

    with TestClient(app):
        pass

    with session_factory() as session:
        assert PasswordStore(session).verify("build-stuff")
        assert session.scalar(select(AppSetting).where(AppSetting.key == PASSWORD_HASH_KEY))
