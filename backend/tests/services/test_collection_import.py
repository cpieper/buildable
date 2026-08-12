from io import BytesIO

from sqlalchemy.orm import Session

from app.models import OwnedSet
from app.repositories.catalog import CatalogRepository
from app.services.collection_import import import_rebrickable_collection_csv
from app.services.rebrickable import ImportedPart, ImportedSet


def test_collection_csv_import_fetches_missing_catalog_sets_before_adding_owned_set(
    session: Session,
) -> None:
    """Skipping uncached CSV rows makes imports look broken for normal exports."""
    looked_up: list[str] = []

    def lookup(set_num: str) -> ImportedSet:
        looked_up.append(set_num)
        return ImportedSet(
            set_num=set_num,
            name="Retro Food Truck",
            year=2026,
            theme_id=603,
            num_parts=42,
            image_url="https://example.test/food-truck.png",
            external_url=f"https://example.test/sets/{set_num}",
            parts=[
                ImportedPart(
                    part_num="3001",
                    part_name="Brick 2 x 4",
                    part_image_url="https://example.test/brick.png",
                    color_id=5,
                    color_name="Red",
                    rgb_hex="C91A09",
                    quantity=2,
                    is_spare=False,
                    source_id="101",
                )
            ],
        )

    summary = import_rebrickable_collection_csv(
        BytesIO(b"Set Number,Quantity,Inventory Ver\n60452-1,2,1\n"),
        session,
        lookup_missing=lookup,
    )

    assert looked_up == ["60452-1"]
    assert summary.rows_imported == 1
    assert summary.quantity_added == 2
    assert summary.rows_skipped == 0
    assert summary.missing_set_nums == []
    assert CatalogRepository(session).get_effective_set("60452-1") is not None
    owned = session.get(OwnedSet, 1)
    assert owned is not None
    assert (owned.set_num, owned.quantity) == ("60452-1", 2)
