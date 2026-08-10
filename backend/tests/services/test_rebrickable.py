import httpx
import pytest
from sqlalchemy.orm import Session

from app.models import CatalogSet
from app.services.rebrickable import CatalogLookupError, RebrickableClient


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
