from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_auth
from app.api.matches import match_counts
from app.db import get_session
from app.schemas.matches import RecommendationItemResponse, RecommendationsResponse
from app.services.inventory import compute_inventory
from app.services.recommendations import (
    MatchStatus,
    RecommendationSort,
    SortDirection,
    evaluate_recommendations,
    sort_recommendations,
)

router = APIRouter(
    prefix="/api/recommendations",
    tags=["recommendations"],
    dependencies=[Depends(require_auth)],
)


def _statuses(value: str | None) -> frozenset[MatchStatus] | None:
    if value is None or not value.strip():
        return None
    allowed = {"exact", "substitution", "missing"}
    parsed = frozenset(item.strip() for item in value.split(",") if item.strip())
    if not parsed or not parsed <= allowed:
        raise HTTPException(status_code=422, detail="status must contain exact, substitution, or missing")
    return parsed  # type: ignore[return-value]


@router.get("", response_model=RecommendationsResponse)
def recommendations(
    session: Annotated[Session, Depends(get_session)],
    status: Annotated[str | None, Query()] = None,
    max_pieces: Annotated[int | None, Query(ge=0)] = None,
    theme: Annotated[str | None, Query()] = None,
    year_from: Annotated[int | None, Query()] = None,
    year_to: Annotated[int | None, Query()] = None,
    hide_owned: Annotated[bool, Query()] = True,
    sort: Annotated[RecommendationSort, Query()] = "buildability",
    direction: Annotated[SortDirection, Query()] = "asc",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RecommendationsResponse:
    if year_from is not None and year_to is not None and year_from > year_to:
        raise HTTPException(status_code=422, detail="year_from must not exceed year_to")
    inventory = compute_inventory(session)
    active_max_pieces = inventory.total_quantity if max_pieces is None else max_pieces
    # An explicit zero disables the threshold; an empty collection's default does not.
    sql_max_pieces = active_max_pieces if max_pieces is None or max_pieces > 0 else None
    active_theme = theme.strip() if theme and theme.strip() else None
    matches = evaluate_recommendations(
        session,
        inventory,
        max_pieces=sql_max_pieces,
        theme=active_theme,
        year_from=year_from,
        year_to=year_to,
        hide_owned=hide_owned,
        statuses=_statuses(status),
    )
    ordered = sort_recommendations(matches, sort, direction, default=sort == "buildability" and direction == "asc")
    return RecommendationsResponse(
        items=[
            RecommendationItemResponse(
                set_num=item.target.set_num,
                name=item.target.name,
                year=item.target.year,
                theme_name=item.target.theme_name,
                num_parts=item.target.num_parts,
                image_url=item.target.image_url,
                has_local_overrides=item.target.has_local_overrides,
                status=item.result.status,
                counts=match_counts(item.result),
                percent_exact=item.result.percent_exact,
                percent_buildable=item.result.percent_buildable,
            )
            for item in ordered[offset : offset + limit]
        ],
        total_candidates=len(ordered),
        offset=offset,
        limit=limit,
        max_pieces=active_max_pieces,
        theme=active_theme,
        year_from=year_from,
        year_to=year_to,
        hide_owned=hide_owned,
        status=sorted(_statuses(status)) if _statuses(status) is not None else None,
        sort=sort,
        direction=direction,
    )
