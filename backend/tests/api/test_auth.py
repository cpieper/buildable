from collections.abc import Iterator
from pathlib import Path
from time import time

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import get_session
from app.main import create_app
from app.models import AppSetting


class PasswordStoreFixture:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def set_password(self, password: str, *, revision: int = 1) -> None:
        self.set_hash(PasswordHash.recommended().hash(password), revision=revision)

    def set_hash(self, password_hash: str, *, revision: int = 1) -> None:
        with self.session_factory.begin() as session:
            session.merge(
                AppSetting(
                    key="auth.password_hash", value=password_hash, secret=True
                )
            )
            session.merge(
                AppSetting(
                    key="auth.revision", value=str(revision), secret=True
                )
            )


@pytest.fixture
def password_store(
    session_factory: sessionmaker[Session],
) -> PasswordStoreFixture:
    return PasswordStoreFixture(session_factory)


def test_login_sets_required_session_cookie_and_authenticates(
    client: TestClient, password_store: PasswordStoreFixture
) -> None:
    password_store.set_password("build-stuff")

    response = client.post("/api/auth/login", json={"password": "build-stuff"})

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "what2build_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Max-Age=2592000" in cookie
    assert "Path=/" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie
    assert client.get("/api/auth/session").json() == {"authenticated": True}


def test_login_sets_secure_cookie_when_configured(
    tmp_path: Path,
    session_factory: sessionmaker[Session],
    password_store: PasswordStoreFixture,
) -> None:
    password_store.set_password("build-stuff")
    settings = Settings(
        data_dir=tmp_path / "unused-data",
        database_url=f"sqlite:///{tmp_path / 'unused.db'}",
        secure_cookies=True,
    )
    app = create_app(settings=settings, session_factory=session_factory)

    def override_get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as secure_client:
        response = secure_client.post(
            "/api/auth/login", json={"password": "build-stuff"}
        )

    assert response.status_code == 204
    assert "Secure" in response.headers["set-cookie"]


