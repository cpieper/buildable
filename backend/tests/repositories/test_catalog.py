from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import Base, create_db_engine
from app.main import create_app
from app.models import (
    CatalogColor,
    CatalogPart,
    CatalogSet,
    CatalogSetOverride,
    CatalogSetPart,
    CatalogSetPartOverride,
    OwnedSet,
    OwnedSetMissingPart,
)
from app.repositories.catalog import CatalogRepository


def seed_catalog_set(
    session: Session,
    *,
    set_num: str,
    name: str,
    theme_name: str | None = "Town",
) -> None:
    session.add(
        CatalogSet(
            set_num=set_num,
            name=name,
            year=1990,
            theme_id=1,
            theme_name=theme_name,
            num_parts=2,
            image_url=None,
            external_url=f"https://example.test/sets/{set_num}",
            instructions_url=None,
            source="test",
            source_updated_at=None,
            imported_at=datetime.now(UTC),
        )
    )


def seed_catalog_part_row(
    session: Session,
    set_num: str,
    part_num: str,
    color_id: int,
    *,
    quantity: int,
    part_name: str = "Brick 2 x 4",
    color_name: str = "Red",
    rgb_hex: str = "C91A09",
    is_spare: bool = False,
    source_kind: str = "part",
    source_id: str = "1",
) -> None:
    seed_catalog_part_and_color(
        session,
        part_num=part_num,
        color_id=color_id,
        part_name=part_name,
        color_name=color_name,
        rgb_hex=rgb_hex,
    )
    session.add(
        CatalogSetPart(
            set_num=set_num,
            part_num=part_num,
            color_id=color_id,
            quantity=quantity,
            is_spare=is_spare,
            source_kind=source_kind,
            source_id=source_id,
        )
    )


def seed_catalog_part_and_color(
    session: Session,
    *,
    part_num: str = "3001",
    color_id: int = 5,
    part_name: str = "Brick 2 x 4",
    color_name: str = "Red",
    rgb_hex: str = "C91A09",
) -> None:
    if session.get(CatalogPart, part_num) is None:
        session.add(
            CatalogPart(
                part_num=part_num,
                name=part_name,
                category_name="Bricks",
                image_url=f"https://example.test/parts/{part_num}.png",
                external_ids_json="{}",
            )
        )
    if session.get(CatalogColor, color_id) is None:
        session.add(
            CatalogColor(
                id=color_id,
                name=color_name,
                rgb_hex=rgb_hex,
                external_ids_json="{}",
            )
        )
    session.flush()


def test_effective_set_applies_metadata_and_inventory_overrides(
    session: Session,
) -> None:
    seed_catalog_set(session, set_num="1234-1", name="Original")
    seed_catalog_part_row(session, "1234-1", "3001", 5, quantity=2)
    session.add(CatalogSetOverride(set_num="1234-1", name="Corrected"))
    session.add(
        CatalogSetPartOverride(
            set_num="1234-1",
            part_num="3001",
            color_id=5,
            operation="upsert",
            quantity=3,
            is_spare=False,
        )
    )
    session.commit()

    result = CatalogRepository(session).get_effective_set("1234-1")

    assert result is not None
    assert result.name == "Corrected"
    assert result.has_local_overrides is True
    assert [(row.part_num, row.color_id, row.quantity) for row in result.parts] == [
        ("3001", 5, 3)
    ]
    assert result.parts[0].source_kind == "override"
    assert session.get(CatalogSet, "1234-1").name == "Original"
    assert session.get(CatalogSetPart, 1).quantity == 2


def test_delete_override_hides_imported_inventory_row(session: Session) -> None:
    seed_catalog_set(session, set_num="1234-1", name="Original")
    seed_catalog_part_row(session, "1234-1", "3001", 5, quantity=2)
    session.add(
        CatalogSetPartOverride(
            set_num="1234-1",
            part_num="3001",
            color_id=5,
            operation="delete",
            quantity=None,
            is_spare=False,
        )
    )
    session.commit()

    result = CatalogRepository(session).get_effective_set("1234-1")

    assert result is not None
    assert result.parts == []


def test_effective_set_aggregates_sources_and_sorts_by_part_and_color(
    session: Session,
) -> None:
    seed_catalog_set(session, set_num="1234-1", name="Original")
    seed_catalog_part_row(
        session,
        "1234-1",
        "3002",
        2,
        quantity=1,
        part_name="Brick 2 x 3",
        color_name="Blue",
    )
    seed_catalog_part_row(
        session,
        "1234-1",
        "3001",
        5,
        quantity=2,
        source_id="first",
    )
    seed_catalog_part_row(
        session,
        "1234-1",
        "3001",
        5,
        quantity=4,
        source_id="second",
    )
    session.commit()

    result = CatalogRepository(session).get_effective_set("1234-1")

    assert result is not None
    assert [
        (row.part_name, row.color_name, row.quantity, row.source_kind)
        for row in result.parts
    ] == [
        ("Brick 2 x 3", "Blue", 1, "part"),
        ("Brick 2 x 4", "Red", 6, "part"),
    ]


