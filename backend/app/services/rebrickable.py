import json
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    CatalogColor,
    CatalogPart,
    CatalogSet,
    CatalogSetPart,
    SyncRun,
    utc_now,
)
from app.repositories.catalog import CatalogRepository, EffectiveSet
from app.schemas.catalog import ImportSummary, RemoteSetSummary
from app.services.catalog_import import (
    REBRICKABLE_SOURCE,
    CatalogImportError,
    _prepare_owned_session,
)

_API_ROOT = "https://rebrickable.com/api/v3/lego/sets"
_SOURCE = "rebrickable_api"


class CatalogLookupError(ValueError):
    def __init__(
        self, code: str, message: str, retry_after: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after


@dataclass(frozen=True)
class ImportedPart:
    part_num: str
    part_name: str
    part_image_url: str | None
    color_id: int
    color_name: str
    rgb_hex: str
    quantity: int
    is_spare: bool
    source_id: str


@dataclass(frozen=True)
class ImportedSet:
    set_num: str
    name: str
    year: int | None
    theme_id: int | None
    num_parts: int
    image_url: str | None
    external_url: str | None
    parts: list[ImportedPart]


class RebrickableClient:
    def __init__(self, api_key: str | None, *, transport: httpx.BaseTransport | None = None) -> None:
        if not api_key:
            raise CatalogLookupError("api_key_missing", "Rebrickable lookup is disabled")
        self._client = httpx.Client(
            headers={"Authorization": f"key {api_key}"},
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0),
            transport=transport,
        )

    def search_sets(self, query: str, limit: int) -> list[RemoteSetSummary]:
        results: list[RemoteSetSummary] = []
        next_url: str | None = f"{_API_ROOT}/"
        params: dict[str, object] | None = {"search": query, "page_size": limit}
        while next_url is not None and len(results) < limit:
            payload = self._json_object(self._request(next_url, params=params))
            results.extend(self._summary(row) for row in self._results(payload))
            next_value = payload.get("next")
            if next_value is not None and not isinstance(next_value, str):
                raise CatalogLookupError("invalid_response", "Invalid upstream response")
            next_url = next_value
            params = None
        return results[:limit]

    def lookup_set(self, set_num: str) -> ImportedSet:
        set_payload = self._json_object(self._request(f"{_API_ROOT}/{set_num}/"))
        summary = self._summary(set_payload)
        parts: list[ImportedPart] = []
        next_url: str | None = f"{_API_ROOT}/{set_num}/parts/"
        params: dict[str, object] | None = {
            "inc_minifig_parts": 1,
            "page_size": 1000,
        }
        while next_url is not None:
            page = self._json_object(self._request(next_url, params=params))
            parts.extend(self._part(row) for row in self._results(page))
            next_value = page.get("next")
            if next_value is not None and not isinstance(next_value, str):
                raise CatalogLookupError("invalid_response", "Invalid upstream response")
            next_url = next_value
            params = None
        return ImportedSet(
            set_num=summary.set_num,
            name=summary.name,
            year=summary.year,
            theme_id=_optional_int(set_payload, "theme_id"),
            num_parts=summary.num_parts,
            image_url=summary.image_url,
            external_url=summary.external_url,
            parts=parts,
        )

    def _request(self, url: str, *, params: dict[str, object] | None = None) -> httpx.Response:
        try:
            response = self._client.get(url, params=params)
        except httpx.TimeoutException as error:
            raise CatalogLookupError("unavailable", "Rebrickable is unavailable") from error
        except httpx.RequestError as error:
            raise CatalogLookupError("unavailable", "Rebrickable is unavailable") from error
        if response.status_code == 404:
            raise CatalogLookupError("not_found", "Set not found")
        if response.status_code == 429:
            retry_after = _retry_after(response.headers.get("Retry-After"))
            raise CatalogLookupError("throttled", "Rebrickable request was throttled", retry_after)
        if response.is_error:
            raise CatalogLookupError("unavailable", "Rebrickable is unavailable")
        return response

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise CatalogLookupError("invalid_response", "Invalid upstream response") from error
        if not isinstance(payload, dict):
            raise CatalogLookupError("invalid_response", "Invalid upstream response")
        return payload

    @staticmethod
    def _results(payload: dict[str, Any]) -> list[dict[str, Any]]:
        results = payload.get("results")
        if not isinstance(results, list) or not all(isinstance(row, dict) for row in results):
            raise CatalogLookupError("invalid_response", "Invalid upstream response")
        return results

    @staticmethod
    def _summary(row: dict[str, Any]) -> RemoteSetSummary:
        try:
            return RemoteSetSummary(
                set_num=_string(row, "set_num"),
                name=_string(row, "name"),
                year=_optional_int(row, "year"),
                theme_id=_optional_int(row, "theme_id"),
                num_parts=_nonnegative_int(row, "num_parts"),
                image_url=_optional_string(row, "set_img_url"),
                external_url=_optional_string(row, "set_url"),
            )
        except (TypeError, ValueError) as error:
            raise CatalogLookupError("invalid_response", "Invalid upstream response") from error

    @staticmethod
    def _part(row: dict[str, Any]) -> ImportedPart:
        try:
            part = _object(row, "part")
            color = _object(row, "color")
            return ImportedPart(
                part_num=_string(part, "part_num"),
                part_name=_string(part, "name"),
                part_image_url=_optional_string(part, "part_img_url"),
                color_id=_nonnegative_int(color, "id"),
                color_name=_string(color, "name"),
                rgb_hex=_string(color, "rgb"),
                quantity=_positive_int(row, "quantity"),
                is_spare=_boolean(row, "is_spare"),
                source_id=str(_nonnegative_int(row, "id")),
            )
        except (TypeError, ValueError) as error:
            raise CatalogLookupError("invalid_response", "Invalid upstream response") from error