def test_login_normalizes_unconfigured_password_error(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"password": "anything"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid password"}


def test_login_normalizes_wrong_password_error(
    client: TestClient, password_store: PasswordStoreFixture
) -> None:
    password_store.set_password("correct-password")

    response = client.post("/api/auth/login", json={"password": "wrong-password"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid password"}


def test_login_normalizes_invalid_stored_hash_error(
    client: TestClient, password_store: PasswordStoreFixture
) -> None:
    password_store.set_hash("not-a-password-hash")

    response = client.post("/api/auth/login", json={"password": "anything"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid password"}


def test_session_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/auth/session")

    assert response.status_code == 401


def test_protected_route_uses_shared_auth_dependency(
    app: FastAPI,
    password_store: PasswordStoreFixture,
) -> None:
    from app.api.dependencies import require_auth

    @app.get("/api/protected-probe", dependencies=[Depends(require_auth)])
    def protected_probe() -> dict[str, bool]:
        return {"protected": True}

    password_store.set_password("build-stuff")

    with TestClient(app) as probe_client:
        assert probe_client.get("/api/protected-probe").status_code == 401
        probe_client.post("/api/auth/login", json={"password": "build-stuff"})
        assert probe_client.get("/api/protected-probe").json() == {
            "protected": True
        }


def test_logout_clears_cookie_and_invalidates_session(
    client: TestClient, password_store: PasswordStoreFixture
) -> None:
    password_store.set_password("build-stuff")
    client.post("/api/auth/login", json={"password": "build-stuff"})

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert "what2build_session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/auth/session").status_code == 401


def test_session_rejects_cookie_older_than_thirty_days(
    client: TestClient,
    password_store: PasswordStoreFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_store.set_password("build-stuff")
    current_time = int(time())
    with monkeypatch.context() as timestamp_patch:
        timestamp_patch.setattr(
            "itsdangerous.timed.time.time",
            lambda: current_time - (60 * 60 * 24 * 30) - 1,
        )
        expired_token = URLSafeTimedSerializer(
            "development-only-change-me"
        ).dumps({"authenticated": True, "revision": 1})
    client.cookies.set("what2build_session", expired_token)

    response = client.get("/api/auth/session")

    assert response.status_code == 401


def test_session_rejects_signed_cookie_with_stale_revision(
    client: TestClient,
    password_store: PasswordStoreFixture,
    session_factory: sessionmaker[Session],
) -> None:
    password_store.set_password("build-stuff")
    client.post("/api/auth/login", json={"password": "build-stuff"})

    with session_factory.begin() as session:
        revision = session.get_one(AppSetting, "auth.revision")
        revision.value = "2"

    assert client.get("/api/auth/session").status_code == 401


def test_password_change_invalidates_existing_session_and_authenticates_new_one(
    app: FastAPI,
    client: TestClient,
    password_store: PasswordStoreFixture,
) -> None:
    password_store.set_password("old-password")
    client.post("/api/auth/login", json={"password": "old-password"})
    old_cookie = client.cookies.get("what2build_session")

    response = client.post(
        "/api/auth/password",
        json={
            "current_password": "old-password",
            "new_password": "new-password",
        },
    )

    assert response.status_code == 204
    assert client.get("/api/auth/session").json() == {"authenticated": True}
    with TestClient(app) as stale_client:
        stale_client.cookies.set("what2build_session", old_cookie)
        assert stale_client.get("/api/auth/session").status_code == 401
        assert stale_client.post(
            "/api/auth/login", json={"password": "old-password"}
        ).status_code == 401
        assert stale_client.post(
            "/api/auth/login", json={"password": "new-password"}
        ).status_code == 204


def test_password_change_rejects_wrong_current_password(
    client: TestClient, password_store: PasswordStoreFixture
) -> None:
    password_store.set_password("old-password")
    client.post("/api/auth/login", json={"password": "old-password"})

    response = client.post(
        "/api/auth/password",
        json={
            "current_password": "wrong-password",
            "new_password": "new-password",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid password"}
    assert client.get("/api/auth/session").json() == {"authenticated": True}


def test_password_change_marks_auth_settings_secret(
    client: TestClient,
    password_store: PasswordStoreFixture,
    session_factory: sessionmaker[Session],
) -> None:
    password_store.set_password("old-password")
    client.post("/api/auth/login", json={"password": "old-password"})

    client.post(
        "/api/auth/password",
        json={
            "current_password": "old-password",
            "new_password": "new-password",
        },
    )

    with session_factory() as session:
        password_hash = session.get_one(AppSetting, "auth.password_hash")
        revision = session.get_one(AppSetting, "auth.revision")
        assert password_hash.secret is True
        assert revision.secret is True
        assert revision.value == "2"


def test_cli_reset_password_hashes_password_and_increments_revision(
    tmp_path: Path,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import cli

    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'unused.db'}",
    )
    answers = iter(["first-password", "first-password"])
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "SessionFactory", session_factory)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(answers))

    assert cli.main(["reset-password"]) == 0

    with session_factory() as session:
        password_setting = session.get_one(AppSetting, "auth.password_hash")
        revision_setting = session.get_one(AppSetting, "auth.revision")
        assert PasswordHash.recommended().verify(
            "first-password", password_setting.value
        )
        assert password_setting.secret is True
        assert revision_setting.value == "1"
        assert revision_setting.secret is True

    answers = iter(["second-password", "second-password"])

    assert cli.main(["reset-password"]) == 0

    with session_factory() as session:
        password_setting = session.get_one(AppSetting, "auth.password_hash")
        revision_setting = session.get_one(AppSetting, "auth.revision")
        assert PasswordHash.recommended().verify(
            "second-password", password_setting.value
        )
        assert revision_setting.value == "2"


def test_cli_reset_password_rejects_mismatched_confirmation(
    tmp_path: Path,
    session_factory: sessionmaker[Session],
    password_store: PasswordStoreFixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app import cli

    password_store.set_password("unchanged-password")
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'unused.db'}",
    )
    answers = iter(["new-password", "different-password"])
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "SessionFactory", session_factory)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(answers))

    assert cli.main(["reset-password"]) == 1

    assert "Passwords do not match" in capsys.readouterr().err
    with session_factory() as session:
        password_setting = session.get_one(AppSetting, "auth.password_hash")
        revision_setting = session.get_one(AppSetting, "auth.revision")
        assert PasswordHash.recommended().verify(
            "unchanged-password", password_setting.value
        )
        assert revision_setting.value == "1"
