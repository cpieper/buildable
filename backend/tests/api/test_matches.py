from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy.orm import Session, sessionmaker

from app.models import AppSetting


def _authenticate(client: TestClient, session_factory: sessionmaker[Session]) -> None:
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
    assert client.post("/api/auth/login", json={"password": "build-stuff"}).status_code == 204


def _manual_set(client: TestClient, set_num: str, name: str, parts: list[dict]) -> None:
    response = client.post(
        "/api/catalog/manual-sets",
        json={"set_num": set_num, "name": name, "parts": parts},
    )
    assert response.status_code == 201


def test_target_match_serializes_color_substitution_story(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _authenticate(client, session_factory)
    _manual_set(
        client,
        "1234-1",
        "Owned",
        [
            {
                "part_num": "3001",
                "part_name": "Brick",
                "color_id": 1,
                "color_name": "Blue",
                "rgb_hex": "0055BF",
                "quantity": 2,
            }
        ],
    )
    _manual_set(
        client,
        "5678-1",
        "Target",
        [
            {
                "part_num": "3001",
                "part_name": "Brick",
                "color_id": 5,
                "color_name": "Red",
                "rgb_hex": "C91A09",
                "quantity": 2,
            }
        ],
    )
    assert client.post("/api/collection", json={"set_num": "1234-1"}).status_code == 201

    response = client.get("/api/matches/5678-1")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "substitution"
    assert body["counts"]["color_substitution"] == 2
    assert body["substitutions"] == [
        {
            "required_part": {"part_num": "3001", "name": "Brick", "image_url": None},
            "required_color": {"id": 5, "name": "Red", "rgb_hex": "C91A09"},
            "supplied_part": {"part_num": "3001", "name": "Brick", "image_url": None},
            "supplied_color": {"id": 1, "name": "Blue", "rgb_hex": "0055BF"},
            "quantity": 2,
            "kind": "color",
        }
    ]


def test_target_match_returns_not_found_for_unknown_set(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _authenticate(client, session_factory)

    assert client.get("/api/matches/missing-1").status_code == 404
