from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_auth
from app.db import get_session
from app.schemas.inventory import InventoryResponse
from app.services.inventory import compute_inventory

router = APIRouter(
    prefix="/api/inventory", tags=["inventory"], dependencies=[Depends(require_auth)]
)


@router.get("", response_model=InventoryResponse)
def inventory(
    session: Annotated[Session, Depends(get_session)],
    q: Annotated[str, Query()] = "",
    color_id: Annotated[int | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> InventoryResponse:
    snapshot = compute_inventory(session)
    normalized = q.strip().casefold()
    items = [
        item
        for item in snapshot.items
        if (
            not normalized
            or normalized in item.part_num.casefold()
            or normalized in item.part_name.casefold()
        )
        and (color_id is None or item.color_id == color_id)
    ]
    return InventoryResponse(
        items=items[offset : offset + limit],
        warnings=list(snapshot.warnings),
        total_quantity=snapshot.total_quantity,
    )
