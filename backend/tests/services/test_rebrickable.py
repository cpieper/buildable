from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session

from app.models import CatalogSet
from app.services.catalog_import import import_rebrickable_zip
from app.services.rebrickable import (
    CatalogLookupError,
    ImportedPart,
    ImportedSet,
    RebrickableClient,
    import_rebrickable_set,
)


class MockTransport:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._responses: list[tuple[int, object, dict[str, str]]] = []

    def respond(
        self, status_code: int, body: object, *, headers: dict[str, str] | None = None
    ) -> None:
        self._responses.append((status_code, body, headers or {}))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status_code, body, headers = self._responses.pop(0)
        return httpx.Response(status_code, json=body, headers=headers, request=request)


@pytest.fixture
def mock_transport() -> MockTransport:
    transport = MockTransport()
    transport.respond(
        200,
        {
            "set_num": "75379-1",
            "name": "R2-D2",
            "year": 2021,
            "theme_id": 158,
            "num_parts": 2314,
            "set_img_url": "https://example.test/r2.png",
            "set_url": "https://example.test/sets/75379-1",
        },
    )
    transport.respond(
        200,
        {
            "next": "https://rebrickable.com/api/v3/lego/sets/75379-1/parts/?page=2",
            "results": [_part(index) for index in range(100)],
        },
    )
    transport.respond(200, {"next": None, "results": [_part(100)]})
    return transport


def _part(index: int) -> dict[str, object]:
    return {
        "id": index + 1,
        "part": {
            "part_num": f"part-{index}",
            "name": f"Part {index}",
            "part_img_url": f"https://example.test/part-{index}.png",
        },
        "color": {"id": index + 1, "name": f"Color {index}", "rgb": "AABBCC"},
        "quantity": 1,
        "is_spare": False,
    }


def test_lookup_fetches_set_and_all_part_pages(mock_transport: MockTransport) -> None:
    """Removing next-page traversal would leave incomplete inventories."""
    client = RebrickableClient("secret", transport=httpx.MockTransport(mock_transport))

    imported = client.lookup_set("75379-1")

    assert imported.set_num == "75379-1"
    assert len(imported.parts) == 101
    assert mock_transport.requests[0].headers["authorization"] == "key secret"
    assert mock_transport.requests[1].url.params["inc_minifig_parts"] == "1"
    assert mock_transport.requests[1].url.params["page_size"] == "1000"
    assert mock_transport.requests[2].url.params["page"] == "2"


def test_throttle_error_preserves_retry_after() -> None:
    """Treating a throttle as generic availability loses the retry guidance."""
    transport = MockTransport()
    transport.respond(
        429,
        {"detail": "Expected available in 2 seconds."},
        headers={"Retry-After": "2"},
    )

    with pytest.raises(CatalogLookupError) as error:
        RebrickableClient("secret", transport=httpx.MockTransport(transport)).lookup_set(
            "75379-1"
        )

    assert error.value.code == "throttled"
    assert error.value.retry_after == 2


def test_remote_search_returns_summaries_without_importing(
    session: Session,
) -> None:
    """Accidentally using import code in search would mutate the local cache."""
    transport = MockTransport()
    transport.respond(
        200,
        {
            "next": None,
            "results": [
                {
                    "set_num": "10497-1",
                    "name": "Galaxy Explorer",
                    "year": 2022,
                    "theme_id": 158,
                    "num_parts": 1254,
                    "set_img_url": "https://example.test/galaxy.png",
                    "set_url": "https://example.test/sets/10497-1",
                }
            ],
        },
    )

    results = RebrickableClient("secret", transport=httpx.MockTransport(transport)).search_sets(
        "Galaxy Explorer", limit=20
    )

    assert results[0].set_num == "10497-1"
    assert transport.requests[0].url.params["search"] == "Galaxy Explorer"
    assert transport.requests[0].url.params["page_size"] == "20"
    assert session.get(CatalogSet, "10497-1") is None


