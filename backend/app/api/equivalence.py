from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_auth
from app.db import get_session
from app.models import CatalogPart, EquivalenceGroup, EquivalenceMember
from app.schemas.settings import EquivalenceGroupResponse, EquivalenceGroupWrite

router = APIRouter(prefix="/api/equivalence-groups", tags=["equivalence-groups"], dependencies=[Depends(require_auth)])


def _response(session: Session, group: EquivalenceGroup) -> EquivalenceGroupResponse:
    return EquivalenceGroupResponse(id=group.id, name=group.name, notes=group.notes, created_at=group.created_at, updated_at=group.updated_at, part_nums=sorted(session.scalars(select(EquivalenceMember.part_num).where(EquivalenceMember.group_id == group.id)).all()))


def _validate_members(session: Session, part_nums: list[str], group_id: int | None = None) -> None:
    found = set(session.scalars(select(CatalogPart.part_num).where(CatalogPart.part_num.in_(part_nums))).all())
    if found != set(part_nums):
        raise HTTPException(status_code=422, detail="All equivalence members must be existing catalog parts")
    statement = select(EquivalenceMember.part_num).where(EquivalenceMember.part_num.in_(part_nums))
    if group_id is not None:
        statement = statement.where(EquivalenceMember.group_id != group_id)
    conflict = session.scalar(statement)
    if conflict is not None:
        raise HTTPException(status_code=409, detail={"code": "part_already_grouped", "message": f"Part {conflict} already belongs to an equivalence group"})


def _group_or_404(session: Session, group_id: int) -> EquivalenceGroup:
    group = session.get(EquivalenceGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Equivalence group not found")
    return group


@router.get("", response_model=list[EquivalenceGroupResponse])
def list_groups(session: Annotated[Session, Depends(get_session)]) -> list[EquivalenceGroupResponse]:
    return [_response(session, group) for group in session.scalars(select(EquivalenceGroup).order_by(EquivalenceGroup.id)).all()]


@router.post("", response_model=EquivalenceGroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(payload: EquivalenceGroupWrite, session: Annotated[Session, Depends(get_session)]) -> EquivalenceGroupResponse:
    if session.scalar(select(EquivalenceGroup).where(EquivalenceGroup.name == payload.name)) is not None:
        raise HTTPException(status_code=409, detail={"code": "name_already_exists", "message": "Equivalence group name already exists"})
    _validate_members(session, payload.part_nums)
    group = EquivalenceGroup(name=payload.name, notes=payload.notes)
    session.add(group)
    session.flush()
    session.add_all(EquivalenceMember(group_id=group.id, part_num=part_num) for part_num in payload.part_nums)
    session.commit()
    session.refresh(group)
    return _response(session, group)


@router.put("/{group_id}", response_model=EquivalenceGroupResponse)
def update_group(group_id: int, payload: EquivalenceGroupWrite, session: Annotated[Session, Depends(get_session)]) -> EquivalenceGroupResponse:
    group = _group_or_404(session, group_id)
    duplicate = session.scalar(select(EquivalenceGroup).where(EquivalenceGroup.name == payload.name, EquivalenceGroup.id != group_id))
    if duplicate is not None:
        raise HTTPException(status_code=409, detail={"code": "name_already_exists", "message": "Equivalence group name already exists"})
    _validate_members(session, payload.part_nums, group_id)
    group.name = payload.name
    group.notes = payload.notes
    for member in session.scalars(select(EquivalenceMember).where(EquivalenceMember.group_id == group_id)).all():
        session.delete(member)
    session.flush()
    session.add_all(EquivalenceMember(group_id=group_id, part_num=part_num) for part_num in payload.part_nums)
    session.commit()
    session.refresh(group)
    return _response(session, group)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: int, session: Annotated[Session, Depends(get_session)]) -> None:
    session.delete(_group_or_404(session, group_id))
    session.commit()
