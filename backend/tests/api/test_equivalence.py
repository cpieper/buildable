import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy.orm import Session, sessionmaker

from app.models import AppSetting
from app.services.recommendations import load_equivalence_map


@pytest.fixture
def authenticated(client: TestClient, session_factory: sessionmaker[Session]) -> TestClient:
    with session_factory.begin() as session:
        session.add_all([AppSetting(key="auth.password_hash", value=PasswordHash.recommended().hash("build-stuff"), secret=True), AppSetting(key="auth.revision", value="1", secret=True)])
    assert client.post("/api/auth/login", json={"password": "build-stuff"}).status_code == 204
    return client


def _catalog(client: TestClient, set_num: str, part_num: str, color_id: int) -> None:
    assert client.post("/api/catalog/manual-sets", json={"set_num": set_num, "name": set_num, "parts": [{"part_num": part_num, "part_name": part_num, "color_id": color_id, "color_name": "Color", "rgb_hex": "FFFFFF", "quantity": 1}]}).status_code == 201


@pytest.mark.parametrize("method,path", [
    ("get", "/api/equivalence-groups"),
    ("post", "/api/equivalence-groups"),
    ("put", "/api/equivalence-groups/1"),
    ("delete", "/api/equivalence-groups/1"),
])
def test_equivalence_routes_require_authentication(method: str, path: str, client: TestClient) -> None:
    assert client.request(method, path, json={}).status_code == 401


def test_equivalence_group_turns_missing_result_into_substitution(authenticated: TestClient) -> None:
    _catalog(authenticated, "1234-1", "15573", 5)
    _catalog(authenticated, "5678-1", "3794b", 5)
    assert authenticated.post("/api/collection", json={"set_num": "1234-1"}).status_code == 201
    assert authenticated.get("/api/matches/5678-1").json()["status"] == "missing"

    response = authenticated.post("/api/equivalence-groups", json={"name": "1x2 jumper variants", "part_nums": ["15573", "3794b"], "notes": None})

    assert response.status_code == 201
    assert response.json()["part_nums"] == ["15573", "3794b"]
    assert authenticated.get("/api/matches/5678-1").json()["status"] == "substitution"


def test_equivalence_group_crud_validation_conflicts_and_symmetric_map(
    authenticated: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _catalog(authenticated, "1234-1", "3001", 5)
    _catalog(authenticated, "5678-1", "3002", 5)
    _catalog(authenticated, "9999-1", "3003", 5)
    invalid = authenticated.post("/api/equivalence-groups", json={"name": "Invalid", "part_nums": ["3001", "3001"]})
    unknown = authenticated.post("/api/equivalence-groups", json={"name": "Unknown", "part_nums": ["3001", "missing"]})
    assert invalid.status_code == 422
    assert unknown.status_code == 422

    created = authenticated.post("/api/equivalence-groups", json={"name": "Group", "part_nums": ["3001", "3002"]})
    assert created.status_code == 201
    group_id = created.json()["id"]
    duplicate = authenticated.post("/api/equivalence-groups", json={"name": "Other", "part_nums": ["3002", "3003"]})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "part_already_grouped"

    changed = authenticated.put(f"/api/equivalence-groups/{group_id}", json={"name": "Group 2", "part_nums": ["3001", "3003"], "notes": "edited"})
    assert changed.status_code == 200
    with session_factory() as session:
        assert load_equivalence_map(session) == {"3001": frozenset({"3003"}), "3003": frozenset({"3001"})}
    assert authenticated.delete(f"/api/equivalence-groups/{group_id}").status_code == 204
    assert authenticated.get("/api/equivalence-groups").json() == []
