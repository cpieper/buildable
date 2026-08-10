from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    CatalogColor,
    CatalogPart,
    CatalogSet,
    CatalogSetOverride,
    EquivalenceGroup,
    EquivalenceMember,
    OwnedSet,
    OwnedSetMissingPart,
)
from app.schemas.backup import BackupV1
from app.services.backup import BackupValidationError, export_backup, restore_backup


def seed_catalog(session: Session) -> None:
    session.add_all([
        CatalogSet(set_num="1000-1", name="One", num_parts=1, source="test"),
        CatalogSet(set_num="2000-1", name="Two", num_parts=1, source="test"),
        CatalogPart(part_num="3001", name="Brick", external_ids_json="{}"),
        CatalogColor(id=5, name="Red", rgb_hex="C91A09", external_ids_json="{}"),
    ])
    session.commit()


def seed_personal_data(session: Session) -> None:
    seed_catalog(session)
    first = OwnedSet(set_num="1000-1", quantity=2, completeness="incomplete", notes="shelf")
    second = OwnedSet(set_num="2000-1")
    session.add_all([first, second, CatalogSetOverride(set_num="1000-1", name="Local", reason="typo")])
    session.flush()
    session.add(OwnedSetMissingPart(owned_set_id=first.id, part_num="3001", color_id=5, quantity=1, note="lost"))
    group = EquivalenceGroup(name="Alternates", notes="ok")
    session.add(group)
    session.flush()
    session.add(EquivalenceMember(group_id=group.id, part_num="3001"))
    session.add(AppSetting(key="ui.default_sort", value="buildability", secret=False))
    session.commit()


def test_backup_round_trip_preserves_personal_data(session: Session) -> None:
    seed_personal_data(session)
    payload = export_backup(session).model_dump(mode="json")
    session.query(OwnedSet).delete()
    session.query(CatalogSetOverride).delete()
    session.query(EquivalenceMember).delete()
    session.query(EquivalenceGroup).delete()
    session.query(AppSetting).delete()
    session.commit()

    result = restore_backup(session, BackupV1.model_validate(payload), mode="replace")
    restored = export_backup(session).model_dump(mode="json")

    assert result.owned_sets == 2
    assert {key: value for key, value in restored.items() if key != "exported_at"} == {
        key: value for key, value in payload.items() if key != "exported_at"
    }


def test_backup_excludes_secrets(session: Session) -> None:
    session.add_all([
        AppSetting(key="auth.password_hash", value="hash", secret=True),
        AppSetting(key="rebrickable_api_key", value="secret", secret=True),
        AppSetting(key="ui.default_sort", value="buildability", secret=False),
    ])
    session.commit()

    serialized = export_backup(session).model_dump_json()

    assert "auth.password_hash" not in serialized
    assert "rebrickable_api_key" not in serialized
    assert "ui.default_sort" in serialized


def test_restore_rejects_unsupported_schema_and_dangling_dependencies_before_writes(session: Session) -> None:
    seed_catalog(session)
    unsupported = BackupV1.model_construct(schema_name="what2build.backup/v2")
    try:
        restore_backup(session, unsupported, mode="replace")
    except BackupValidationError as error:
        assert error.code == "unsupported_schema"
    else:
        raise AssertionError("unsupported schema was accepted")

    dangling = BackupV1.model_validate({"schema": "what2build.backup/v1", "exported_at": "2026-08-10T12:00:00Z", "owned_sets": [{"set_num": "missing-1", "quantity": 1, "completeness": "complete", "unknown_missing_count": 0, "unknown_missing_note": None, "notes": None, "missing_parts": []}], "missing_parts": [], "set_overrides": [], "set_part_overrides": [], "equivalence_groups": [], "settings": {}})
    try:
        restore_backup(session, dangling, mode="replace")
    except BackupValidationError as error:
        assert error.code == "missing_dependencies"
        assert error.dependencies["sets"] == ["missing-1"]
    else:
        raise AssertionError("dangling data was accepted")
    assert session.scalars(select(OwnedSet)).all() == []


@pytest.mark.parametrize(
    ("key", "mode", "existing_secret"),
    [
        (key, mode, existing_secret)
        for key in (
            "auth.password_hash",
            "auth.revision",
            "session_secret",
            "rebrickable_api_key",
        )
        for mode in ("replace", "merge")
        for existing_secret in (False, True)
    ],
)
def test_restore_rejects_reserved_secret_setting_keys_before_mutation(
    session: Session, key: str, mode: str, existing_secret: bool
) -> None:
    seed_catalog(session)
    session.add(OwnedSet(set_num="1000-1", notes="keep"))
    if existing_secret:
        session.add(AppSetting(key=key, value="existing", secret=True))
    session.commit()
    backup = BackupV1.model_validate({"schema": "what2build.backup/v1", "exported_at": "2026-08-10T12:00:00Z", "owned_sets": [], "missing_parts": [], "set_overrides": [], "set_part_overrides": [], "equivalence_groups": [], "settings": {key: "malicious"}})

    with pytest.raises(BackupValidationError, match="reserved") as captured:
        restore_backup(session, backup, mode=mode)

    assert captured.value.code == "reserved_setting_key"
    assert session.scalars(select(OwnedSet)).one().notes == "keep"
    stored = session.get(AppSetting, key)
    if existing_secret:
        assert stored is not None
        assert stored.value == "existing"
        assert stored.secret is True
    else:
        assert stored is None


