from sqlalchemy.orm import Session

from app.models import (
    CatalogColor,
    CatalogPart,
    CatalogSet,
    CatalogSetPart,
    OwnedSet,
    OwnedSetMissingPart,
)
from app.services.inventory import compute_inventory


def seed_set_with_parts(
    session: Session, set_num: str, parts: list[tuple[str, int, int, bool]]
) -> None:
    session.add(
        CatalogSet(set_num=set_num, name="Test Set", num_parts=0, source="test")
    )
    for part_num, color_id, quantity, is_spare in parts:
        if session.get(CatalogPart, part_num) is None:
            session.add(
                CatalogPart(
                    part_num=part_num, name=f"Part {part_num}", external_ids_json="{}"
                )
            )
        if session.get(CatalogColor, color_id) is None:
            session.add(
                CatalogColor(
                    id=color_id,
                    name=f"Color {color_id}",
                    rgb_hex="FFFFFF",
                    external_ids_json="{}",
                )
            )
        session.add(
            CatalogSetPart(
                set_num=set_num,
                part_num=part_num,
                color_id=color_id,
                quantity=quantity,
                is_spare=is_spare,
                source_kind="test",
                source_id=set_num,
            )
        )
    session.commit()


def test_inventory_expands_copies_includes_spares_and_subtracts_known_missing(
    session: Session,
) -> None:
    seed_set_with_parts(
        session, "1234-1", [("3001", 5, 2, False), ("6141", 1, 1, True)]
    )
    owned = OwnedSet(set_num="1234-1", quantity=2, completeness="incomplete")
    session.add(owned)
    session.commit()
    session.add(
        OwnedSetMissingPart(
            owned_set_id=owned.id, part_num="3001", color_id=5, quantity=1
        )
    )
    session.commit()

    snapshot = compute_inventory(session)

    assert snapshot.quantity("3001", 5) == 3
    assert snapshot.quantity("6141", 1) == 2


def test_unknown_missing_note_warns_without_changing_math(session: Session) -> None:
    seed_set_with_parts(session, "1234-1", [("3001", 5, 2, False)])
    session.add(
        OwnedSet(
            set_num="1234-1",
            quantity=1,
            completeness="incomplete",
            unknown_missing_count=3,
            unknown_missing_note="A few tiny pieces",
        )
    )
    session.commit()

    snapshot = compute_inventory(session)

    assert snapshot.quantity("3001", 5) == 2
    assert snapshot.warnings[0].set_num == "1234-1"