def test_spare_classification_change_uses_delete_and_upsert(session: Session) -> None:
    seed_catalog_set(session, set_num="1234-1", name="Original")
    seed_catalog_part_row(session, "1234-1", "3001", 5, quantity=2, is_spare=False)
    session.add_all(
        [
            CatalogSetPartOverride(
                set_num="1234-1",
                part_num="3001",
                color_id=5,
                operation="delete",
                quantity=None,
                is_spare=False,
            ),
            CatalogSetPartOverride(
                set_num="1234-1",
                part_num="3001",
                color_id=5,
                operation="upsert",
                quantity=2,
                is_spare=True,
            ),
        ]
    )
    session.commit()

    result = CatalogRepository(session).get_effective_set("1234-1")

    assert result is not None
    assert [(row.quantity, row.is_spare) for row in result.parts] == [(2, True)]


def test_search_sets_uses_effective_metadata_and_limit(session: Session) -> None:
    seed_catalog_set(session, set_num="1000-1", name="Imported Name")
    seed_catalog_set(session, set_num="2000-1", name="Castle Gate")
    session.add(
        CatalogSetOverride(
            set_num="1000-1", name="Castle Courtyard", theme_name="Castle"
        )
    )
    session.commit()

    results = CatalogRepository(session).search_sets("castle", limit=1)

    assert [(result.set_num, result.name) for result in results] == [
        ("1000-1", "Castle Courtyard")
    ]
    assert CatalogRepository(session).search_sets("Imported Name", limit=10) == []
    assert CatalogRepository(session).search_sets("1000-1", limit=10)[0].name == (
        "Castle Courtyard"
    )


def test_schema_rejects_nonpositive_catalog_set_part_quantity(
    session: Session,
) -> None:
    seed_catalog_set(session, set_num="1234-1", name="Original")
    seed_catalog_part_and_color(session)
    session.commit()
    session.add(
        CatalogSetPart(
            set_num="1234-1",
            part_num="3001",
            color_id=5,
            quantity=0,
            is_spare=False,
            source_kind="part",
            source_id="invalid",
        )
    )

    _assert_check_constraint(session, "ck_catalog_set_parts_quantity")


def test_schema_rejects_nonpositive_owned_set_quantity(session: Session) -> None:
    seed_catalog_set(session, set_num="1234-1", name="Original")
    session.commit()
    session.add(
        OwnedSet(
            set_num="1234-1",
            quantity=0,
            completeness="complete",
            unknown_missing_count=0,
        )
    )

    _assert_check_constraint(session, "ck_owned_sets_quantity")


def test_schema_rejects_invalid_owned_set_completeness(session: Session) -> None:
    seed_catalog_set(session, set_num="1234-1", name="Original")
    session.commit()
    session.add(
        OwnedSet(
            set_num="1234-1",
            quantity=1,
            completeness="unknown",
            unknown_missing_count=0,
        )
    )

    _assert_check_constraint(session, "ck_owned_sets_completeness")


def test_schema_rejects_nonpositive_missing_part_quantity(
    session: Session,
) -> None:
    seed_catalog_set(session, set_num="1234-1", name="Original")
    seed_catalog_part_and_color(session)
    owned_set = OwnedSet(
        set_num="1234-1",
        quantity=1,
        completeness="complete",
        unknown_missing_count=0,
    )
    session.add(owned_set)
    session.commit()
    session.add(
        OwnedSetMissingPart(
            owned_set_id=owned_set.id,
            part_num="3001",
            color_id=5,
            quantity=0,
        )
    )

    _assert_check_constraint(session, "ck_owned_set_missing_parts_quantity")


def test_schema_rejects_invalid_inventory_override_operation(
    session: Session,
) -> None:
    seed_catalog_set(session, set_num="1234-1", name="Original")
    seed_catalog_part_and_color(session)
    session.commit()
    session.add(
        CatalogSetPartOverride(
            set_num="1234-1",
            part_num="3001",
            color_id=5,
            operation="replace",
            quantity=1,
            is_spare=False,
        )
    )

    _assert_check_constraint(session, "ck_catalog_set_part_overrides_operation")