def test_remote_search_follows_next_page_until_limit() -> None:
    """Stopping after the first page can hide an otherwise matching remote set."""
    transport = MockTransport()
    transport.respond(
        200,
        {
            "next": "https://rebrickable.com/api/v3/lego/sets/?page=2",
            "results": [
                {
                    "set_num": "10497-1",
                    "name": "Galaxy Explorer",
                    "year": 2022,
                    "theme_id": 158,
                    "num_parts": 1254,
                    "set_img_url": None,
                    "set_url": "https://example.test/sets/10497-1",
                }
            ],
        },
    )
    transport.respond(
        200,
        {
            "next": None,
            "results": [
                {
                    "set_num": "497-1",
                    "name": "Galaxy Explorer",
                    "year": 1979,
                    "theme_id": 158,
                    "num_parts": 338,
                    "set_img_url": None,
                    "set_url": "https://example.test/sets/497-1",
                }
            ],
        },
    )

    results = RebrickableClient("secret", transport=httpx.MockTransport(transport)).search_sets(
        "Galaxy Explorer", limit=2
    )

    assert [result.set_num for result in results] == ["10497-1", "497-1"]
    assert transport.requests[1].url.params["page"] == "2"


@pytest.mark.parametrize(
    "next_url",
    [
        "https://attacker.example/api/v3/lego/sets/?page=2",
        "https://rebrickable.com/api/v3/lego/parts/?page=2",
    ],
)
def test_remote_search_rejects_untrusted_next_without_requesting_it(
    next_url: str,
) -> None:
    """Following a foreign or wrong-path URL would leak the API key."""
    transport = MockTransport()
    transport.respond(200, {"next": next_url, "results": []})

    with pytest.raises(CatalogLookupError, match="Invalid upstream response") as error:
        RebrickableClient("secret", transport=httpx.MockTransport(transport)).search_sets(
            "Galaxy Explorer", limit=20
        )

    assert error.value.code == "invalid_response"
    assert len(transport.requests) == 1


def test_remote_search_rejects_cyclic_next_without_requesting_it() -> None:
    """Repeated pagination URLs would let an upstream response loop forever."""
    transport = MockTransport()
    transport.respond(
        200,
        {"next": "https://rebrickable.com/api/v3/lego/sets/?page=1", "results": []},
    )

    with pytest.raises(CatalogLookupError, match="Invalid upstream response") as error:
        RebrickableClient("secret", transport=httpx.MockTransport(transport)).search_sets(
            "Galaxy Explorer", limit=20
        )

    assert error.value.code == "invalid_response"
    assert len(transport.requests) == 1


def test_client_closes_owned_httpx_client() -> None:
    """Leaving a request-scoped HTTP client open leaks pooled connections."""
    transport = ClosingTransport()

    with RebrickableClient("secret", transport=transport):
        pass

    assert transport.closed is True


def test_client_closes_owned_httpx_client_when_request_fails() -> None:
    """An exception path must release the request-scoped connection pool too."""
    transport = ClosingTransport()

    with (
        pytest.raises(RuntimeError, match="lookup failed"),
        RebrickableClient("secret", transport=transport),
    ):
        raise RuntimeError("lookup failed")

    assert transport.closed is True


def test_targeted_lookup_keeps_csv_source_compatible_with_zip_refresh(
    session: Session,
) -> None:
    """Changing a CSV set's source makes the next ZIP refresh reject it as foreign."""
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "rebrickable-small"
    with (fixture_dir / "valid-catalog.zip").open("rb") as archive:
        import_rebrickable_zip(archive, session)
    import_rebrickable_set(
        ImportedSet(
            set_num="1234-1",
            name="Updated Castle Cart",
            year=2024,
            theme_id=10,
            num_parts=1,
            image_url=None,
            external_url="https://example.test/sets/1234-1",
            parts=[
                ImportedPart(
                    part_num="3001",
                    part_name="Brick 2 x 4",
                    part_image_url=None,
                    color_id=4,
                    color_name="Red",
                    rgb_hex="C91A09",
                    quantity=1,
                    is_spare=False,
                    source_id="1",
                )
            ],
        ),
        session,
    )

    with (fixture_dir / "valid-catalog.zip").open("rb") as archive:
        import_rebrickable_zip(archive, session)

    assert session.get_one(CatalogSet, "1234-1").name == "Castle Cart"


class ClosingTransport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.closed = False

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url}")

    def close(self) -> None:
        self.closed = True