def import_rebrickable_set(imported: ImportedSet, session: Session) -> tuple[EffectiveSet, ImportSummary]:
    _prepare_owned_session(session)
    started_at = utc_now()
    try:
        existing = session.get(CatalogSet, imported.set_num)
        if existing is not None and existing.source not in {REBRICKABLE_SOURCE, _SOURCE}:
            raise CatalogImportError(f"set {imported.set_num!r} conflicts with source {existing.source!r}")
        if existing is None:
            existing = CatalogSet(set_num=imported.set_num)
            session.add(existing)
        existing.name = imported.name
        existing.year = imported.year
        existing.theme_id = imported.theme_id
        existing.theme_name = None
        existing.num_parts = imported.num_parts
        existing.image_url = imported.image_url
        existing.external_url = imported.external_url
        existing.instructions_url = None
        existing.source = _SOURCE
        existing.source_updated_at = None
        existing.imported_at = utc_now()

        for part in imported.parts:
            catalog_part = session.get(CatalogPart, part.part_num)
            if catalog_part is None:
                catalog_part = CatalogPart(part_num=part.part_num)
                session.add(catalog_part)
            catalog_part.name = part.part_name
            catalog_part.category_name = None
            catalog_part.image_url = part.part_image_url
            catalog_part.external_ids_json = "{}"
            color = session.get(CatalogColor, part.color_id)
            if color is None:
                color = CatalogColor(id=part.color_id)
                session.add(color)
            color.name = part.color_name
            color.rgb_hex = part.rgb_hex
            color.external_ids_json = "{}"
        session.flush()
        session.execute(delete(CatalogSetPart).where(CatalogSetPart.set_num == imported.set_num))
        for part in imported.parts:
            session.add(
                CatalogSetPart(
                    set_num=imported.set_num,
                    part_num=part.part_num,
                    color_id=part.color_id,
                    quantity=part.quantity,
                    is_spare=part.is_spare,
                    source_kind="rebrickable_api",
                    source_id=part.source_id,
                )
            )
        completed_at = utc_now()
        summary_data = {"sets": 1, "parts": len(imported.parts), "colors": len({part.color_id for part in imported.parts}), "warnings": []}
        run = SyncRun(source=_SOURCE, status="completed", started_at=started_at, completed_at=completed_at, summary_json=json.dumps(summary_data), error=None)
        session.add(run)
        session.commit()
    except (CatalogImportError, SQLAlchemyError) as error:
        session.rollback()
        if isinstance(error, CatalogImportError):
            raise
        raise CatalogImportError(f"catalog lookup import failed: {error}") from error
    result = CatalogRepository(session).get_effective_set(imported.set_num)
    if result is None:
        raise RuntimeError("looked up set missing after committed import")
    return result, ImportSummary(sync_run_id=run.id, started_at=started_at, completed_at=completed_at, **summary_data)


def _object(values: dict[str, Any], key: str) -> dict[str, Any]:
    value = values.get(key)
    if not isinstance(value, dict):
        raise TypeError(key)
    return value


def _string(values: dict[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(key)
    return value


def _optional_string(values: dict[str, Any], key: str) -> str | None:
    value = values.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(key)
    return value


def _optional_int(values: dict[str, Any], key: str) -> int | None:
    value = values.get(key)
    if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
        raise ValueError(key)
    return value


def _nonnegative_int(values: dict[str, Any], key: str) -> int:
    value = values.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(key)
    return value


def _positive_int(values: dict[str, Any], key: str) -> int:
    value = _nonnegative_int(values, key)
    if value == 0:
        raise ValueError(key)
    return value


def _boolean(values: dict[str, Any], key: str) -> bool:
    value = values.get(key)
    if not isinstance(value, bool):
        raise TypeError(key)
    return value


def _retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        result = int(value)
    except ValueError:
        return None
    return result if result >= 0 else None
