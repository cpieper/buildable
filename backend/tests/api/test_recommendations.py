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


def _manual_set(
    client: TestClient,
    set_num: str,
    *,
    name: str,
    year: int | None = None,
    theme_name: str | None = None,
    part_num: str = "3001",
    color_id: int = 5,
    quantity: int = 1,
) -> None:
    response = client.post(
        "/api/catalog/manual-sets",
        json={
            "set_num": set_num,
            "name": name,
            "year": year,
            "theme_name": theme_name,
            "parts": [
                {
                    "part_num": part_num,
                    "part_name": f"Part {part_num}",
                    "color_id": color_id,
                    "color_name": "Red" if color_id == 5 else "Blue",
                    "rgb_hex": "C91A09" if color_id == 5 else "0055BF",
                    "quantity": quantity,
                }
            ],
        },
    )
    assert response.status_code == 201


def test_recommendations_default_to_not_owned_and_within_piece_threshold(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _authenticate(client, session_factory)
    _manual_set(client, "0001-1", name="Owned", quantity=3)
    _manual_set(client, "1000-1", name="Exact", quantity=2)
    _manual_set(client, "1001-1", name="Missing", quantity=3, part_num="3002")
    _manual_set(client, "1002-1", name="Too big", quantity=4)
    assert client.post("/api/collection", json={"set_num": "0001-1"}).status_code == 201

    response = client.get("/api/recommendations")

    assert response.status_code == 200
    body = response.json()
    assert [item["set_num"] for item in body["items"]] == ["1000-1", "1001-1"]
    assert body["total_candidates"] == 2
    assert body["max_pieces"] == 3
    assert body["hide_owned"] is True


def test_recommendations_filter_sort_and_pagination_are_stable(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _authenticate(client, session_factory)
    _manual_set(client, "0001-1", name="Owned", quantity=5)
    _manual_set(client, "1000-1", name="First", year=2020, theme_name="Space", quantity=1)
    _manual_set(client, "1001-1", name="Second", year=2022, theme_name="Space", quantity=2)
    _manual_set(client, "1002-1", name="Other", year=2024, theme_name="Castle", quantity=3)
    assert client.post("/api/collection", json={"set_num": "0001-1"}).status_code == 201

    filtered = client.get(
        "/api/recommendations",
        params={"theme": "space", "year_from": 2021, "sort": "year", "direction": "desc"},
    )
    assert [item["set_num"] for item in filtered.json()["items"]] == ["1001-1"]
    first_page = client.get(
        "/api/recommendations", params={"max_pieces": 0, "sort": "pieces", "limit": 1}
    )
    second_page = client.get(
        "/api/recommendations",
        params={"max_pieces": 0, "sort": "pieces", "limit": 1, "offset": 1},
    )
    assert first_page.json()["items"][0]["set_num"] == "1000-1"
    assert second_page.json()["items"][0]["set_num"] == "1001-1"


def _seed_discriminating_recommendations(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _authenticate(client, session_factory)
    _manual_set(client, "0001-1", name="Owned", quantity=10)
    _manual_set(
        client,
        "1000-1",
        name="Exact First",
        year=2020,
        theme_name="Space",
        quantity=1,
    )
    _manual_set(
        client,
        "1001-1",
        name="Exact Second",
        year=2022,
        theme_name="Space",
        quantity=1,
    )
    _manual_set(
        client,
        "1002-1",
        name="Color Swap",
        year=2021,
        theme_name="Space",
        color_id=1,
        quantity=2,
    )
    _manual_set(
        client,
        "1003-1",
        name="Missing First",
        year=2023,
        theme_name="Space",
        part_num="3002",
        quantity=1,
    )
    _manual_set(
        client,
        "1004-1",
        name="Missing Largest",
        year=2024,
        theme_name="Castle",
        part_num="3003",
        quantity=3,
    )
    _manual_set(
        client,
        "1005-1",
        name="Missing Second",
        year=2024,
        theme_name="Space",
        part_num="3004",
        quantity=1,
    )
    _manual_set(
        client,
        "1006-1",
        name="Above Threshold",
        year=2025,
        theme_name="Space",
        part_num="3005",
        quantity=11,
    )
    assert client.post("/api/collection", json={"set_num": "0001-1"}).status_code == 201


def _set_numbers(client: TestClient, **params: object) -> list[str]:
    response = client.get("/api/recommendations", params=params)
    assert response.status_code == 200
    return [item["set_num"] for item in response.json()["items"]]


def test_recommendations_apply_every_sort_and_direction_with_stable_ties(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_discriminating_recommendations(client, session_factory)

    assert _set_numbers(client, sort="buildability", direction="asc") == [
        "1000-1",
        "1001-1",
        "1002-1",
        "1003-1",
        "1005-1",
        "1004-1",
    ]
    assert _set_numbers(client, sort="buildability", direction="desc") == [
        "1003-1",
        "1004-1",
        "1005-1",
        "1002-1",
        "1000-1",
        "1001-1",
    ]
    assert _set_numbers(client, sort="pieces", direction="asc") == [
        "1000-1",
        "1001-1",
        "1003-1",
        "1005-1",
        "1002-1",
        "1004-1",
    ]
    assert _set_numbers(client, sort="pieces", direction="desc") == [
        "1004-1",
        "1002-1",
        "1000-1",
        "1001-1",
        "1003-1",
        "1005-1",
    ]
    assert _set_numbers(client, sort="year", direction="asc") == [
        "1000-1",
        "1002-1",
        "1001-1",
        "1003-1",
        "1004-1",
        "1005-1",
    ]
    assert _set_numbers(client, sort="year", direction="desc") == [
        "1004-1",
        "1005-1",
        "1003-1",
        "1001-1",
        "1002-1",
        "1000-1",
    ]
    assert _set_numbers(client, sort="mismatches", direction="asc") == [
        "1000-1",
        "1001-1",
        "1003-1",
        "1004-1",
        "1005-1",
        "1002-1",
    ]
    assert _set_numbers(client, sort="mismatches", direction="desc") == [
        "1002-1",
        "1000-1",
        "1001-1",
        "1003-1",
        "1004-1",
        "1005-1",
    ]
    assert _set_numbers(client, sort="missing", direction="asc") == [
        "1000-1",
        "1001-1",
        "1002-1",
        "1003-1",
        "1005-1",
        "1004-1",
    ]
    assert _set_numbers(client, sort="missing", direction="desc") == [
        "1004-1",
        "1003-1",
        "1005-1",
        "1000-1",
        "1001-1",
        "1002-1",
    ]


def test_recommendation_filters_threshold_visibility_and_pagination_contract(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_discriminating_recommendations(client, session_factory)

    default = client.get("/api/recommendations")
    assert default.status_code == 200
    body = default.json()
    assert {key: body[key] for key in body if key != "items"} == {
        "total_candidates": 6,
        "offset": 0,
        "limit": 50,
        "max_pieces": 10,
        "theme": None,
        "year_from": None,
        "year_to": None,
        "hide_owned": True,
        "status": None,
        "sort": "buildability",
        "direction": "asc",
    }
    assert [item["set_num"] for item in body["items"]] == [
        "1000-1",
        "1001-1",
        "1002-1",
        "1003-1",
        "1005-1",
        "1004-1",
    ]
    assert _set_numbers(
        client,
        status="exact,missing",
        theme="Space",
        year_from=2021,
        year_to=2024,
    ) == ["1001-1", "1003-1", "1005-1"]
    assert _set_numbers(client, status="substitution") == ["1002-1"]
    assert "0001-1" not in _set_numbers(client)
    assert "0001-1" in _set_numbers(client, hide_owned=False)
    assert "1006-1" not in _set_numbers(client)
    assert "1006-1" in _set_numbers(client, max_pieces=0)

    first_page = client.get("/api/recommendations", params={"limit": 2})
    second_page = client.get("/api/recommendations", params={"limit": 2, "offset": 2})
    assert [item["set_num"] for item in first_page.json()["items"]] == ["1000-1", "1001-1"]
    assert [item["set_num"] for item in second_page.json()["items"]] == ["1002-1", "1003-1"]
    assert first_page.json()["total_candidates"] == second_page.json()["total_candidates"] == 6
    assert client.get("/api/recommendations", params={"limit": 101}).status_code == 422


def test_recommendations_empty_inventory_is_empty(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    _authenticate(client, session_factory)
    _manual_set(client, "1000-1", name="Candidate")

    response = client.get("/api/recommendations")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total_candidates"] == 0
