from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import AppSetting, CatalogSet, OwnedSet, SyncRun
from app.schemas.catalog import RemoteSetSummary
from app.services.rebrickable import CatalogLookupError, ImportedPart, ImportedSet


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
        ("get", "/api/catalog/remote-search", {}),
        ("post", "/api/catalog/lookup/1234-1", {}),
        (
            "post",
            "/api/catalog/manual-sets",
            {
                "json": {
                    "set_num": "9000-1",
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
        (
            "post",
            "/api/catalog/discovery-import",
            {"files": {"file": ("sets.csv", b"Set Number\n10497-1\n", "text/csv")}},
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
        "set_num": "9000-1",
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
    assert created.json()["set_num"] == "9000-1"
    assert created.json()["parts"][0]["quantity"] == 4
    assert [
        item["set_num"]
        for item in authenticated_client.get(
            "/api/catalog/sets", params={"q": "moon", "limit": 20}
        ).json()
    ] == ["9000-1"]
    assert [
        item["name"]
        for item in authenticated_client.get(
            "/api/catalog/sets", params={"q": "9000-1", "limit": 20}
        ).json()
    ] == ["Moon Rover"]
    assert authenticated_client.get(
        "/api/catalog/sets", params={"q": "space", "limit": 20}
    ).json() == []


def test_set_detail_returns_effective_parts_and_missing_set_is_404(
    authenticated_client: TestClient,
) -> None:
    payload = {
        "set_num": "9000-1",
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

    response = authenticated_client.get("/api/catalog/sets/9000-1")

    assert response.status_code == 200
    assert response.json() == {
        "set_num": "9000-1",
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


def test_remote_search_returns_remote_summaries_without_mutating_cache(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    """Routing remote search through the importer would create unwanted cache rows."""
    class FakeRebrickableClient:
        def __init__(self, api_key: str | None) -> None:
            assert api_key == "secret"

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def search_sets(self, query: str, limit: int) -> list[RemoteSetSummary]:
            assert (query, limit) == ("Galaxy Explorer", 20)
            return [
                RemoteSetSummary(
                    set_num="10497-1",
                    name="Galaxy Explorer",
                    year=2022,
                    theme_id=158,
                    num_parts=1254,
                    image_url="https://example.test/galaxy.png",
                    external_url="https://example.test/sets/10497-1",
                )
            ]

    authenticated_client.app.state.settings.rebrickable_api_key = "secret"
    monkeypatch.setattr("app.api.catalog.RebrickableClient", FakeRebrickableClient)

    response = authenticated_client.get(
        "/api/catalog/remote-search", params={"q": "Galaxy Explorer", "limit": 20}
    )

    assert response.status_code == 200
    assert response.json()[0]["set_num"] == "10497-1"
    with session_factory() as session:
        assert session.get(CatalogSet, "10497-1") is None


def test_lookup_imports_selected_set_and_returns_sync_summary(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting the targeted importer would return a set that the cache cannot use."""
    class FakeRebrickableClient:
        def __init__(self, api_key: str | None) -> None:
            assert api_key == "secret"

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def lookup_set(self, set_num: str) -> ImportedSet:
            assert set_num == "10497-1"
            return ImportedSet(
                set_num="10497-1",
                name="Galaxy Explorer",
                year=2022,
                theme_id=158,
                num_parts=2,
                image_url="https://example.test/galaxy.png",
                external_url="https://example.test/sets/10497-1",
                parts=[
                    ImportedPart(
                        part_num="3001",
                        part_name="Brick 2 x 4",
                        part_image_url=None,
                        color_id=4,
                        color_name="Red",
                        rgb_hex="C91A09",
                        quantity=2,
                        is_spare=False,
                        source_id="1",
                    )
                ],
            )

    authenticated_client.app.state.settings.rebrickable_api_key = "secret"
    monkeypatch.setattr("app.api.catalog.RebrickableClient", FakeRebrickableClient)

    response = authenticated_client.post("/api/catalog/lookup/10497-1")

    assert response.status_code == 200
    assert response.json()["set"]["parts"][0]["quantity"] == 2
    assert response.json()["summary"]["sync_run_id"] > 0


def test_discovery_import_fetches_catalog_sets_without_adding_collection_rows(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    looked_up: list[str] = []

    class FakeRebrickableClient:
        def __init__(self, api_key: str | None) -> None:
            assert api_key == "secret"

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def lookup_set(self, set_num: str) -> ImportedSet:
            looked_up.append(set_num)
            return ImportedSet(
                set_num=set_num,
                name=f"Candidate {set_num}",
                year=2026,
                theme_id=158,
                num_parts=2,
                image_url=None,
                external_url=f"https://example.test/sets/{set_num}",
                parts=[
                    ImportedPart(
                        part_num="3001",
                        part_name="Brick 2 x 4",
                        part_image_url=None,
                        color_id=4,
                        color_name="Red",
                        rgb_hex="C91A09",
                        quantity=2,
                        is_spare=False,
                        source_id=set_num,
                    )
                ],
            )

    authenticated_client.app.state.settings.rebrickable_api_key = "secret"
    monkeypatch.setattr("app.api.catalog.RebrickableClient", FakeRebrickableClient)

    response = authenticated_client.post(
        "/api/catalog/discovery-import",
        files={
            "file": (
                "discovery.csv",
                b"Set Number,Quantity\n10497-1,1\n10497-1,1\n31109-1,1\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["sets_imported"] == 2
    assert response.json()["rows_skipped"] == 0
    assert looked_up == ["10497-1", "31109-1"]
    with session_factory() as session:
        assert session.get(CatalogSet, "10497-1") is not None
        assert session.get(CatalogSet, "31109-1") is not None
        assert session.scalars(select(OwnedSet)).all() == []


def test_discovery_import_reports_mocs_as_inventory_unsupported(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    looked_up: list[str] = []

    class FakeRebrickableClient:
        def __init__(self, api_key: str | None) -> None:
            assert api_key == "secret"

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def lookup_set(self, set_num: str) -> ImportedSet:
            looked_up.append(set_num)
            raise CatalogLookupError("not_found", "Set not found")

    authenticated_client.app.state.settings.rebrickable_api_key = "secret"
    monkeypatch.setattr("app.api.catalog.RebrickableClient", FakeRebrickableClient)

    response = authenticated_client.post(
        "/api/catalog/discovery-import",
        files={
            "file": (
                "discovery.csv",
                b"Set Number,Quantity\nMOC-268046,1\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["sets_imported"] == 0
    assert response.json()["rows_skipped"] == 1
    assert response.json()["skipped_set_nums"] == ["MOC-268046"]
    assert looked_up == ["MOC-268046"]
    assert response.json()["warnings"] == [
        (
            "MOC-268046 is a Rebrickable MOC. Rebrickable does not expose "
            "arbitrary MOC inventories through the API, so import an inventory CSV "
            "for this MOC to match against it."
        )
    ]


def test_lookup_missing_api_key_uses_normalized_error(
    authenticated_client: TestClient,
) -> None:
    """Returning a generic server error hides the configuration action the user needs."""
    response = authenticated_client.post("/api/catalog/lookup/10497-1")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "api_key_missing"


def test_lookup_failure_preserves_existing_cached_set(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    """Deleting cached inventory before a failed remote response would lose usable data."""
    with session_factory.begin() as session:
        session.add(
            CatalogSet(
                set_num="10497-1",
                name="Cached Galaxy Explorer",
                year=2022,
                theme_id=None,
                theme_name=None,
                num_parts=2,
                image_url=None,
                external_url=None,
                instructions_url=None,
                source="rebrickable_api",
            )
        )

    class FailingRebrickableClient:
        def __init__(self, api_key: str | None) -> None:
            assert api_key == "secret"

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def lookup_set(self, set_num: str) -> ImportedSet:
            raise CatalogLookupError("unavailable", "Rebrickable is unavailable")

    authenticated_client.app.state.settings.rebrickable_api_key = "secret"
    monkeypatch.setattr("app.api.catalog.RebrickableClient", FailingRebrickableClient)

    response = authenticated_client.post("/api/catalog/lookup/10497-1")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "rebrickable_unavailable"
    with session_factory() as session:
        assert session.get_one(CatalogSet, "10497-1").name == "Cached Galaxy Explorer"


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (CatalogLookupError("not_found", "Set not found"), 404, "set_not_found"),
        (
            CatalogLookupError("throttled", "Throttled", retry_after=2),
            429,
            "rebrickable_throttled",
        ),
        (
            CatalogLookupError("unavailable", "Unavailable"),
            503,
            "rebrickable_unavailable",
        ),
        (
            CatalogLookupError("invalid_response", "Malformed"),
            502,
            "invalid_upstream_response",
        ),
    ],
)
def test_lookup_maps_remote_errors_to_normalized_api_response(
    authenticated_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: CatalogLookupError,
    expected_status: int,
    expected_code: str,
) -> None:
    """Changing a lookup error status/code would break callers' recovery behavior."""
    class FailingRebrickableClient:
        def __init__(self, api_key: str | None) -> None:
            assert api_key == "secret"

        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def lookup_set(self, set_num: str) -> ImportedSet:
            raise error

    authenticated_client.app.state.settings.rebrickable_api_key = "secret"
    monkeypatch.setattr("app.api.catalog.RebrickableClient", FailingRebrickableClient)

    response = authenticated_client.post("/api/catalog/lookup/10497-1")

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    if error.retry_after is not None:
        assert response.headers["retry-after"] == "2"


@pytest.mark.parametrize("set_num", ["MOC-42", "arbitrary", "1234-0", "123A-1"])
def test_manual_entry_rejects_non_official_set_numbers(
    set_num: str, authenticated_client: TestClient
) -> None:
    response = authenticated_client.post(
        "/api/catalog/manual-sets",
        json={
            "set_num": set_num,
            "name": "Not official",
            "parts": [
                {
                    "part_num": "3001",
                    "part_name": "Brick 2 x 4",
                    "color_id": 5,
                    "color_name": "Red",
                    "rgb_hex": "C91A09",
                    "quantity": 1,
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "set_num"


@pytest.mark.parametrize("set_num", ["0-1", "0007-2"])
def test_manual_entry_accepts_legacy_zero_prefixed_design_ids(
    set_num: str, authenticated_client: TestClient
) -> None:
    response = authenticated_client.post(
        "/api/catalog/manual-sets",
        json={
            "set_num": set_num,
            "name": "Legacy official set",
            "parts": [
                {
                    "part_num": "3001",
                    "part_name": "Brick 2 x 4",
                    "color_id": 5,
                    "color_name": "Red",
                    "rgb_hex": "C91A09",
                    "quantity": 1,
                }
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["set_num"] == set_num
