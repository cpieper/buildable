import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    CatalogColor,
    CatalogPart,
    CatalogSet,
    CatalogSetOverride,
    CatalogSetPartOverride,
    EquivalenceGroup,
    EquivalenceMember,
    OwnedSet,
    OwnedSetMissingPart,
)
from app.schemas.backup import (
    BackupV1,
    EquivalenceGroupBackup,
    MissingPartBackup,
    OwnedSetBackup,
    RestoreSummary,
    SetOverrideBackup,
    SetPartOverrideBackup,
)

BACKUP_SCHEMA = "what2build.backup/v1"
RESERVED_SETTING_KEYS = frozenset(
    {
        "auth.password_hash",
        "auth.revision",
        "session_secret",
        "rebrickable_api_key",
    }
)


class BackupValidationError(ValueError):
    def __init__(self, code: str, message: str, dependencies: dict[str, list[str | int]] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.dependencies = dependencies or {}


def write_backup_json(path: Path, backup: BackupV1) -> None:
    """Atomically create a UTF-8 backup without overwriting an existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(temporary_fd, "w", encoding="utf-8") as stream:
            stream.write(backup.model_dump_json(by_alias=True, indent=2))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def export_backup(session: Session) -> BackupV1:
    owned = session.scalars(select(OwnedSet).order_by(OwnedSet.set_num)).all()
    owned_by_id = {row.id: row.set_num for row in owned}
    missing = session.scalars(select(OwnedSetMissingPart).order_by(OwnedSetMissingPart.owned_set_id, OwnedSetMissingPart.part_num, OwnedSetMissingPart.color_id)).all()
    return BackupV1(
        exported_at=datetime.now(UTC),
        owned_sets=[OwnedSetBackup(set_num=row.set_num, quantity=row.quantity, completeness=row.completeness, unknown_missing_count=row.unknown_missing_count, unknown_missing_note=row.unknown_missing_note, notes=row.notes) for row in owned],
        missing_parts=[MissingPartBackup(set_num=owned_by_id[row.owned_set_id], part_num=row.part_num, color_id=row.color_id, quantity=row.quantity, note=row.note) for row in missing],
        set_overrides=[SetOverrideBackup(set_num=row.set_num, name=row.name, year=row.year, theme_name=row.theme_name, num_parts=row.num_parts, image_url=row.image_url, external_url=row.external_url, instructions_url=row.instructions_url, reason=row.reason) for row in session.scalars(select(CatalogSetOverride).order_by(CatalogSetOverride.set_num)).all()],
        set_part_overrides=[SetPartOverrideBackup(set_num=row.set_num, part_num=row.part_num, color_id=row.color_id, is_spare=row.is_spare, operation=row.operation, quantity=row.quantity, reason=row.reason) for row in session.scalars(select(CatalogSetPartOverride).order_by(CatalogSetPartOverride.set_num, CatalogSetPartOverride.part_num, CatalogSetPartOverride.color_id, CatalogSetPartOverride.is_spare)).all()],
        equivalence_groups=[EquivalenceGroupBackup(name=row.name, notes=row.notes, part_nums=sorted(session.scalars(select(EquivalenceMember.part_num).where(EquivalenceMember.group_id == row.id)).all())) for row in session.scalars(select(EquivalenceGroup).order_by(EquivalenceGroup.name)).all()],
        settings={row.key: row.value for row in session.scalars(select(AppSetting).where(AppSetting.secret.is_(False)).order_by(AppSetting.key)).all()},
    )


def validate_backup(session: Session, backup: BackupV1) -> dict[str, list[str | int]]:
    if backup.schema_name != BACKUP_SCHEMA:
        raise BackupValidationError("unsupported_schema", f"Unsupported backup schema: {backup.schema_name}")
    _reject_duplicates(backup)
    _reject_secret_settings(session, backup)
    set_nums = {row.set_num for row in backup.owned_sets} | {row.set_num for row in backup.missing_parts} | {row.set_num for row in backup.set_overrides} | {row.set_num for row in backup.set_part_overrides}
    part_nums = {row.part_num for row in backup.missing_parts} | {row.part_num for row in backup.set_part_overrides} | {part for group in backup.equivalence_groups for part in group.part_nums}
    color_ids = {row.color_id for row in backup.missing_parts} | {row.color_id for row in backup.set_part_overrides}
    found_sets = set(session.scalars(select(CatalogSet.set_num).where(CatalogSet.set_num.in_(set_nums))).all()) if set_nums else set()
    found_parts = set(session.scalars(select(CatalogPart.part_num).where(CatalogPart.part_num.in_(part_nums))).all()) if part_nums else set()
    found_colors = set(session.scalars(select(CatalogColor.id).where(CatalogColor.id.in_(color_ids))).all()) if color_ids else set()
    missing = {"sets": sorted(set_nums - found_sets), "parts": sorted(part_nums - found_parts), "colors": sorted(color_ids - found_colors)}
    missing = {key: value for key, value in missing.items() if value}
    if missing:
        raise BackupValidationError("missing_dependencies", "Catalog dependencies are missing", missing)
    return missing


def _reject_secret_settings(session: Session, backup: BackupV1) -> None:
    reserved = sorted(RESERVED_SETTING_KEYS.intersection(backup.settings))
    if reserved:
        raise BackupValidationError(
            "reserved_setting_key",
            f"Backup contains reserved setting key: {reserved[0]}",
        )
    if not backup.settings:
        return
    destination_secret = session.scalars(
        select(AppSetting.key).where(
            AppSetting.key.in_(backup.settings), AppSetting.secret.is_(True)
        )
    ).first()
    if destination_secret is not None:
        raise BackupValidationError(
            "secret_setting_key",
            f"Backup setting key is secret in this database: {destination_secret}",
        )


def _reject_duplicates(backup: BackupV1) -> None:
    groups = {
        "owned_sets": [row.set_num for row in backup.owned_sets],
        "missing_parts": [(row.set_num, row.part_num, row.color_id) for row in backup.missing_parts],
        "set_overrides": [row.set_num for row in backup.set_overrides],
        "set_part_overrides": [(row.set_num, row.part_num, row.color_id, row.is_spare) for row in backup.set_part_overrides],
        "equivalence_groups": [row.name for row in backup.equivalence_groups],
        "settings": list(backup.settings),
    }
    for kind, keys in groups.items():
        if len(keys) != len(set(keys)):
            raise BackupValidationError("duplicate_natural_key", f"Duplicate {kind} natural key")
    owned = set(groups["owned_sets"])
    if any(row.set_num not in owned for row in backup.missing_parts):
        raise BackupValidationError("missing_owned_set", "Missing parts must reference a backed-up owned set")


def restore_backup(session: Session, backup: BackupV1, mode: str) -> RestoreSummary:
    if mode not in {"replace", "merge"}:
        raise BackupValidationError("invalid_mode", "mode must be replace or merge")
    validate_backup(session, backup)
    summary = RestoreSummary(owned_sets=len(backup.owned_sets), missing_parts=len(backup.missing_parts), set_overrides=len(backup.set_overrides), set_part_overrides=len(backup.set_part_overrides), equivalence_groups=len(backup.equivalence_groups), settings=len(backup.settings))
    try:
        with session.begin_nested():
            if mode == "replace":
                _replace(session, backup)
                summary.changed = sum((summary.owned_sets, summary.missing_parts, summary.set_overrides, summary.set_part_overrides, summary.equivalence_groups, summary.settings))
            else:
                _merge(session, backup, summary)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return summary


def _replace(session: Session, backup: BackupV1) -> None:
    session.execute(delete(OwnedSetMissingPart))
    session.execute(delete(OwnedSet))
    session.execute(delete(CatalogSetPartOverride))
    session.execute(delete(CatalogSetOverride))
    session.execute(delete(EquivalenceMember))
    session.execute(delete(EquivalenceGroup))
    session.execute(delete(AppSetting).where(AppSetting.secret.is_(False)))
    _insert_all(session, backup)


def _insert_all(session: Session, backup: BackupV1) -> None:
    owned = {row.set_num: OwnedSet(**row.model_dump()) for row in backup.owned_sets}
    session.add_all(owned.values())
    session.flush()
    session.add_all(OwnedSetMissingPart(owned_set_id=owned[row.set_num].id, part_num=row.part_num, color_id=row.color_id, quantity=row.quantity, note=row.note) for row in backup.missing_parts)
    session.add_all(CatalogSetOverride(**row.model_dump()) for row in backup.set_overrides)
    session.add_all(CatalogSetPartOverride(**row.model_dump()) for row in backup.set_part_overrides)
    for row in backup.equivalence_groups:
        group = EquivalenceGroup(name=row.name, notes=row.notes)
        session.add(group)
        session.flush()
        session.add_all(EquivalenceMember(group_id=group.id, part_num=part_num) for part_num in row.part_nums)
    session.add_all(AppSetting(key=key, value=value, secret=False) for key, value in backup.settings.items())


def _merge(session: Session, backup: BackupV1, summary: RestoreSummary) -> None:
    for row in backup.owned_sets:
        current = session.scalar(select(OwnedSet).where(OwnedSet.set_num == row.set_num))
        if current is None:
            current = OwnedSet(**row.model_dump())
            session.add(current)
            session.flush()
            summary.changed += 1
        elif _same(current, row.model_dump()):
            summary.skipped += 1
        else:
            summary.conflicting += 1
    # Missing parts need the owned-set natural key, not a database id.
    for row in backup.missing_parts:
        owner = session.scalar(select(OwnedSet).where(OwnedSet.set_num == row.set_num))
        assert owner is not None
        current = session.scalar(select(OwnedSetMissingPart).where(OwnedSetMissingPart.owned_set_id == owner.id, OwnedSetMissingPart.part_num == row.part_num, OwnedSetMissingPart.color_id == row.color_id))
        if current is None:
            session.add(OwnedSetMissingPart(owned_set_id=owner.id, part_num=row.part_num, color_id=row.color_id, quantity=row.quantity, note=row.note))
            summary.changed += 1
        elif _same(current, {"quantity": row.quantity, "note": row.note}):
            summary.skipped += 1
        else:
            summary.conflicting += 1
    _merge_model_rows(session, CatalogSetOverride, backup.set_overrides, ("set_num",), summary)
    _merge_model_rows(session, CatalogSetPartOverride, backup.set_part_overrides, ("set_num", "part_num", "color_id", "is_spare"), summary)
    for row in backup.equivalence_groups:
        current = session.scalar(select(EquivalenceGroup).where(EquivalenceGroup.name == row.name))
        if current is None:
            group = EquivalenceGroup(name=row.name, notes=row.notes)
            session.add(group); session.flush()
            session.add_all(EquivalenceMember(group_id=group.id, part_num=part) for part in row.part_nums)
            summary.changed += 1
        else:
            members = sorted(session.scalars(select(EquivalenceMember.part_num).where(EquivalenceMember.group_id == current.id)).all())
            if current.notes == row.notes and members == sorted(row.part_nums): summary.skipped += 1
            else: summary.conflicting += 1
    for key, value in backup.settings.items():
        current = session.get(AppSetting, key)
        if current is None:
            session.add(AppSetting(key=key, value=value, secret=False)); summary.changed += 1
        elif current.secret or current.value != value: summary.conflicting += 1
        else: summary.skipped += 1


def _merge_model_rows(session: Session, model: type, rows: list[SetOverrideBackup] | list[SetPartOverrideBackup], keys: tuple[str, ...], summary: RestoreSummary) -> None:
    for row in rows:
        data = row.model_dump()
        current = session.scalar(select(model).filter_by(**{key: data[key] for key in keys}))
        if current is None:
            session.add(model(**data)); summary.changed += 1
        elif _same(current, data): summary.skipped += 1
        else: summary.conflicting += 1


def _same(model: object, data: dict[str, object]) -> bool:
    return all(getattr(model, key) == value for key, value in data.items())
