from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from app.repositories.catalog import EffectivePartRow, EffectiveSet
from app.services.inventory import InventorySnapshot


@dataclass(frozen=True)
class MatchAllocation:
    required_part_num: str
    required_color_id: int
    supplied_part_num: str
    supplied_color_id: int
    quantity: int
    kind: Literal["exact", "color", "equivalent_exact_color", "equivalent_color"]


@dataclass(frozen=True)
class MissingRequirement:
    part_num: str
    part_name: str
    color_id: int
    color_name: str
    quantity: int


@dataclass(frozen=True)
class MatchResult:
    status: Literal["exact", "substitution", "missing"]
    required_quantity: int
    exact_quantity: int
    color_substitution_quantity: int
    equivalence_substitution_quantity: int
    missing_quantity: int
    percent_exact: float
    percent_buildable: float
    allocations: tuple[MatchAllocation, ...]
    missing: tuple[MissingRequirement, ...]


def match_set(
    target: EffectiveSet,
    inventory: InventorySnapshot,
    equivalents: Mapping[str, frozenset[str]],
) -> MatchResult:
    requirements = _normalize_requirements(target.parts)
    if not requirements:
        raise ValueError("Target must contain at least one non-spare part.")

    available = _available_quantities(inventory)
    allocations: list[MatchAllocation] = []
    missing: list[MissingRequirement] = []
    exact_quantity = 0
    color_substitution_quantity = 0
    equivalence_substitution_quantity = 0

    for required in requirements:
        remaining = required.quantity
        passes = (
            [(required.part_num, required.color_id, "exact")],
            _same_part_other_colors(required, available),
            _equivalent_exact_color(required, equivalents),
            _equivalent_other_colors(required, available, equivalents),
        )
        for candidates in passes:
            for supplied_part_num, supplied_color_id, kind in candidates:
                if remaining == 0:
                    break
                supplied_key = (supplied_part_num, supplied_color_id)
                quantity = min(remaining, available.get(supplied_key, 0))
                if quantity == 0:
                    continue
                available[supplied_key] -= quantity
                remaining -= quantity
                allocations.append(
                    MatchAllocation(
                        required.part_num,
                        required.color_id,
                        supplied_part_num,
                        supplied_color_id,
                        quantity,
                        kind,
                    )
                )
                if kind == "exact":
                    exact_quantity += quantity
                elif kind == "color":
                    color_substitution_quantity += quantity
                else:
                    equivalence_substitution_quantity += quantity
        if remaining:
            missing.append(
                MissingRequirement(
                    required.part_num,
                    required.part_name,
                    required.color_id,
                    required.color_name,
                    remaining,
                )
            )

    required_quantity = sum(required.quantity for required in requirements)
    missing_quantity = sum(value.quantity for value in missing)
    if missing_quantity:
        status: Literal["exact", "substitution", "missing"] = "missing"
    elif color_substitution_quantity or equivalence_substitution_quantity:
        status = "substitution"
    else:
        status = "exact"
    return MatchResult(
        status=status,
        required_quantity=required_quantity,
        exact_quantity=exact_quantity,
        color_substitution_quantity=color_substitution_quantity,
        equivalence_substitution_quantity=equivalence_substitution_quantity,
        missing_quantity=missing_quantity,
        percent_exact=round(exact_quantity / required_quantity * 100, 1),
        percent_buildable=round((required_quantity - missing_quantity) / required_quantity * 100, 1),
        allocations=tuple(allocations),
        missing=tuple(missing),
    )


def _available_quantities(inventory: InventorySnapshot) -> dict[tuple[str, int], int]:
    quantities: dict[tuple[str, int], int] = defaultdict(int)
    for item in inventory.items:
        quantities[(item.part_num, item.color_id)] += item.quantity
    return dict(quantities)


def _normalize_requirements(parts: list[EffectivePartRow]) -> list[EffectivePartRow]:
    quantities: dict[tuple[str, int], int] = defaultdict(int)
    details: dict[tuple[str, int], EffectivePartRow] = {}
    for part in parts:
        if part.is_spare:
            continue
        key = (part.part_num, part.color_id)
        quantities[key] += part.quantity
        details.setdefault(key, part)
    return [
        EffectivePartRow(
            part_num=part_num,
            part_name=details[(part_num, color_id)].part_name,
            color_id=color_id,
            color_name=details[(part_num, color_id)].color_name,
            rgb_hex=details[(part_num, color_id)].rgb_hex,
            quantity=quantity,
            is_spare=False,
            source_kind=details[(part_num, color_id)].source_kind,
            image_url=details[(part_num, color_id)].image_url,
        )
        for (part_num, color_id), quantity in sorted(quantities.items())
    ]


def _same_part_other_colors(
    required: EffectivePartRow, available: Mapping[tuple[str, int], int]
) -> list[tuple[str, int, Literal["color"]]]:
    return [
        (part_num, color_id, "color")
        for (part_num, color_id), quantity in sorted(
            available.items(), key=lambda value: (-value[1], value[0][1])
        )
        if part_num == required.part_num and color_id != required.color_id and quantity > 0
    ]


def _equivalent_exact_color(
    required: EffectivePartRow, equivalents: Mapping[str, frozenset[str]]
) -> list[tuple[str, int, Literal["equivalent_exact_color"]]]:
    return [
        (part_num, required.color_id, "equivalent_exact_color")
        for part_num in sorted(equivalents.get(required.part_num, frozenset()))
        if part_num != required.part_num
    ]


def _equivalent_other_colors(
    required: EffectivePartRow,
    available: Mapping[tuple[str, int], int],
    equivalents: Mapping[str, frozenset[str]],
) -> list[tuple[str, int, Literal["equivalent_color"]]]:
    equivalent_parts = equivalents.get(required.part_num, frozenset())
    return [
        (part_num, color_id, "equivalent_color")
        for (part_num, color_id), quantity in sorted(
            available.items(), key=lambda value: (-value[1], value[0][0], value[0][1])
        )
        if (
            part_num in equivalent_parts
            and part_num != required.part_num
            and color_id != required.color_id
            and quantity > 0
        )
    ]
