from collections.abc import Callable, Iterator
from datetime import UTC
from pathlib import Path
from typing import BinaryIO

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.models import AppSetting, CatalogSet, CatalogSetPart, SyncRun
from app.repositories.catalog import CatalogRepository
from app.schemas.catalog import ManualCatalogPart, ManualCatalogSetCreate
from app.services.catalog_import import (
    CatalogImportError,
    import_manual_set,
    import_rebrickable_zip,
)


@pytest.fixture
def zip_fixture() -> Iterator[Callable[[str], BinaryIO]]:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "rebrickable-small"
    opened: list[BinaryIO] = []

    def open_fixture(name: str) -> BinaryIO:
        stream = (fixture_dir / name).open("rb")
        opened.append(stream)
        return stream

    yield open_fixture
    for stream in opened:
        stream.close()


def part_tuples(result: object) -> set[tuple[str, int, int, bool, str]]:
    assert result is not None
    return {
        (
            part.part_num,
            part.color_id,
            part.quantity,
            part.is_spare,
            part.source_kind,
        )
        for part in result.parts
    }


def test_zip_import_preserves_color_and_expands_minifig_parts(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    summary = import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)
    result = CatalogRepository(session).get_effective_set("1234-1")

    assert summary.sets == 1
    assert summary.parts == 3
    assert summary.colors == 3
    assert summary.warnings == []
    assert summary.sync_run_id > 0
    assert summary.started_at.tzinfo == UTC
    assert summary.completed_at.tzinfo == UTC
    assert summary.completed_at >= summary.started_at
    assert ("3001", 5, 2, False, "set") in part_tuples(result)
    assert ("3626", 14, 1, False, "minifig") in part_tuples(result)
    assert ("6141", 1, 1, True, "set") in part_tuples(result)

    rows = session.scalars(
        select(CatalogSetPart).order_by(CatalogSetPart.part_num)
    ).all()
    assert [
        (row.part_num, row.source_kind, row.source_id) for row in rows
    ] == [
        ("3001", "set", "101"),
        ("3626", "minifig", "fig-0001"),
        ("6141", "set", "101"),
    ]


def test_malformed_zip_rolls_back_every_catalog_change(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    with pytest.raises(CatalogImportError, match="inventory_parts.csv:2"):
        import_rebrickable_zip(zip_fixture("bad-quantity.zip"), session)

    assert session.scalar(select(func.count()).select_from(CatalogSet)) == 0
    failed_run = session.scalar(select(SyncRun))
    assert failed_run is not None
    assert failed_run.status == "failed"
    assert failed_run.completed_at is not None
    assert "inventory_parts.csv:2" in (failed_run.error or "")


@pytest.mark.parametrize(
    ("fixture_name", "diagnostic"),
    [
        ("duplicate-parts.zip", "inventory_parts.csv:3"),
        ("unknown-color.zip", "inventory_parts.csv:2"),
        ("unknown-theme-parent.zip", "themes.csv:2"),
        ("bad-minifig-count.zip", "minifigs.csv:2"),
    ],
)
def test_zip_import_rejects_duplicate_rows_and_unknown_references(
    fixture_name: str,
    diagnostic: str,
    session: Session,
    zip_fixture: Callable[[str], BinaryIO],
) -> None:
    with pytest.raises(CatalogImportError, match=diagnostic):
        import_rebrickable_zip(zip_fixture(fixture_name), session)

    assert session.scalar(select(func.count()).select_from(CatalogSet)) == 0


def test_failed_replacement_preserves_previous_cache(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)

    with pytest.raises(CatalogImportError):
        import_rebrickable_zip(zip_fixture("bad-quantity.zip"), session)

    result = CatalogRepository(session).get_effective_set("1234-1")
    assert result is not None
    assert result.name == "Castle Cart"
    assert ("3001", 5, 2, False, "set") in part_tuples(result)
    assert session.scalars(select(SyncRun).order_by(SyncRun.id)).all()[0].status == (
        "completed"
    )
    assert session.scalars(select(SyncRun).order_by(SyncRun.id)).all()[1].status == (
        "failed"
    )


def test_manual_import_creates_immutable_catalog_rows(session: Session) -> None:
    payload = ManualCatalogSetCreate(
        set_num="custom-1",
        name="My Build",
        year=2026,
        theme_name="Original",
        image_url="https://example.test/custom.png",
        parts=[
            ManualCatalogPart(
                part_num="3001",
                part_name="Brick 2 x 4",
                color_id=5,
                color_name="Red",
                rgb_hex="C91A09",
                quantity=3,
            )
        ],
    )

    result = import_manual_set(payload, session)

    assert result.set_num == "custom-1"
    assert result.num_parts == 3
    assert part_tuples(result) == {("3001", 5, 3, False, "manual")}
    stored = session.get_one(CatalogSet, "custom-1")
    assert stored.source == "manual"
    assert stored.image_url == "https://example.test/custom.png"
    row = session.scalar(
        select(CatalogSetPart).where(CatalogSetPart.set_num == "custom-1")
    )
    assert row is not None
    assert row.source_id == "custom-1"


def test_zip_replacement_preserves_manual_sets(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    import_manual_set(
        ManualCatalogSetCreate(
            set_num="custom-1",
            name="My Build",
            parts=[
                ManualCatalogPart(
                    part_num="custom-part",
                    part_name="Custom Part",
                    color_id=999,
                    color_name="Custom Color",
                    rgb_hex="123ABC",
                    quantity=1,
                )
            ],
        ),
        session,
    )

    import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)

    assert CatalogRepository(session).get_effective_set("custom-1") is not None
    assert CatalogRepository(session).get_effective_set("1234-1") is not None


def test_zip_import_rejects_core_dml_without_rolling_back_caller_work(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    session.execute(
        insert(AppSetting).values(key="caller-owned", value="keep-me", secret=False)
    )

    with pytest.raises(CatalogImportError, match="without pending changes"):
        import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)

    setting = session.get_one(AppSetting, "caller-owned")
    assert setting.value == "keep-me"
    assert session.scalar(select(func.count()).select_from(CatalogSet)) == 0


def test_zip_import_rejects_explicit_transaction_without_closing_it(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    with session.begin():
        with pytest.raises(CatalogImportError, match="without pending changes"):
            import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)
        session.add(AppSetting(key="still-active", value="yes", secret=False))

    assert session.get_one(AppSetting, "still-active").value == "yes"
    assert session.scalar(select(func.count()).select_from(CatalogSet)) == 0
