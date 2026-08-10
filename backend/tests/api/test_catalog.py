from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import AppSetting, CatalogSet, SyncRun


@pytest.fixture
def authenticated_client(
    client: TestClient, session_factory: sessionmaker[Session]
) -> TestClient:
    with session_factory.begin() as session:
        session.add_all(
            [
                AppSetting(
                    key="auth.password_hash",
                    value=PasswordHash.recommended().hash("build-stuff"),
                    secret=True,
                ),
                AppSetting(key="auth.revision", value="1", secret=True),
            ]
        )
    response = client.post("/api/auth/login", json={"password": "build-stuff"})
    assert response.status_code == 204
    return client


@pytest.fixture
def catalog_fixture_dir() -> Path:
    return Path(__file__).parents[1] / "fixtures" / "rebrickable-small"


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", "/api/catalog/sets", {}),
        ("get", "/api/catalog/sets/1234-1", {}),
        (
            "post",
            "/api/catalog/manual-sets",
            {
                "json": {
                    "set_num": "custom-1",
                    "name": "Custom",
                    "parts": [],
                }
            },
        ),
        (
            "post",
            "/api/catalog/import",
            {"files": {"file": ("catalog.zip", b"not-a-zip", "application/zip")}},
        ),
    ],
)
def test_catalog_routes_require_authentication(
    method: str, path: str, kwargs: dict[str, object], client: TestClient
) -> None:
    response = client.request(method, path, **kwargs)

    assert response.status_code == 401


def test_zip_import_response_includes_counts_timestamps_and_sync_id(
    authenticated_client: TestClient,
    catalog_fixture_dir: Path,
    session_factory: sessionmaker[Session],
) -> None:
    with (catalog_fixture_dir / "valid-catalog.zip").open("rb") as archive:
        response = authenticated_client.post(
            "/api/catalog/import",
            files={"file": ("catalog.zip", archive, "application/zip")},
        )

    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in ("sets", "parts", "colors", "warnings")} == {
        "sets": 1,
        "parts": 3,
        "colors": 3,
        "warnings": [],
    }
    assert datetime.fromisoformat(body["started_at"]).tzinfo is not None
    assert datetime.fromisoformat(body["completed_at"]).tzinfo is not None
    assert body["sync_run_id"] > 0
    with session_factory() as session:
        run = session.get_one(SyncRun, body["sync_run_id"])
        assert run.status == "completed"


def test_malformed_upload_returns_422_and_preserves_prior_cache(
    authenticated_client: TestClient,
    catalog_fixture_dir: Path,
    session_factory: sessionmaker[Session],
) -> None:
    with (catalog_fixture_dir / "valid-catalog.zip").open("rb") as archive:
        first = authenticated_client.post(
            "/api/catalog/import",
            files={"file": ("catalog.zip", archive, "application/zip")},
        )
    assert first.status_code == 200

    with (catalog_fixture_dir / "bad-quantity.zip").open("rb") as archive:
        response = authenticated_client.post(
            "/api/catalog/import",
            files={"file": ("bad.zip", archive, "application/zip")},
        )

    assert response.status_code == 422
    assert "inventory_parts.csv:2" in response.json()["detail"]
    with session_factory() as session:
        assert session.get_one(CatalogSet, "1234-1").name == "Castle Cart"
        statuses = session.scalars(select(SyncRun.status).order_by(SyncRun.id)).all()
        assert statuses == ["completed", "failed"]


def test_unreadable_zip_member_returns_422_and_records_failed_sync(
    authenticated_client: TestClient,
    catalog_fixture_dir: Path,
    session_factory: sessionmaker[Session],
) -> None:
    with (catalog_fixture_dir / "encrypted-catalog.zip").open("rb") as archive:
        response = authenticated_client.post(
            "/api/catalog/import",
            files={"file": ("encrypted.zip", archive, "application/zip")},
        )

    assert response.status_code == 422
    assert "sets.csv" in response.json()["detail"]
    with session_factory() as session:
        failed_run = session.scalar(select(SyncRun))
        assert failed_run is not None
        assert failed_run.status == "failed"
        assert "sets.csv" in (failed_run.error or "")


def test_manual_entry_is_searchable_by_name_and_set_number(
    authenticated_client: TestClient,
) -> None:
    payload = {
        "set_num": "MOC-42",
        "name": "Moon Rover",
        "year": 2026,
        "theme_name": "Space",
        "image_url": "https://example.test/moon-rover.png",
        "external_url": "https://example.test/moon-rover",
        "instructions_url": "https://example.test/moon-rover.pdf",
        "parts": [
            {
                "part_num": "3001",
                "part_name": "Brick 2 x 4",
                "color_id": 5,
                "color_name": "Red",
                "rgb_hex": "C91A09",
                "quantity": 4,
                "is_spare": False,
            }
        ],
    }

    created = authenticated_client.post("/api/catalog/manual-sets", json=payload)

    assert created.status_code == 201
    assert created.json()["set_num"] == "MOC-42"
    assert created.json()["parts"][0]["quantity"] == 4
    assert [
        item["set_num"]
        for item in authenticated_client.get(
            "/api/catalog/sets", params={"q": "moon", "limit": 20}
        ).json()
    ] == ["MOC-42"]
    assert [
        item["name"]
        for item in authenticated_client.get(
            "/api/catalog/sets", params={"q": "mOc-42", "limit": 20}
        ).json()
    ] == ["Moon Rover"]
    assert authenticated_client.get(
        "/api/catalog/sets", params={"q": "space", "limit": 20}
    ).json() == []


def test_set_detail_returns_effective_parts_and_missing_set_is_404(
    authenticated_client: TestClient,
) -> None:
    payload = {
        "set_num": "MOC-42",
        "name": "Moon Rover",
        "parts": [
            {
                "part_num": "3001",
                "part_name": "Brick 2 x 4",
                "color_id": 5,
                "color_name": "Red",
                "rgb_hex": "C91A09",
                "quantity": 4,
            }
        ],
    }
    assert (
        authenticated_client.post("/api/catalog/manual-sets", json=payload).status_code
        == 201
    )

    response = authenticated_client.get("/api/catalog/sets/MOC-42")

    assert response.status_code == 200
    assert response.json() == {
        "set_num": "MOC-42",
        "name": "Moon Rover",
        "year": None,
        "theme_name": None,
        "num_parts": 4,
        "image_url": None,
        "has_local_overrides": False,
        "external_url": None,
        "instructions_url": None,
        "parts": [
            {
                "part_num": "3001",
                "part_name": "Brick 2 x 4",
                "color_id": 5,
                "color_name": "Red",
                "rgb_hex": "C91A09",
                "quantity": 4,
                "is_spare": False,
                "source_kind": "manual",
                "image_url": None,
            }
        ],
    }
    assert authenticated_client.get("/api/catalog/sets/missing-1").status_code == 404
