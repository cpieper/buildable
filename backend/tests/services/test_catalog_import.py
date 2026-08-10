from collections.abc import Callable, Iterator
from datetime import UTC
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pydantic import ValidationError
from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    CatalogColor,
    CatalogPart,
    CatalogSet,
    CatalogSetOverride,
    CatalogSetPart,
    CatalogSetPartOverride,
    OwnedSet,
    SyncRun,
)
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


@pytest.fixture
def zip_builder() -> Callable[..., BinaryIO]:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "rebrickable-small"
    valid_archive = fixture_dir / "valid-catalog.zip"

    def build(
        replacements: dict[str, str] | None = None,
        *,
        remove: set[str] | None = None,
    ) -> BinaryIO:
        replacement_bytes = {
            name: content.encode() for name, content in (replacements or {}).items()
        }
        removed = remove or set()
        result = BytesIO()
        with ZipFile(valid_archive) as source, ZipFile(
            result, "w", compression=ZIP_DEFLATED
        ) as target:
            for name in source.namelist():
                if name in removed:
                    continue
                target.writestr(name, replacement_bytes.get(name, source.read(name)))
        result.seek(0)
        return result

    return build


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
        set_num="9000-1",
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

    assert result.set_num == "9000-1"
    assert result.num_parts == 3
    assert part_tuples(result) == {("3001", 5, 3, False, "manual")}
    stored = session.get_one(CatalogSet, "9000-1")
    assert stored.source == "manual"
    assert stored.image_url == "https://example.test/custom.png"
    row = session.scalar(
        select(CatalogSetPart).where(CatalogSetPart.set_num == "9000-1")
    )
    assert row is not None
    assert row.source_id == "9000-1"


