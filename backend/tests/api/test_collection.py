import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy.orm import Session, sessionmaker

from app.models import AppSetting


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
    assert (
        client.post("/api/auth/login", json={"password": "build-stuff"}).status_code
        == 204
    )
    return client


def _catalog(client: TestClient) -> None:
    response = client.post(
        "/api/catalog/manual-sets",
        json={
            "set_num": "1234-1",
            "name": "Castle Cart",
            "parts": [
                {
                    "part_num": "3001",
                    "part_name": "Brick",
                    "color_id": 5,
                    "color_name": "Red",
                    "rgb_hex": "C91A09",
                    "quantity": 2,
                },
                {
                    "part_num": "6141",
                    "part_name": "Plate",
                    "color_id": 1,
                    "color_name": "Blue",
                    "rgb_hex": "0055BF",
                    "quantity": 1,
                    "is_spare": True,
                },
            ],
        },
    )
    assert response.status_code == 201


def test_collection_and_inventory_routes_require_authentication(
    client: TestClient,
) -> None:
    assert client.get("/api/collection").status_code == 401
    assert client.get("/api/inventory").status_code == 401


def test_collection_crud_duplicate_increment_missing_limits_and_cascade(
    authenticated_client: TestClient,
) -> None:
    _catalog(authenticated_client)
    created = authenticated_client.post(
        "/api/collection",
        json={
            "set_num": "1234-1",
            "quantity": 1,
            "completeness": "incomplete",
            "notes": "shelf",
        },
    )
    assert created.status_code == 201
    owned_id = created.json()["id"]
    incremented = authenticated_client.post(
        "/api/collection", json={"set_num": "1234-1", "quantity": 2}
    )
    assert incremented.status_code == 201
    assert incremented.json()["quantity"] == 3
    missing = authenticated_client.post(
        f"/api/collection/{owned_id}/missing-parts",
        json={"part_num": "3001", "color_id": 5, "quantity": 5},
    )
    assert missing.status_code == 201
    missing_id = missing.json()["id"]
    edited = authenticated_client.patch(
        f"/api/collection/{owned_id}/missing-parts/{missing_id}",
        json={"quantity": 6, "note": "verified"},
    )
    assert edited.status_code == 200
    assert edited.json()["note"] == "verified"
    assert (
        authenticated_client.post(
            f"/api/collection/{owned_id}/missing-parts",
            json={"part_num": "3001", "color_id": 5, "quantity": 2},
        ).status_code
        == 422
    )
    assert (
        authenticated_client.patch(
            f"/api/collection/{owned_id}", json={"quantity": 2}
        ).status_code
        == 422
    )
    assert (
        authenticated_client.delete(
            f"/api/collection/{owned_id}/missing-parts/{missing_id}"
        ).status_code
        == 204
    )
    assert (
        authenticated_client.post(
            f"/api/collection/{owned_id}/missing-parts",
            json={"part_num": "3001", "color_id": 5, "quantity": 1},
        ).status_code
        == 201
    )
    assert authenticated_client.delete(f"/api/collection/{owned_id}").status_code == 204
    assert (
        authenticated_client.get(
            f"/api/collection/{owned_id}/missing-parts"
        ).status_code
        == 404
    )


def test_inventory_search_color_pagination_and_warnings(
    authenticated_client: TestClient,
) -> None:
    _catalog(authenticated_client)
    owned = authenticated_client.post(
        "/api/collection",
        json={
            "set_num": "1234-1",
            "unknown_missing_count": 1,
            "unknown_missing_note": "lost",
        },
    ).json()
    response = authenticated_client.get(
        "/api/inventory", params={"q": "brick", "color_id": 5, "limit": 1}
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] == 2
    assert response.json()["warnings"] == [
        {
            "owned_set_id": owned["id"],
            "set_num": "1234-1",
            "set_name": "Castle Cart",
            "unknown_missing_count": 1,
            "note": "lost",
        }
    ]
    assert (
        authenticated_client.get(
            "/api/inventory", params={"offset": 1, "limit": 1}
        ).json()["items"][0]["part_num"]
        == "6141"
    )


def test_quantity_reduction_allows_exact_missing_boundary_and_rejects_below_it(
    authenticated_client: TestClient,
) -> None:
    _catalog(authenticated_client)
    owned = authenticated_client.post(
        "/api/collection", json={"set_num": "1234-1", "quantity": 4}
    ).json()
    owned_id = owned["id"]
    assert (
        authenticated_client.post(
            f"/api/collection/{owned_id}/missing-parts",
            json={"part_num": "3001", "color_id": 5, "quantity": 6},
        ).status_code
        == 201
    )

    at_boundary = authenticated_client.patch(
        f"/api/collection/{owned_id}", json={"quantity": 3}
    )

    assert at_boundary.status_code == 200
    assert at_boundary.json()["quantity"] == 3
    below_boundary = authenticated_client.patch(
        f"/api/collection/{owned_id}", json={"quantity": 2}
    )
    assert below_boundary.status_code == 422
    assert authenticated_client.get("/api/collection").json()[0]["quantity"] == 3
