from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CatalogSet,
    CatalogSetOverride,
    EquivalenceMember,
    OwnedSet,
)
from app.repositories.catalog import CatalogRepository, EffectiveSet
from app.services.inventory import InventorySnapshot
from app.services.matcher import MatchResult, match_set

MatchStatus = Literal["exact", "substitution", "missing"]
RecommendationSort = Literal["buildability", "pieces", "year", "mismatches", "missing"]
SortDirection = Literal["asc", "desc"]


@dataclass(frozen=True)
class Recommendation:
    target: EffectiveSet
    result: MatchResult


def load_equivalence_map(session: Session) -> dict[str, frozenset[str]]:
    members_by_group: dict[int, set[str]] = defaultdict(set)
    for group_id, part_num in session.execute(
        select(EquivalenceMember.group_id, EquivalenceMember.part_num)
    ):
        members_by_group[group_id].add(part_num)

    equivalents: dict[str, set[str]] = defaultdict(set)
    for members in members_by_group.values():
        for part_num in members:
            equivalents[part_num].update(members - {part_num})
    return {part_num: frozenset(values) for part_num, values in equivalents.items()}


def candidate_set_numbers(
    session: Session,
    *,
    max_pieces: int | None,
    theme: str | None,
    year_from: int | None,
    year_to: int | None,
    hide_owned: bool,
) -> list[str]:
    """Apply catalog-sized filters in SQL before local matcher evaluation."""
    effective_num_parts = func.coalesce(CatalogSetOverride.num_parts, CatalogSet.num_parts)
    effective_theme = func.coalesce(CatalogSetOverride.theme_name, CatalogSet.theme_name)
    effective_year = func.coalesce(CatalogSetOverride.year, CatalogSet.year)
    statement = select(CatalogSet.set_num).outerjoin(CatalogSetOverride)
    if max_pieces is not None:
        statement = statement.where(effective_num_parts <= max_pieces)
    if theme:
        statement = statement.where(func.lower(effective_theme) == theme.casefold())
    if year_from is not None:
        statement = statement.where(effective_year >= year_from)
    if year_to is not None:
        statement = statement.where(effective_year <= year_to)
    if hide_owned:
        statement = statement.where(
            ~CatalogSet.set_num.in_(select(OwnedSet.set_num))
        )
    return list(session.scalars(statement.order_by(CatalogSet.set_num)))


def evaluate_recommendations(
    session: Session,
    inventory: InventorySnapshot,
    *,
    max_pieces: int | None,
    theme: str | None,
    year_from: int | None,
    year_to: int | None,
    hide_owned: bool,
    statuses: frozenset[MatchStatus] | None,
) -> list[Recommendation]:
    repository = CatalogRepository(session)
    equivalents = load_equivalence_map(session)
    recommendations: list[Recommendation] = []
    for set_num in candidate_set_numbers(
        session,
        max_pieces=max_pieces,
        theme=theme,
        year_from=year_from,
        year_to=year_to,
        hide_owned=hide_owned,
    ):
        target = repository.get_effective_set(set_num)
        if target is None:
            continue
        try:
            result = match_set(target, inventory, equivalents)
        except ValueError:
            continue
        if statuses is None or result.status in statuses:
            recommendations.append(Recommendation(target, result))
    return recommendations


def sort_recommendations(
    recommendations: Iterable[Recommendation],
    sort: RecommendationSort,
    direction: SortDirection,
    *,
    default: bool,
) -> list[Recommendation]:
    values = list(recommendations)
    if default:
        ranks = {"exact": 0, "substitution": 1, "missing": 2}
        return sorted(
            values,
            key=lambda item: (
                ranks[item.result.status],
                item.result.missing_quantity,
                item.result.color_substitution_quantity
                + item.result.equivalence_substitution_quantity,
                item.target.set_num,
            ),
        )

    def ordered_by(metric: object) -> list[Recommendation]:
        return sorted(
            sorted(values, key=lambda item: item.target.set_num),
            key=metric,
            reverse=direction == "desc",
        )

    if sort == "buildability":
        ranks = {"exact": 0, "substitution": 1, "missing": 2}
        return ordered_by(lambda item: ranks[item.result.status])
    if sort == "pieces":
        return ordered_by(lambda item: item.target.num_parts)
    if sort == "year":
        return ordered_by(
            lambda item: (item.target.year is None, item.target.year or 0)
        )
    if sort == "mismatches":
        return ordered_by(
            lambda item: (
                item.result.color_substitution_quantity
                + item.result.equivalence_substitution_quantity,
            )
        )
    return ordered_by(lambda item: item.result.missing_quantity)