def test_schema_rejects_nonpositive_upsert_override_quantity(
    session: Session,
) -> None:
    seed_catalog_set(session, set_num="1234-1", name="Original")
    seed_catalog_part_and_color(session)
    session.commit()
    session.add(
        CatalogSetPartOverride(
            set_num="1234-1",
            part_num="3001",
            color_id=5,
            operation="upsert",
            quantity=0,
            is_spare=False,
        )
    )

    _assert_check_constraint(
        session, "ck_catalog_set_part_overrides_operation_quantity"
    )


def test_schema_rejects_quantity_for_delete_override(session: Session) -> None:
    seed_catalog_set(session, set_num="1234-1", name="Original")
    seed_catalog_part_and_color(session)
    session.commit()
    session.add(
        CatalogSetPartOverride(
            set_num="1234-1",
            part_num="3001",
            color_id=5,
            operation="delete",
            quantity=1,
            is_spare=False,
        )
    )

    _assert_check_constraint(
        session, "ck_catalog_set_part_overrides_operation_quantity"
    )


def _assert_check_constraint(session: Session, constraint_name: str) -> None:
    with pytest.raises(IntegrityError) as error:
        session.commit()

    assert str(error.value.orig) == f"CHECK constraint failed: {constraint_name}"


def test_sqlite_connections_enable_required_pragmas(engine: Engine) -> None:
    with engine.connect() as connection:
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
        busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()

    assert foreign_keys == 1
    assert journal_mode == "wal"
    assert busy_timeout == 5_000


def test_app_startup_creates_data_directory_and_upgrades_schema(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "nested" / "data"
    database_path = data_dir / "app.db"
    settings = Settings(
        data_dir=data_dir,
        database_url=f"sqlite:///{database_path}",
    )

    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert data_dir.is_dir()
    assert database_path.is_file()


def test_alembic_upgrade_creates_missing_sqlite_parent_directory(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "missing" / "migration.db"
    config = Config(Path(__file__).resolve().parents[2] / "alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    assert database_path.is_file()
    migration_engine = create_engine(f"sqlite:///{database_path}")
    try:
        with migration_engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        migration_engine.dispose()
    assert revision == "0001_initial_schema"


def test_create_all_and_alembic_have_identical_server_defaults(
    tmp_path: Path,
) -> None:
    create_all_engine = create_db_engine(f"sqlite:///{tmp_path / 'create-all.db'}")
    Base.metadata.create_all(create_all_engine)

    migration_path = tmp_path / "migration.db"
    config = Config(Path(__file__).resolve().parents[2] / "alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{migration_path}")
    command.upgrade(config, "head")
    migration_engine = create_engine(f"sqlite:///{migration_path}")

    expected = {
        ("app_settings", "secret"): "0",
        ("app_settings", "updated_at"): "CURRENT_TIMESTAMP",
        ("catalog_colors", "external_ids_json"): "'{}'",
        ("catalog_parts", "external_ids_json"): "'{}'",
        ("catalog_set_overrides", "updated_at"): "CURRENT_TIMESTAMP",
        ("catalog_set_part_overrides", "is_spare"): "0",
        ("catalog_set_part_overrides", "updated_at"): "CURRENT_TIMESTAMP",
        ("catalog_set_parts", "is_spare"): "0",
        ("catalog_sets", "imported_at"): "CURRENT_TIMESTAMP",
        ("equivalence_groups", "created_at"): "CURRENT_TIMESTAMP",
        ("equivalence_groups", "updated_at"): "CURRENT_TIMESTAMP",
        ("owned_sets", "added_at"): "CURRENT_TIMESTAMP",
        ("owned_sets", "completeness"): "'complete'",
        ("owned_sets", "quantity"): "1",
        ("owned_sets", "unknown_missing_count"): "0",
        ("owned_sets", "updated_at"): "CURRENT_TIMESTAMP",
        ("sync_runs", "started_at"): "CURRENT_TIMESTAMP",
    }

    try:
        assert _server_defaults(create_all_engine) == expected
        assert _server_defaults(migration_engine) == expected
    finally:
        create_all_engine.dispose()
        migration_engine.dispose()


def test_injected_session_factory_skips_startup_migration(
    tmp_path: Path,
    session_factory: sessionmaker[Session],
) -> None:
    data_dir = tmp_path / "must-not-be-created"
    settings = Settings(
        data_dir=data_dir,
        database_url=f"sqlite:///{data_dir / 'unused.db'}",
    )

    with TestClient(
        create_app(settings=settings, session_factory=session_factory)
    ) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert not data_dir.exists()


def _server_defaults(engine: Engine) -> dict[tuple[str, str], str]:
    inspector = inspect(engine)
    return {
        (table_name, column["name"]): column["default"]
        for table_name in inspector.get_table_names()
        for column in inspector.get_columns(table_name)
        if column["default"] is not None
    }
