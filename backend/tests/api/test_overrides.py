import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy.orm import Session, sessionmaker

from app.models import AppSetting, CatalogSetPart


@pytest.fixture
def authenticated(client: TestClient, session_factory: sessionmaker[Session]) -> TestClient:
    with session_factory.begin() as session:
        session.add_all(
            [
                AppSetting(key="auth.password_hash", value=PasswordHash.recommended().hash("build-stuff"), secret=True),
                AppSetting(key="auth.revision", value="1", secret=True),
            ]
        )
    assert client.post("/api/auth/login", json={"password": "build-stuff"}).status_code == 204
    return client


def _catalog(client: TestClient) -> None:
    response = client.post(
        "/api/catalog/manual-sets",
        json={
            "set_num": "1234-1",
            "name": "Original",
            "year": 1990,
            "parts": [
                {
                    "part_num": "3001",
                    "part_name": "Brick",
                    "color_id": 5,
                    "color_name": "Red",
                    "rgb_hex": "C91A09",
                    "quantity": 2,
                }
            ],
        },
    )
    assert response.status_code == 201


@pytest.mark.parametrize("method,path", [
    ("get", "/api/overrides/sets/1234-1"),
    ("put", "/api/overrides/sets/1234-1"),
    ("delete", "/api/overrides/sets/1234-1"),
    ("put", "/api/overrides/sets/1234-1/parts/3001/5"),
    ("delete", "/api/overrides/sets/1234-1/parts/3001/5"),
])
def test_override_routes_require_authentication(
    method: str, path: str, client: TestClient
) -> None:
    assert client.request(method, path, json={}).status_code == 401


def test_inventory_override_changes_effective_set_without_mutating_import(
    authenticated: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _catalog(authenticated)
    with session_factory() as session:
        imported_row_id = session.query(CatalogSetPart.id).scalar()

    response = authenticated.put(
        "/api/overrides/sets/1234-1/parts/3001/5",
        json={"operation": "upsert", "quantity": 4, "is_spare": False, "reason": "Counted from instructions"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["imported"]["quantity"] == 2
    assert body["override"]["quantity"] == 4
    assert body["effective"]["quantity"] == 4
    assert body["has_local_overrides"] is True
    with session_factory() as session:
        assert session.get(CatalogSetPart, imported_row_id).quantity == 2


def test_metadata_override_delete_and_validation(
    authenticated: TestClient,
) -> None:
    _catalog(authenticated)
    invalid = authenticated.put("/api/overrides/sets/1234-1", json={"name": "Corrected", "reason": " "})
    assert invalid.status_code == 422

    response = authenticated.put(
        "/api/overrides/sets/1234-1", json={"name": "Corrected", "reason": "Catalog correction"}
    )
    assert response.status_code == 200
    assert response.json()["imported"]["name"] == "Original"
    assert response.json()["override"]["name"] == "Corrected"
    assert response.json()["effective"]["name"] == "Corrected"
    assert authenticated.get("/api/overrides/sets/1234-1").status_code == 200
    assert authenticated.request("DELETE", "/api/overrides/sets/1234-1", json={"reason": "Undo correction"}).status_code == 204
    assert authenticated.get("/api/overrides/sets/1234-1").status_code == 404


def test_part_override_enforces_identity_and_operation_contract(authenticated: TestClient) -> None:
    _catalog(authenticated)
    bad_upsert = authenticated.put(
        "/api/overrides/sets/1234-1/parts/3001/5",
        json={"operation": "upsert", "quantity": 0, "is_spare": False, "reason": "Bad"},
    )
    bad_delete = authenticated.put(
        "/api/overrides/sets/1234-1/parts/3001/5",
        json={"operation": "delete", "quantity": 1, "is_spare": True, "reason": "Bad"},
    )
    assert bad_upsert.status_code == 422
    assert bad_delete.status_code == 422

    deleted = authenticated.put(
        "/api/overrides/sets/1234-1/parts/3001/5",
        json={"operation": "delete", "quantity": None, "is_spare": False, "reason": "Not required"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["effective"] is None
    assert authenticated.request("DELETE", "/api/overrides/sets/1234-1/parts/3001/5", json={"is_spare": False, "reason": "Undo correction"}).status_code == 204
