from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_auth
from app.db import get_session
from app.models import OwnedSet, OwnedSetMissingPart
from app.repositories.catalog import CatalogRepository
from app.schemas.collection import (
    CollectionImportSummary,
    MissingPartCreate,
    MissingPartResponse,
    MissingPartUpdate,
    OwnedSetCreate,
    OwnedSetResponse,
    OwnedSetUpdate,
)
from app.services.collection_import import (
    CollectionImportError,
    import_rebrickable_collection_csv,
)

router = APIRouter(
    prefix="/api/collection", tags=["collection"], dependencies=[Depends(require_auth)]
)


def _owned_or_404(session: Session, owned_set_id: int) -> OwnedSet:
    owned = session.get(OwnedSet, owned_set_id)
    if owned is None:
        raise HTTPException(status_code=404, detail="Owned set not found")
    return owned


def _response(session: Session, owned: OwnedSet) -> OwnedSetResponse:
    effective = CatalogRepository(session).get_effective_set(owned.set_num)
    if effective is None:
        raise HTTPException(status_code=404, detail="Catalog set not found")
    missing_total = session.scalar(
        select(func.coalesce(func.sum(OwnedSetMissingPart.quantity), 0)).where(
            OwnedSetMissingPart.owned_set_id == owned.id
        )
    )
    return OwnedSetResponse(
        id=owned.id,
        set_num=owned.set_num,
        set_name=effective.name,
        quantity=owned.quantity,
        completeness=owned.completeness,
        unknown_missing_count=owned.unknown_missing_count,
        unknown_missing_note=owned.unknown_missing_note,
        notes=owned.notes,
        known_missing_total=missing_total or 0,
        has_local_overrides=effective.has_local_overrides,
        added_at=owned.added_at,
        updated_at=owned.updated_at,
    )


def _validate_missing_total(
    session: Session,
    owned: OwnedSet,
    part_num: str,
    color_id: int,
    proposed: int,
    exclude_id: int | None = None,
) -> None:
    effective = CatalogRepository(session).get_effective_set(owned.set_num)
    if effective is None:
        raise HTTPException(status_code=404, detail="Catalog set not found")
    expected = (
        sum(
            part.quantity
            for part in effective.parts
            if part.part_num == part_num and part.color_id == color_id
        )
        * owned.quantity
    )
    statement = select(func.coalesce(func.sum(OwnedSetMissingPart.quantity), 0)).where(
        OwnedSetMissingPart.owned_set_id == owned.id,
        OwnedSetMissingPart.part_num == part_num,
        OwnedSetMissingPart.color_id == color_id,
    )
    if exclude_id is not None:
        statement = statement.where(OwnedSetMissingPart.id != exclude_id)
    existing = session.scalar(statement) or 0
    if proposed + existing > expected:
        raise HTTPException(
            status_code=422,
            detail="Missing quantity exceeds effective expected quantity",
        )


def _validate_all_missing(session: Session, owned: OwnedSet) -> None:
    for part_num, color_id, missing_total in session.execute(
        select(
            OwnedSetMissingPart.part_num,
            OwnedSetMissingPart.color_id,
            func.sum(OwnedSetMissingPart.quantity),
        )
        .where(OwnedSetMissingPart.owned_set_id == owned.id)
        .group_by(OwnedSetMissingPart.part_num, OwnedSetMissingPart.color_id)
    ):
        effective = CatalogRepository(session).get_effective_set(owned.set_num)
        if effective is None:
            raise HTTPException(status_code=404, detail="Catalog set not found")
        expected = (
            sum(
                part.quantity
                for part in effective.parts
                if part.part_num == part_num and part.color_id == color_id
            )
            * owned.quantity
        )
        if missing_total > expected:
            raise HTTPException(
                status_code=422,
                detail="Missing quantity exceeds effective expected quantity",
            )


@router.get("", response_model=list[OwnedSetResponse])
def list_collection(
    session: Annotated[Session, Depends(get_session)],
) -> list[OwnedSetResponse]:
    return [
        _response(session, owned)
        for owned in session.scalars(select(OwnedSet).order_by(OwnedSet.id)).all()
    ]