def test_backup_schema_alias_serializes_exact_v1_wire_field(session: Session) -> None:
    payload = export_backup(session).model_dump(mode="json")

    assert payload["schema"] == "what2build.backup/v1"
    assert "schema_name" not in payload


@pytest.mark.parametrize("mode", ["replace", "merge"])
def test_restore_rejects_destination_secret_setting_key_before_mutation(
    session: Session, mode: str
) -> None:
    seed_catalog(session)
    session.add_all([
        OwnedSet(set_num="1000-1", notes="keep"),
        AppSetting(key="custom.secret", value="existing", secret=True),
    ])
    session.commit()
    backup = BackupV1.model_validate({"schema": "what2build.backup/v1", "exported_at": "2026-08-10T12:00:00Z", "owned_sets": [], "missing_parts": [], "set_overrides": [], "set_part_overrides": [], "equivalence_groups": [], "settings": {"custom.secret": "malicious"}})

    with pytest.raises(BackupValidationError, match="secret") as captured:
        restore_backup(session, backup, mode=mode)

    assert captured.value.code == "secret_setting_key"
    assert session.scalars(select(OwnedSet)).one().notes == "keep"
    assert session.get(AppSetting, "custom.secret").value == "existing"  # type: ignore[union-attr]


def test_merge_reports_conflicts_and_rejects_duplicate_natural_keys(session: Session) -> None:
    seed_catalog(session)
    session.add(OwnedSet(set_num="1000-1", quantity=1))
    session.commit()
    conflict = BackupV1.model_validate({"schema": "what2build.backup/v1", "exported_at": "2026-08-10T12:00:00Z", "owned_sets": [{"set_num": "1000-1", "quantity": 2, "completeness": "complete", "unknown_missing_count": 0, "unknown_missing_note": None, "notes": None, "missing_parts": []}], "missing_parts": [], "set_overrides": [], "set_part_overrides": [], "equivalence_groups": [], "settings": {}})
    summary = restore_backup(session, conflict, mode="merge")
    assert summary.conflicting == 1
    assert session.scalar(select(OwnedSet.quantity)) == 1

    duplicate = conflict.model_copy(update={"owned_sets": conflict.owned_sets * 2})
    try:
        restore_backup(session, duplicate, mode="merge")
    except BackupValidationError as error:
        assert error.code == "duplicate_natural_key"
    else:
        raise AssertionError("duplicate keys were accepted")


def test_backup_writer_refuses_existing_destination_and_creates_parents(
    tmp_path: Path, session: Session
) -> None:
    from app.services.backup import write_backup_json

    target = Path(str(tmp_path)) / "new" / "backup.json"
    write_backup_json(target, export_backup(session))
    assert target.is_file()
    try:
        write_backup_json(target, export_backup(session))
    except FileExistsError:
        pass
    else:
        raise AssertionError("writer overwrote an existing backup")


def test_cli_export_creates_file_once_and_reports_counts(
    tmp_path: Path,
    session_factory: object,
    monkeypatch: object,
    capsys: object,
) -> None:
    from app import cli

    monkeypatch.setattr(cli, "SessionFactory", session_factory)  # type: ignore[attr-defined]
    target = tmp_path / "nested" / "backup.json"
    assert cli.main(["export-backup", str(target)]) == 0
    assert target.is_file()
    assert str(target) in capsys.readouterr().out  # type: ignore[attr-defined]
    assert cli.main(["export-backup", str(target)]) == 1


def test_replace_rolls_back_when_the_insert_phase_fails(
    session: Session, monkeypatch: object
) -> None:
    import app.services.backup as backup_service

    seed_catalog(session)
    session.add(OwnedSet(set_num="1000-1"))
    session.commit()
    payload = export_backup(session)

    def fail_after_delete(_session: Session, _backup: BackupV1) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(backup_service, "_insert_all", fail_after_delete)  # type: ignore[attr-defined]
    try:
        restore_backup(session, payload, mode="replace")
    except RuntimeError:
        pass
    else:
        raise AssertionError("replace did not raise")
    assert session.scalars(select(OwnedSet)).one().set_num == "1000-1"
