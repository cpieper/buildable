from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OwnedSet, OwnedSetMissingPart
from app.repositories.catalog import CatalogRepository


@dataclass(frozen=True)
class InventoryItem:
    part_num: str
    part_name: str
    color_id: int
    color_name: str
    rgb_hex: str
    quantity: int
    image_url: str | None
    source_set_nums: tuple[str, ...]


@dataclass(frozen=True)
class InventoryWarning:
    owned_set_id: int
    set_num: str
    set_name: str
    unknown_missing_count: int | None
    note: str | None


@dataclass(frozen=True)
class InventorySnapshot:
    items: tuple[InventoryItem, ...]
    warnings: tuple[InventoryWarning, ...]
    total_quantity: int

    def quantity(self, part_num: str, color_id: int) -> int:
        return next(
            (
                item.quantity
                for item in self.items
                if item.part_num == part_num and item.color_id == color_id
            ),
            0,
        )


def compute_inventory(session: Session) -> InventorySnapshot:
    repository = CatalogRepository(session)
    quantities: dict[tuple[str, int], int] = defaultdict(int)
    details: dict[tuple[str, int], tuple[str, str, str, str | None]] = {}
    sources: dict[tuple[str, int], set[str]] = defaultdict(set)
    warnings: list[InventoryWarning] = []
    owned_sets = session.scalars(select(OwnedSet).order_by(OwnedSet.id)).all()
    for owned in owned_sets:
        effective = repository.get_effective_set(owned.set_num)
        if effective is None:
            continue
        for part in effective.parts:
            key = (part.part_num, part.color_id)
            quantities[key] += part.quantity * owned.quantity
            details[key] = (
                part.part_name,
                part.color_name,
                part.rgb_hex,
                part.image_url,
            )
            sources[key].add(owned.set_num)
        if owned.unknown_missing_count or owned.unknown_missing_note:
            warnings.append(
                InventoryWarning(
                    owned.id,
                    effective.set_num,
                    effective.name,
                    owned.unknown_missing_count,
                    owned.unknown_missing_note,
                )
            )

    missing_rows = session.scalars(
        select(OwnedSetMissingPart).order_by(OwnedSetMissingPart.id)
    ).all()
    owned_by_id = {owned.id: owned for owned in owned_sets}
    for missing in missing_rows:
        owned = owned_by_id.get(missing.owned_set_id)
        if owned is None:
            continue
        key = (missing.part_num, missing.color_id)
        available = quantities[key]
        quantities[key] = max(0, available - missing.quantity)
        effective = repository.get_effective_set(owned.set_num)
        if effective is not None:
            expected = (
                sum(
                    part.quantity
                    for part in effective.parts
                    if part.part_num == missing.part_num
                    and part.color_id == missing.color_id
                )
                * owned.quantity
            )
            if missing.quantity > expected:
                warnings.append(
                    InventoryWarning(
                        owned.id,
                        effective.set_num,
                        effective.name,
                        None,
                        "Recorded missing quantity exceeds available expected quantity.",
                    )
                )

    items = tuple(
        InventoryItem(
            part_num=part_num,
            part_name=details[(part_num, color_id)][0],
            color_id=color_id,
            color_name=details[(part_num, color_id)][1],
            rgb_hex=details[(part_num, color_id)][2],
            quantity=quantity,
            image_url=details[(part_num, color_id)][3],
            source_set_nums=tuple(sorted(sources[(part_num, color_id)])),
        )
        for (part_num, color_id), quantity in sorted(
            quantities.items(),
            key=lambda item: (details[item[0]][0].casefold(), item[0]),
        )
        if quantity > 0
    )
    return InventorySnapshot(
        items, tuple(warnings), sum(item.quantity for item in items)
    )