@router.post("", response_model=OwnedSetResponse, status_code=status.HTTP_201_CREATED)
def add_set(
    payload: OwnedSetCreate, session: Annotated[Session, Depends(get_session)]
) -> OwnedSetResponse:
    if CatalogRepository(session).get_effective_set(payload.set_num) is None:
        raise HTTPException(status_code=404, detail="Catalog set not found")
    owned = session.scalar(select(OwnedSet).where(OwnedSet.set_num == payload.set_num))
    if owned is None:
        owned = OwnedSet(**payload.model_dump())
        session.add(owned)
    else:
        owned.quantity += payload.quantity
    session.commit()
    session.refresh(owned)
    return _response(session, owned)


@router.post("/import", response_model=CollectionImportSummary)
def import_collection(
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_session)],
) -> CollectionImportSummary:
    try:
        return import_rebrickable_collection_csv(file.file, session)
    except CollectionImportError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.patch("/{owned_set_id}", response_model=OwnedSetResponse)
def update_set(
    owned_set_id: int,
    payload: OwnedSetUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> OwnedSetResponse:
    owned = _owned_or_404(session, owned_set_id)
    changes = payload.model_dump(exclude_unset=True)
    new_quantity = changes.get("quantity", owned.quantity)
    if new_quantity != owned.quantity:
        original = owned.quantity
        owned.quantity = new_quantity
        try:
            _validate_all_missing(session, owned)
        except Exception:
            owned.quantity = original
            raise
    for key, value in changes.items():
        setattr(owned, key, value)
    session.commit()
    session.refresh(owned)
    return _response(session, owned)


@router.delete("/{owned_set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_set(
    owned_set_id: int, session: Annotated[Session, Depends(get_session)]
) -> None:
    session.delete(_owned_or_404(session, owned_set_id))
    session.commit()


@router.get("/{owned_set_id}/missing-parts", response_model=list[MissingPartResponse])
def list_missing(
    owned_set_id: int, session: Annotated[Session, Depends(get_session)]
) -> list[OwnedSetMissingPart]:
    _owned_or_404(session, owned_set_id)
    return session.scalars(
        select(OwnedSetMissingPart)
        .where(OwnedSetMissingPart.owned_set_id == owned_set_id)
        .order_by(OwnedSetMissingPart.id)
    ).all()


@router.post(
    "/{owned_set_id}/missing-parts",
    response_model=MissingPartResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_missing(
    owned_set_id: int,
    payload: MissingPartCreate,
    session: Annotated[Session, Depends(get_session)],
) -> OwnedSetMissingPart:
    owned = _owned_or_404(session, owned_set_id)
    _validate_missing_total(
        session, owned, payload.part_num, payload.color_id, payload.quantity
    )
    missing = OwnedSetMissingPart(owned_set_id=owned.id, **payload.model_dump())
    session.add(missing)
    session.commit()
    session.refresh(missing)
    return missing


@router.patch(
    "/{owned_set_id}/missing-parts/{missing_id}", response_model=MissingPartResponse
)
def update_missing(
    owned_set_id: int,
    missing_id: int,
    payload: MissingPartUpdate,
    session: Annotated[Session, Depends(get_session)],
) -> OwnedSetMissingPart:
    owned = _owned_or_404(session, owned_set_id)
    missing = session.get(OwnedSetMissingPart, missing_id)
    if missing is None or missing.owned_set_id != owned.id:
        raise HTTPException(status_code=404, detail="Missing part not found")
    changes = payload.model_dump(exclude_unset=True)
    if "quantity" in changes:
        _validate_missing_total(
            session,
            owned,
            missing.part_num,
            missing.color_id,
            changes["quantity"],
            missing.id,
        )
    for key, value in changes.items():
        setattr(missing, key, value)
    session.commit()
    session.refresh(missing)
    return missing


@router.delete(
    "/{owned_set_id}/missing-parts/{missing_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_missing(
    owned_set_id: int,
    missing_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    _owned_or_404(session, owned_set_id)
    missing = session.get(OwnedSetMissingPart, missing_id)
    if missing is None or missing.owned_set_id != owned_set_id:
        raise HTTPException(status_code=404, detail="Missing part not found")
    session.delete(missing)
    session.commit()
