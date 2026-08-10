from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_request_settings, require_auth
from app.config import Settings
from app.db import get_session
from app.repositories.catalog import CatalogRepository, EffectiveSet
from app.schemas.catalog import (
    CatalogLookupResponse,
    CatalogSetDetail,
    CatalogSetSummary,
    ImportSummary,
    ManualCatalogSetCreate,
    RemoteSetSummary,
)
from app.services.catalog_import import (
    CatalogImportError,
    import_manual_set,
    import_rebrickable_zip,
)
from app.services.rebrickable import (
    CatalogLookupError,
    RebrickableClient,
    import_rebrickable_set,
)

router = APIRouter(
    prefix="/api/catalog",
    tags=["catalog"],
    dependencies=[Depends(require_auth)],
)


def _lookup_error(error: CatalogLookupError) -> HTTPException:
    mapping = {
        "api_key_missing": (status.HTTP_409_CONFLICT, "api_key_missing"),
        "not_found": (status.HTTP_404_NOT_FOUND, "set_not_found"),
        "throttled": (status.HTTP_429_TOO_MANY_REQUESTS, "rebrickable_throttled"),
        "unavailable": (status.HTTP_503_SERVICE_UNAVAILABLE, "rebrickable_unavailable"),
        "invalid_response": (status.HTTP_502_BAD_GATEWAY, "invalid_upstream_response"),
    }
    status_code, code = mapping[error.code]
    headers = (
        {"Retry-After": str(error.retry_after)}
        if error.retry_after is not None
        else None
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": error.message, "retry_after": error.retry_after},
        headers=headers,
    )


@router.get("/remote-search", response_model=list[RemoteSetSummary])
def remote_search(
    settings: Annotated[Settings, Depends(get_request_settings)],
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RemoteSetSummary]:
    try:
        return RebrickableClient(settings.rebrickable_api_key).search_sets(q, limit)
    except CatalogLookupError as error:
        raise _lookup_error(error) from error


@router.post("/lookup/{set_num}", response_model=CatalogLookupResponse)
def lookup_set(
    set_num: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> CatalogLookupResponse:
    try:
        imported = RebrickableClient(settings.rebrickable_api_key).lookup_set(set_num)
        effective_set, summary = import_rebrickable_set(imported, session)
        return CatalogLookupResponse(set=effective_set, summary=summary)
    except CatalogLookupError as error:
        raise _lookup_error(error) from error
    except CatalogImportError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "invalid_upstream_response",
                "message": str(error),
                "retry_after": None,
            },
        ) from error


@router.post("/import", response_model=ImportSummary)
def import_catalog(
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_session)],
) -> ImportSummary:
    try:
        return import_rebrickable_zip(file.file, session)
    except CatalogImportError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.post(
    "/manual-sets",
    response_model=CatalogSetDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_set(
    payload: ManualCatalogSetCreate,
    session: Annotated[Session, Depends(get_session)],
) -> EffectiveSet:
    try:
        return import_manual_set(payload, session)
    except CatalogImportError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get("/sets", response_model=list[CatalogSetSummary])
def search_sets(
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[EffectiveSet]:
    return CatalogRepository(session).search_sets(q, limit)


@router.get("/sets/{set_num}", response_model=CatalogSetDetail)
def get_set(
    set_num: str,
    session: Annotated[Session, Depends(get_session)],
) -> EffectiveSet:
    result = CatalogRepository(session).get_effective_set(set_num)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Set not found")
    return result