def test_zip_replacement_preserves_manual_sets(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    import_manual_set(
        ManualCatalogSetCreate(
            set_num="9000-1",
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

    assert CatalogRepository(session).get_effective_set("9000-1") is not None
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
    with Session(bind=session.get_bind()) as independent_session:
        assert independent_session.get(AppSetting, "caller-owned") is None

    session.rollback()
    assert session.get(AppSetting, "caller-owned") is None
    with Session(bind=session.get_bind()) as independent_session:
        assert independent_session.get(AppSetting, "caller-owned") is None
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


@pytest.mark.parametrize("set_num", ["MOC-42", "custom", "1234-0", "123A-1"])
def test_manual_schema_rejects_non_official_set_numbers(set_num: str) -> None:
    with pytest.raises(ValidationError):
        ManualCatalogSetCreate(
            set_num=set_num,
            name="Not an official set",
            parts=[
                ManualCatalogPart(
                    part_num="3001",
                    part_name="Brick 2 x 4",
                    color_id=5,
                    color_name="Red",
                    rgb_hex="C91A09",
                    quantity=1,
                )
            ],
        )


@pytest.mark.parametrize("set_num", ["0-1", "0007-2"])
def test_manual_schema_accepts_legacy_zero_prefixed_design_ids(set_num: str) -> None:
    payload = ManualCatalogSetCreate(
        set_num=set_num,
        name="Legacy official set",
        parts=[
            ManualCatalogPart(
                part_num="3001",
                part_name="Brick 2 x 4",
                color_id=5,
                color_name="Red",
                rgb_hex="C91A09",
                quantity=1,
            )
        ],
    )

    assert payload.set_num == set_num


def test_minifig_expansion_multiplies_highest_version_inventory(
    session: Session, zip_builder: Callable[..., BinaryIO]
) -> None:
    archive = zip_builder(
        {
            "inventories.csv": (
                "id,version,set_num\n"
                "100,1,1234-1\n"
                "101,2,1234-1\n"
                "200,1,fig-0001\n"
                "201,2,fig-0001\n"
            ),
            "inventory_parts.csv": (
                "inventory_id,part_num,color_id,quantity,is_spare,img_url\n"
                "101,3001,5,2,f,\n"
                "200,3626,14,99,f,\n"
                "201,3626,14,3,f,\n"
            ),
            "inventory_minifigs.csv": (
                "inventory_id,fig_num,quantity\n101,fig-0001,2\n"
            ),
        }
    )

    import_rebrickable_zip(archive, session)

    result = CatalogRepository(session).get_effective_set("1234-1")
    assert ("3626", 14, 6, False, "minifig") in part_tuples(result)
    assert all(part.quantity != 198 for part in result.parts if part.part_num == "3626")


@pytest.mark.parametrize(
    ("replacements", "removed", "diagnostic"),
    [
        ({}, {"colors.csv"}, "colors.csv: missing required ZIP member"),
        (
            {"colors.csv": "id,name,is_trans\n5,Red,f\n"},
            set(),
            "colors.csv:1: missing required columns: rgb",
        ),
        (
            {"colors.csv": "id,id,name,rgb,is_trans\n5,5,Red,C91A09,f\n"},
            set(),
            "colors.csv:1: duplicate CSV header: id",
        ),
    ],
)
def test_zip_import_rejects_missing_members_and_invalid_headers(
    replacements: dict[str, str],
    removed: set[str],
    diagnostic: str,
    session: Session,
    zip_builder: Callable[..., BinaryIO],
) -> None:
    with pytest.raises(CatalogImportError, match=diagnostic):
        import_rebrickable_zip(
            zip_builder(replacements, remove=removed),
            session,
        )

    assert session.scalar(select(func.count()).select_from(CatalogSet)) == 0
    assert diagnostic in (session.scalar(select(SyncRun.error)) or "")


@pytest.mark.parametrize(
    ("member", "content", "diagnostic"),
    [
        (
            "sets.csv",
            (
                "set_num,name,year,theme_id,num_parts,img_url\n"
                "1234-1,Castle Cart,2024,10,4,\n"
                "1234-1,Duplicate,2024,10,4,\n"
            ),
            "sets.csv:3: duplicate identity '1234-1'",
        ),
        (
            "parts.csv",
            (
                "part_num,name,part_cat_id,part_material\n"
                "3001,Brick 2 x 4,999,Plastic\n"
                "6141,Plate Round 1 x 1,1,Plastic\n"
                "3626,Minifig Head,2,Plastic\n"
            ),
            "parts.csv:2: unknown part_cat_id 999",
        ),
        (
            "inventory_minifigs.csv",
            "inventory_id,fig_num,quantity\n101,fig-missing,1\n",
            "inventory_minifigs.csv:2: unknown fig_num 'fig-missing'",
        ),
    ],
)
def test_zip_import_rejects_representative_duplicate_and_reference_errors(
    member: str,
    content: str,
    diagnostic: str,
    session: Session,
    zip_builder: Callable[..., BinaryIO],
) -> None:
    with pytest.raises(CatalogImportError) as captured:
        import_rebrickable_zip(zip_builder({member: content}), session)

    assert str(captured.value) == diagnostic
    assert session.scalar(select(func.count()).select_from(CatalogSet)) == 0


def test_zip_import_upserts_shared_dimensions_without_changing_manual_inventory(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    import_manual_set(
        ManualCatalogSetCreate(
            set_num="9000-1",
            name="Official Manual Entry",
            parts=[
                ManualCatalogPart(
                    part_num="3001",
                    part_name="Locally supplied name",
                    color_id=5,
                    color_name="Locally supplied color",
                    rgb_hex="000000",
                    quantity=7,
                )
            ],
        ),
        session,
    )

    import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)

    manual = CatalogRepository(session).get_effective_set("9000-1")
    assert manual is not None
    assert manual.name == "Official Manual Entry"
    assert [(part.part_num, part.quantity) for part in manual.parts] == [("3001", 7)]
    assert manual.parts[0].part_name == "Brick 2 x 4"
    assert manual.parts[0].color_name == "Red"
    assert manual.parts[0].rgb_hex == "C91A09"


def test_zip_import_retains_stale_unreferenced_dimensions(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    session.add_all(
        [
            CatalogPart(
                part_num="stale-part",
                name="Retained Part",
                category_name=None,
                image_url=None,
                external_ids_json="{}",
            ),
            CatalogColor(
                id=999,
                name="Retained Color",
                rgb_hex="123ABC",
                external_ids_json="{}",
            ),
        ]
    )
    session.commit()

    import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)

    assert session.get_one(CatalogPart, "stale-part").name == "Retained Part"
    assert session.get_one(CatalogColor, 999).name == "Retained Color"


def _replacement_zip(zip_builder: Callable[..., BinaryIO]) -> BinaryIO:
    return zip_builder(
        {
            "sets.csv": (
                "set_num,name,year,theme_id,num_parts,img_url\n"
                "5678-1,Replacement Set,2025,10,2,\n"
            ),
            "inventories.csv": (
                "id,version,set_num\n300,1,5678-1\n200,1,fig-0001\n"
            ),
            "inventory_parts.csv": (
                "inventory_id,part_num,color_id,quantity,is_spare,img_url\n"
                "300,3001,5,1,f,\n200,3626,14,1,f,\n"
            ),
            "inventory_minifigs.csv": (
                "inventory_id,fig_num,quantity\n300,fig-0001,1\n"
            ),
        }
    )


@pytest.mark.parametrize("reference_kind", ["set_override", "part_override", "owned_set"])
def test_zip_replacement_rejects_stale_sets_with_personal_references(
    reference_kind: str,
    session: Session,
    zip_fixture: Callable[[str], BinaryIO],
    zip_builder: Callable[..., BinaryIO],
) -> None:
    import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)
    if reference_kind == "set_override":
        session.add(CatalogSetOverride(set_num="1234-1", name="Keep Me"))
    elif reference_kind == "part_override":
        session.add(
            CatalogSetPartOverride(
                set_num="1234-1",
                part_num="3001",
                color_id=5,
                is_spare=False,
                operation="upsert",
                quantity=8,
            )
        )
    else:
        session.add(OwnedSet(set_num="1234-1", quantity=1))
    session.commit()

    with pytest.raises(CatalogImportError, match="cannot remove stale set"):
        import_rebrickable_zip(_replacement_zip(zip_builder), session)

    assert CatalogRepository(session).get_effective_set("1234-1") is not None
    assert CatalogRepository(session).get_effective_set("5678-1") is None


def test_zip_import_rejects_pending_orm_writes_without_rolling_them_back(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    setting = AppSetting(key="pending-orm", value="keep-me", secret=False)
    session.add(setting)

    with pytest.raises(CatalogImportError, match="without pending changes"):
        import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)

    assert setting in session.new
    assert session.scalar(select(func.count()).select_from(CatalogSet)) == 0


def test_zip_import_allows_clean_read_only_autobegin(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    assert session.scalar(select(func.count()).select_from(CatalogSet)) == 0

    summary = import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)

    assert summary.sets == 1
    assert session.get_one(CatalogSet, "1234-1").name == "Castle Cart"


def test_database_write_failure_rolls_back_and_records_failed_sync(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    catalog_models = (CatalogSet, CatalogPart, CatalogColor, CatalogSetPart)
    before_counts = {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        for model in catalog_models
    }
    assert before_counts == {
        "catalog_sets": 0,
        "catalog_parts": 0,
        "catalog_colors": 0,
        "catalog_set_parts": 0,
    }
    session.rollback()
    session.execute(
        text(
            "CREATE TRIGGER fail_catalog_write BEFORE INSERT ON catalog_sets "
            "BEGIN SELECT missing_catalog_function(); END"
        )
    )
    session.commit()

    with pytest.raises(CatalogImportError, match="missing_catalog_function"):
        import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)

    after_counts = {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        for model in catalog_models
    }
    assert after_counts == before_counts
    runs = session.scalars(select(SyncRun)).all()
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert "missing_catalog_function" in (runs[0].error or "")


def test_failed_sync_write_reports_both_catalog_and_recording_errors(
    session: Session, zip_fixture: Callable[[str], BinaryIO]
) -> None:
    session.execute(
        text(
            "CREATE TRIGGER fail_catalog_write BEFORE INSERT ON catalog_sets "
            "BEGIN SELECT missing_catalog_function(); END"
        )
    )
    session.execute(
        text(
            "CREATE TRIGGER fail_sync_write BEFORE INSERT ON sync_runs "
            "BEGIN SELECT missing_sync_function(); END"
        )
    )
    session.commit()

    with pytest.raises(CatalogImportError) as captured:
        import_rebrickable_zip(zip_fixture("valid-catalog.zip"), session)

    assert "missing_catalog_function" in str(captured.value)
    assert "missing_sync_function" in str(captured.value)
    assert session.scalar(select(func.count()).select_from(CatalogSet)) == 0
    assert session.scalar(select(func.count()).select_from(SyncRun)) == 0
