from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_auth
from app.db import get_session
from app.repositories.catalog import CatalogRepository, EffectiveSet
from app.schemas.catalog import (
    CatalogSetDetail,
    CatalogSetSummary,
    ImportSummary,
    ManualCatalogSetCreate,
)
from app.services.catalog_import import (
    CatalogImportError,
    import_manual_set,
    import_rebrickable_zip,
)

router = APIRouter(
    prefix="/api/catalog",
    tags=["catalog"],
    dependencies=[Depends(require_auth)],
)


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
