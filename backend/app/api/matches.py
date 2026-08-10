from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import require_auth
from app.db import get_session
from app.repositories.catalog import CatalogRepository, EffectiveSet
from app.schemas.matches import (
    MatchColorResponse,
    MatchCountsResponse,
    MatchPartResponse,
    MatchResponse,
    MissingRequirementResponse,
    SubstitutionResponse,
)
from app.services.inventory import InventoryItem, compute_inventory
from app.services.matcher import MatchAllocation, MatchResult, match_set
from app.services.recommendations import load_equivalence_map

router = APIRouter(
    prefix="/api/matches", tags=["matches"], dependencies=[Depends(require_auth)]
)


def _part(part_num: str, name: str, image_url: str | None) -> MatchPartResponse:
    return MatchPartResponse(part_num=part_num, name=name, image_url=image_url)


def _color(color_id: int, name: str, rgb_hex: str) -> MatchColorResponse:
    return MatchColorResponse(id=color_id, name=name, rgb_hex=rgb_hex)


def match_counts(result: MatchResult) -> MatchCountsResponse:
    return MatchCountsResponse(
        required=result.required_quantity,
        exact=result.exact_quantity,
        color_substitution=result.color_substitution_quantity,
        equivalence_substitution=result.equivalence_substitution_quantity,
        missing=result.missing_quantity,
    )


def substitution_stories(
    target: EffectiveSet,
    allocations: tuple[MatchAllocation, ...],
    inventory_items: tuple[InventoryItem, ...],
) -> list[SubstitutionResponse]:
    details = {(part.part_num, part.color_id): part for part in target.parts}
    supplied_details = {
        (item.part_num, item.color_id): item for item in inventory_items
    }
    grouped: dict[tuple[str, int, str, int, str], int] = defaultdict(int)
    for allocation in allocations:
        if allocation.kind == "exact":
            continue
        grouped[
            (
                allocation.required_part_num,
                allocation.required_color_id,
                allocation.supplied_part_num,
                allocation.supplied_color_id,
                allocation.kind,
            )
        ] += allocation.quantity

    stories: list[SubstitutionResponse] = []
    for (required_part_num, required_color_id, supplied_part_num, supplied_color_id, kind), quantity in sorted(grouped.items()):
        required = details[(required_part_num, required_color_id)]
        supplied = supplied_details[(supplied_part_num, supplied_color_id)]
        stories.append(
            SubstitutionResponse(
                required_part=_part(required.part_num, required.part_name, required.image_url),
                required_color=_color(required.color_id, required.color_name, required.rgb_hex),
                supplied_part=_part(
                    supplied_part_num,
                    supplied.part_name,
                    supplied.image_url,
                ),
                supplied_color=_color(
                    supplied.color_id, supplied.color_name, supplied.rgb_hex
                ),
                quantity=quantity,
                kind=kind,
            )
        )
    return stories


@router.get("/{set_num}", response_model=MatchResponse)
def get_match(
    set_num: str, session: Annotated[Session, Depends(get_session)]
) -> MatchResponse:
    target = CatalogRepository(session).get_effective_set(set_num)
    if target is None:
        raise HTTPException(status_code=404, detail="Set not found")
    inventory = compute_inventory(session)
    try:
        result = match_set(target, inventory, load_equivalence_map(session))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return MatchResponse(
        set_num=target.set_num,
        name=target.name,
        year=target.year,
        theme_name=target.theme_name,
        num_parts=target.num_parts,
        image_url=target.image_url,
        external_url=target.external_url,
        instructions_url=target.instructions_url,
        has_local_overrides=target.has_local_overrides,
        status=result.status,
        counts=match_counts(result),
        percent_exact=result.percent_exact,
        percent_buildable=result.percent_buildable,
        substitutions=substitution_stories(target, result.allocations, inventory.items),
        missing=[
            MissingRequirementResponse(
                part_num=value.part_num,
                part_name=value.part_name,
                color_id=value.color_id,
                color_name=value.color_name,
                quantity=value.quantity,
            )
            for value in result.missing
        ],
        warnings=list(inventory.warnings),
    )
