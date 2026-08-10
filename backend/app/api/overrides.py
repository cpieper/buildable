from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_auth
from app.db import get_session
from app.models import (
    CatalogColor,
    CatalogPart,
    CatalogSet,
    CatalogSetOverride,
    CatalogSetPartOverride,
)
from app.repositories.catalog import CatalogRepository, EffectivePartRow
from app.schemas.settings import (
    OverrideDelete,
    PartCorrectionResponse,
    PartOverrideDelete,
    PartOverrideWrite,
    SetCorrectionResponse,
    SetCorrectionsResponse,
    SetOverrideWrite,
)

router = APIRouter(prefix="/api/overrides", tags=["overrides"], dependencies=[Depends(require_auth)])

_SET_FIELDS = ("name", "year", "theme_name", "num_parts", "image_url", "external_url", "instructions_url")


def _set_or_404(session: Session, set_num: str) -> CatalogSet:
    catalog_set = session.get(CatalogSet, set_num)
    if catalog_set is None:
        raise HTTPException(status_code=404, detail="Set not found")
    return catalog_set


def _set_response(session: Session, set_num: str) -> SetCorrectionResponse:
    catalog_set = _set_or_404(session, set_num)
    override = session.get(CatalogSetOverride, set_num)
    effective = CatalogRepository(session).get_effective_set(set_num)
    assert effective is not None
    imported = {field: getattr(catalog_set, field) for field in _SET_FIELDS}
    raw_override = None if override is None else {field: getattr(override, field) for field in _SET_FIELDS} | {"reason": override.reason}
    effective_values = {field: getattr(effective, field) for field in _SET_FIELDS}
    return SetCorrectionResponse(imported=imported, override=raw_override, effective=effective_values, has_local_overrides=effective.has_local_overrides)


def _part_data(row: EffectivePartRow) -> dict[str, object]:
    return {"part_num": row.part_num, "part_name": row.part_name, "color_id": row.color_id, "color_name": row.color_name, "rgb_hex": row.rgb_hex, "quantity": row.quantity, "is_spare": row.is_spare, "source_kind": row.source_kind, "image_url": row.image_url}


def _part_response(session: Session, override: CatalogSetPartOverride) -> PartCorrectionResponse:
    repository = CatalogRepository(session)
    imported_row = repository._load_imported_parts(override.set_num).get(
        (override.part_num, override.color_id, override.is_spare)
    )
    imported = None if imported_row is None else _part_data(imported_row)
    effective_set = repository.get_effective_set(override.set_num)
    assert effective_set is not None
    effective_row = next((row for row in effective_set.parts if (row.part_num, row.color_id, row.is_spare) == (override.part_num, override.color_id, override.is_spare)), None)
    return PartCorrectionResponse(imported=imported, override={"part_num": override.part_num, "color_id": override.color_id, "is_spare": override.is_spare, "operation": override.operation, "quantity": override.quantity, "reason": override.reason}, effective=None if effective_row is None else _part_data(effective_row), has_local_overrides=effective_set.has_local_overrides)


@router.put("/sets/{set_num}", response_model=SetCorrectionResponse)
def put_set_override(set_num: str, payload: SetOverrideWrite, session: Annotated[Session, Depends(get_session)]) -> SetCorrectionResponse:
    _set_or_404(session, set_num)
    override = session.get(CatalogSetOverride, set_num)
    changes = payload.model_dump(include=payload.model_fields_set)
    correction_fields = set(_SET_FIELDS).intersection(changes)
    if override is None:
        if not any(changes[field] is not None for field in correction_fields):
            return _set_response(session, set_num)
        override = CatalogSetOverride(set_num=set_num)
        session.add(override)
    for field in correction_fields:
        value = changes[field]
        setattr(override, field, value)
    override.reason = payload.reason
    if all(getattr(override, field) is None for field in _SET_FIELDS):
        session.delete(override)
    session.commit()
    return _set_response(session, set_num)


@router.delete("/sets/{set_num}", status_code=status.HTTP_204_NO_CONTENT)
def delete_set_override(set_num: str, payload: Annotated[OverrideDelete, Body()], session: Annotated[Session, Depends(get_session)]) -> None:
    del payload
    override = session.get(CatalogSetOverride, set_num)
    if override is None:
        raise HTTPException(status_code=404, detail="Set override not found")
    session.delete(override)
    session.commit()


@router.put("/sets/{set_num}/parts/{part_num}/{color_id}", response_model=PartCorrectionResponse)
def put_part_override(set_num: str, part_num: str, color_id: int, payload: PartOverrideWrite, session: Annotated[Session, Depends(get_session)]) -> PartCorrectionResponse:
    _set_or_404(session, set_num)
    if session.get(CatalogPart, part_num) is None or session.get(CatalogColor, color_id) is None:
        raise HTTPException(status_code=404, detail="Catalog part or color not found")
    override = session.scalar(select(CatalogSetPartOverride).where(CatalogSetPartOverride.set_num == set_num, CatalogSetPartOverride.part_num == part_num, CatalogSetPartOverride.color_id == color_id, CatalogSetPartOverride.is_spare == payload.is_spare))
    if override is None:
        override = CatalogSetPartOverride(set_num=set_num, part_num=part_num, color_id=color_id, **payload.model_dump())
        session.add(override)
    else:
        for field, value in payload.model_dump().items():
            setattr(override, field, value)
    session.commit()
    return _part_response(session, override)


@router.delete("/sets/{set_num}/parts/{part_num}/{color_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_part_override(set_num: str, part_num: str, color_id: int, payload: Annotated[PartOverrideDelete, Body()], session: Annotated[Session, Depends(get_session)]) -> None:
    override = session.scalar(select(CatalogSetPartOverride).where(CatalogSetPartOverride.set_num == set_num, CatalogSetPartOverride.part_num == part_num, CatalogSetPartOverride.color_id == color_id, CatalogSetPartOverride.is_spare == payload.is_spare))
    if override is None:
        raise HTTPException(status_code=404, detail="Part override not found")
    session.delete(override)
    session.commit()


@router.get("/sets/{set_num}", response_model=SetCorrectionsResponse)
def get_set_overrides(set_num: str, session: Annotated[Session, Depends(get_session)]) -> SetCorrectionsResponse:
    metadata = _set_response(session, set_num)
    overrides = session.scalars(select(CatalogSetPartOverride).where(CatalogSetPartOverride.set_num == set_num).order_by(CatalogSetPartOverride.part_num, CatalogSetPartOverride.color_id, CatalogSetPartOverride.is_spare)).all()
    if metadata.override is None and not overrides:
        raise HTTPException(status_code=404, detail="No local overrides for set")
    return SetCorrectionsResponse(metadata=metadata, parts=[_part_response(session, override) for override in overrides])
