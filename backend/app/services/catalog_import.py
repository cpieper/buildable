import csv
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from io import TextIOWrapper
from typing import BinaryIO
from zipfile import BadZipFile, ZipFile

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, SessionTransactionOrigin

from app.models import (
    CatalogColor,
    CatalogPart,
    CatalogSet,
    CatalogSetOverride,
    CatalogSetPart,
    CatalogSetPartOverride,
    OwnedSet,
    SyncRun,
    utc_now,
)
from app.repositories.catalog import CatalogRepository, EffectiveSet
from app.schemas.catalog import ImportSummary, ManualCatalogSetCreate

REBRICKABLE_SOURCE = "rebrickable_csv"
REQUIRED_COLUMNS = {
    "sets.csv": {"set_num", "name", "year", "theme_id", "num_parts", "img_url"},
    "themes.csv": {"id", "name", "parent_id"},
    "parts.csv": {"part_num", "name", "part_cat_id"},
    "part_categories.csv": {"id", "name"},
    "colors.csv": {"id", "name", "rgb"},
    "inventories.csv": {"id", "version", "set_num"},
    "inventory_parts.csv": {
        "inventory_id",
        "part_num",
        "color_id",
        "quantity",
        "is_spare",
    },
    "inventory_minifigs.csv": {"inventory_id", "fig_num", "quantity"},
    "minifigs.csv": {"fig_num", "name", "num_parts", "img_url"},
}


class CatalogImportError(ValueError):
    pass


@dataclass(frozen=True)
class CsvRow:
    filename: str
    number: int
    values: dict[str, str]

    def error(self, message: str) -> CatalogImportError:
        return CatalogImportError(f"{self.filename}:{self.number}: {message}")


@dataclass(frozen=True)
class ParsedCatalog:
    sets: dict[str, dict[str, object]]
    themes: dict[int, str]
    categories: dict[int, str]
    parts: dict[str, dict[str, object]]
    colors: dict[int, dict[str, object]]
    inventories: dict[int, dict[str, object]]
    inventory_parts: list[dict[str, object]]
    inventory_minifigs: list[dict[str, object]]
    minifigs: dict[str, dict[str, object]]


def import_rebrickable_zip(stream: BinaryIO, session: Session) -> ImportSummary:
    _prepare_owned_session(session)
    started_at = utc_now()
    try:
        parsed = _parse_zip(stream)
        _replace_rebrickable_catalog(parsed, session)
        completed_at = utc_now()
        summary_values = {
            "sets": len(parsed.sets),
            "parts": len(parsed.parts),
            "colors": len(parsed.colors),
            "warnings": [],
            "started_at": started_at,
            "completed_at": completed_at,
        }
        run = SyncRun(
            source=REBRICKABLE_SOURCE,
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            summary_json=json.dumps(
                {
                    "sets": summary_values["sets"],
                    "parts": summary_values["parts"],
                    "colors": summary_values["colors"],
                    "warnings": [],
                }
            ),
            error=None,
        )
        session.add(run)
        session.commit()
        return ImportSummary(sync_run_id=run.id, **summary_values)
    except CatalogImportError as error:
        session.rollback()
        _record_failed_run(session, started_at, error)
        raise
    except (BadZipFile, csv.Error, UnicodeError, IntegrityError, OSError) as error:
        session.rollback()
        normalized = CatalogImportError(f"catalog import failed: {error}")
        _record_failed_run(session, started_at, normalized)
        raise normalized from error


def import_manual_set(
    payload: ManualCatalogSetCreate, session: Session
) -> EffectiveSet:
    _prepare_owned_session(session)
    if session.get(CatalogSet, payload.set_num) is not None:
        session.rollback()
        raise CatalogImportError(f"manual set {payload.set_num!r} already exists")

    identities: set[tuple[str, int, bool]] = set()
    for index, part in enumerate(payload.parts, start=1):
        identity = (part.part_num, part.color_id, part.is_spare)
        if identity in identities:
            session.rollback()
            raise CatalogImportError(
                f"manual parts:{index}: duplicate part/color/spare identity"
            )
        identities.add(identity)

    try:
        imported_at = utc_now()
        session.add(
            CatalogSet(
                set_num=payload.set_num,
                name=payload.name,
                year=payload.year,
                theme_id=None,
                theme_name=payload.theme_name,
                num_parts=sum(
                    part.quantity for part in payload.parts if not part.is_spare
                ),
                image_url=_url_string(payload.image_url),
                external_url=_url_string(payload.external_url),
                instructions_url=_url_string(payload.instructions_url),
                source="manual",
                source_updated_at=None,
                imported_at=imported_at,
            )
        )
        for part in payload.parts:
            existing_part = session.get(CatalogPart, part.part_num)
            if existing_part is None:
                session.add(
                    CatalogPart(
                        part_num=part.part_num,
                        name=part.part_name,
                        category_name=None,
                        image_url=None,
                        external_ids_json="{}",
                    )
                )
            existing_color = session.get(CatalogColor, part.color_id)
            if existing_color is None:
                session.add(
                    CatalogColor(
                        id=part.color_id,
                        name=part.color_name,
                        rgb_hex=part.rgb_hex,
                        external_ids_json="{}",
                    )
                )
            session.flush()
            session.add(
                CatalogSetPart(
                    set_num=payload.set_num,
                    part_num=part.part_num,
                    color_id=part.color_id,
                    quantity=part.quantity,
                    is_spare=part.is_spare,
                    source_kind="manual",
                    source_id=payload.set_num,
                )
            )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise CatalogImportError(f"manual catalog import failed: {error.orig}") from error

    result = CatalogRepository(session).get_effective_set(payload.set_num)
    if result is None:
        raise RuntimeError("manual set missing after committed import")
    return result


def _prepare_owned_session(session: Session) -> None:
    if session.new or session.dirty or session.deleted:
        raise CatalogImportError("catalog import requires a session without pending changes")
    if session.in_transaction():
        transaction = session.get_transaction()
        if (
            transaction is None
            or transaction.origin is not SessionTransactionOrigin.AUTOBEGIN
        ):
            raise CatalogImportError(
                "catalog import requires a session without pending changes"
            )
        connection = session.connection()
        driver_connection = connection.connection.driver_connection
        if getattr(driver_connection, "in_transaction", True):
            raise CatalogImportError(
                "catalog import requires a session without pending changes"
            )
        session.rollback()


def _record_failed_run(
    session: Session, started_at: datetime, error: CatalogImportError
) -> None:
    completed_at = utc_now()
    session.add(
        SyncRun(
            source=REBRICKABLE_SOURCE,
            status="failed",
            started_at=started_at,
            completed_at=completed_at,
            summary_json=None,
            error=str(error),
        )
    )
    session.commit()


def _url_string(value: object | None) -> str | None:
    return None if value is None else str(value)


def _parse_zip(stream: BinaryIO) -> ParsedCatalog:
    try:
        archive = ZipFile(stream)
    except BadZipFile as error:
        raise CatalogImportError("upload is not a valid ZIP archive") from error
    with archive:
        names = archive.namelist()
        for filename in REQUIRED_COLUMNS:
            occurrences = names.count(filename)
            if occurrences == 0:
                raise CatalogImportError(f"{filename}: missing required ZIP member")
            if occurrences > 1:
                raise CatalogImportError(f"{filename}: duplicate ZIP member")
        raw = {
            filename: _read_rows(archive, filename, columns)
            for filename, columns in REQUIRED_COLUMNS.items()
        }
    return _validate_rows(raw)


def _read_rows(
    archive: ZipFile, filename: str, required_columns: set[str]
) -> list[CsvRow]:
    try:
        member = archive.open(filename)
        with TextIOWrapper(member, encoding="utf-8-sig", newline="") as text_stream:
            reader = csv.DictReader(text_stream)
            if reader.fieldnames is None:
                raise CatalogImportError(f"{filename}:1: missing CSV header")
            missing = required_columns.difference(reader.fieldnames)
            if missing:
                names = ", ".join(sorted(missing))
                raise CatalogImportError(
                    f"{filename}:1: missing required columns: {names}"
                )
            rows: list[CsvRow] = []
            for number, values in enumerate(reader, start=2):
                if None in values:
                    raise CatalogImportError(
                        f"{filename}:{number}: row has more values than columns"
                    )
                rows.append(
                    CsvRow(
                        filename=filename,
                        number=number,
                        values={key: value or "" for key, value in values.items()},
                    )
                )
            return rows
    except KeyError as error:
        raise CatalogImportError(f"{filename}: missing required ZIP member") from error
    except (
        BadZipFile,
        RuntimeError,
        NotImplementedError,
        csv.Error,
        UnicodeError,
        OSError,
    ) as error:
        raise CatalogImportError(
            f"{filename}: unable to read ZIP member: {error}"
        ) from error


def _validate_rows(raw: dict[str, list[CsvRow]]) -> ParsedCatalog:
    themes: dict[int, str] = {}
    theme_rows: dict[int, CsvRow] = {}
    theme_parents: dict[int, int | None] = {}
    for row in raw["themes.csv"]:
        theme_id = _integer(row, "id")
        _unique(theme_rows, theme_id, row)
        themes[theme_id] = _required(row, "name")
        theme_parents[theme_id] = _optional_integer(row, "parent_id")
    for theme_id, parent_id in theme_parents.items():
        if parent_id is not None and parent_id not in themes:
            raise theme_rows[theme_id].error(f"unknown parent_id {parent_id}")

    categories: dict[int, str] = {}
    category_rows: dict[int, CsvRow] = {}
    for row in raw["part_categories.csv"]:
        category_id = _integer(row, "id")
        _unique(category_rows, category_id, row)
        categories[category_id] = _required(row, "name")

    colors: dict[int, dict[str, object]] = {}
    color_rows: dict[int, CsvRow] = {}
    for row in raw["colors.csv"]:
        color_id = _integer(row, "id")
        _unique(color_rows, color_id, row)
        colors[color_id] = {
            "id": color_id,
            "name": _required(row, "name"),
            "rgb_hex": _required(row, "rgb"),
        }

    parts: dict[str, dict[str, object]] = {}
    part_rows: dict[str, CsvRow] = {}
    for row in raw["parts.csv"]:
        part_num = _required(row, "part_num")
        _unique(part_rows, part_num, row)
        category_id = _integer(row, "part_cat_id")
        if category_id not in categories:
            raise row.error(f"unknown part_cat_id {category_id}")
        parts[part_num] = {
            "part_num": part_num,
            "name": _required(row, "name"),
            "category_name": categories[category_id],
            "image_url": None,
        }

    minifigs: dict[str, dict[str, object]] = {}
    minifig_rows: dict[str, CsvRow] = {}
    for row in raw["minifigs.csv"]:
        fig_num = _required(row, "fig_num")
        _unique(minifig_rows, fig_num, row)
        num_parts = _integer(row, "num_parts")
        if num_parts < 0:
            raise row.error("num_parts must be non-negative")
        minifigs[fig_num] = {
            "fig_num": fig_num,
            "name": _required(row, "name"),
            "num_parts": num_parts,
        }

    sets: dict[str, dict[str, object]] = {}
    set_rows: dict[str, CsvRow] = {}
    for row in raw["sets.csv"]:
        set_num = _required(row, "set_num")
        _unique(set_rows, set_num, row)
        theme_id = _optional_integer(row, "theme_id")
        if theme_id is not None and theme_id not in themes:
            raise row.error(f"unknown theme_id {theme_id}")
        year = _optional_integer(row, "year")
        num_parts = _integer(row, "num_parts")
        if num_parts < 0:
            raise row.error("num_parts must be non-negative")
        sets[set_num] = {
            "set_num": set_num,
            "name": _required(row, "name"),
            "year": year,
            "theme_id": theme_id,
            "theme_name": themes.get(theme_id),
            "num_parts": num_parts,
            "image_url": row.values["img_url"] or None,
            "row": row,
        }

    inventories: dict[int, dict[str, object]] = {}
    inventory_rows: dict[int, CsvRow] = {}
    inventory_versions: dict[tuple[str, int], CsvRow] = {}
    for row in raw["inventories.csv"]:
        inventory_id = _integer(row, "id")
        _unique(inventory_rows, inventory_id, row)
        version = _integer(row, "version")
        if version <= 0:
            raise row.error("version must be positive")
        set_num = _required(row, "set_num")
        if set_num not in sets and set_num not in minifigs:
            raise row.error(f"unknown set_num {set_num!r}")
        _unique(inventory_versions, (set_num, version), row)
        inventories[inventory_id] = {
            "id": inventory_id,
            "version": version,
            "set_num": set_num,
            "row": row,
        }

    inventory_parts: list[dict[str, object]] = []
    inventory_part_rows: dict[tuple[int, str, int, bool], CsvRow] = {}
    for row in raw["inventory_parts.csv"]:
        inventory_id = _integer(row, "inventory_id")
        part_num = _required(row, "part_num")
        color_id = _integer(row, "color_id")
        quantity = _integer(row, "quantity")
        is_spare = _boolean(row, "is_spare")
        identity = (inventory_id, part_num, color_id, is_spare)
        _unique(inventory_part_rows, identity, row)
        if inventory_id not in inventories:
            raise row.error(f"unknown inventory_id {inventory_id}")
        if part_num not in parts:
            raise row.error(f"unknown part_num {part_num!r}")
        if color_id not in colors:
            raise row.error(f"unknown color_id {color_id}")
        if quantity <= 0:
            raise row.error("quantity must be positive")
        if row.values.get("img_url") and parts[part_num]["image_url"] is None:
            parts[part_num]["image_url"] = row.values["img_url"]
        inventory_parts.append(
            {
                "inventory_id": inventory_id,
                "part_num": part_num,
                "color_id": color_id,
                "quantity": quantity,
                "is_spare": is_spare,
                "row": row,
            }
        )

    inventory_minifigs: list[dict[str, object]] = []
    inventory_minifig_rows: dict[tuple[int, str], CsvRow] = {}
    for row in raw["inventory_minifigs.csv"]:
        inventory_id = _integer(row, "inventory_id")
        fig_num = _required(row, "fig_num")
        quantity = _integer(row, "quantity")
        identity = (inventory_id, fig_num)
        _unique(inventory_minifig_rows, identity, row)
        if inventory_id not in inventories:
            raise row.error(f"unknown inventory_id {inventory_id}")
        if fig_num not in minifigs:
            raise row.error(f"unknown fig_num {fig_num!r}")
        if quantity <= 0:
            raise row.error("quantity must be positive")
        inventory_minifigs.append(
            {
                "inventory_id": inventory_id,
                "fig_num": fig_num,
                "quantity": quantity,
                "row": row,
            }
        )

    return ParsedCatalog(
        sets=sets,
        themes=themes,
        categories=categories,
        parts=parts,
        colors=colors,
        inventories=inventories,
        inventory_parts=inventory_parts,
        inventory_minifigs=inventory_minifigs,
        minifigs=minifigs,
    )


def _replace_rebrickable_catalog(parsed: ParsedCatalog, session: Session) -> None:
    incoming_set_nums = set(parsed.sets)
    collisions = session.scalars(
        select(CatalogSet).where(
            CatalogSet.set_num.in_(incoming_set_nums),
            CatalogSet.source != REBRICKABLE_SOURCE,
        )
    ).all()
    if collisions:
        collision = collisions[0]
        row = parsed.sets[collision.set_num]["row"]
        assert isinstance(row, CsvRow)
        raise row.error(
            f"set_num {collision.set_num!r} conflicts with source {collision.source!r}"
        )

    old_set_nums = set(
        session.scalars(
            select(CatalogSet.set_num).where(CatalogSet.source == REBRICKABLE_SOURCE)
        )
    )
    stale_set_nums = old_set_nums.difference(incoming_set_nums)
    _reject_referenced_stale_sets(stale_set_nums, session)

    affected_set_nums = old_set_nums.union(incoming_set_nums)
    if affected_set_nums:
        session.execute(
            delete(CatalogSetPart).where(CatalogSetPart.set_num.in_(affected_set_nums))
        )
    if stale_set_nums:
        session.execute(delete(CatalogSet).where(CatalogSet.set_num.in_(stale_set_nums)))

    imported_at = utc_now()
    for values in parsed.parts.values():
        part_num = str(values["part_num"])
        part = session.get(CatalogPart, part_num)
        if part is None:
            part = CatalogPart(part_num=part_num)
            session.add(part)
        part.name = str(values["name"])
        part.category_name = str(values["category_name"])
        part.image_url = _optional_string(values["image_url"])
        part.external_ids_json = "{}"

    for values in parsed.colors.values():
        color_id = int(values["id"])
        color = session.get(CatalogColor, color_id)
        if color is None:
            color = CatalogColor(id=color_id)
            session.add(color)
        color.name = str(values["name"])
        color.rgb_hex = str(values["rgb_hex"])
        color.external_ids_json = "{}"

    for values in parsed.sets.values():
        set_num = str(values["set_num"])
        catalog_set = session.get(CatalogSet, set_num)
        if catalog_set is None:
            catalog_set = CatalogSet(set_num=set_num)
            session.add(catalog_set)
        catalog_set.name = str(values["name"])
        catalog_set.year = _optional_int(values["year"])
        catalog_set.theme_id = _optional_int(values["theme_id"])
        catalog_set.theme_name = _optional_string(values["theme_name"])
        catalog_set.num_parts = int(values["num_parts"])
        catalog_set.image_url = _optional_string(values["image_url"])
        catalog_set.external_url = f"https://rebrickable.com/sets/{set_num}/"
        catalog_set.instructions_url = None
        catalog_set.source = REBRICKABLE_SOURCE
        catalog_set.source_updated_at = None
        catalog_set.imported_at = imported_at

    session.flush()
    for row_values in _materialize_set_parts(parsed):
        session.add(CatalogSetPart(**row_values))
    session.flush()


def _reject_referenced_stale_sets(
    stale_set_nums: set[str], session: Session
) -> None:
    if not stale_set_nums:
        return
    references = (
        ("catalog set override", CatalogSetOverride.set_num),
        ("catalog part override", CatalogSetPartOverride.set_num),
        ("owned set", OwnedSet.set_num),
    )
    for label, set_num_column in references:
        referenced = session.scalar(
            select(set_num_column).where(set_num_column.in_(stale_set_nums)).limit(1)
        )
        if referenced is not None:
            raise CatalogImportError(
                f"sets.csv: cannot remove stale set {referenced!r}; {label} references it"
            )


def _materialize_set_parts(parsed: ParsedCatalog) -> list[dict[str, object]]:
    selected = _highest_inventories(parsed.inventories.values())
    parts_by_inventory: dict[int, list[dict[str, object]]] = defaultdict(list)
    for part in parsed.inventory_parts:
        parts_by_inventory[int(part["inventory_id"])].append(part)
    figures_by_inventory: dict[int, list[dict[str, object]]] = defaultdict(list)
    for figure in parsed.inventory_minifigs:
        figures_by_inventory[int(figure["inventory_id"])].append(figure)

    materialized: dict[
        tuple[str, str, int, bool, str, str], int
    ] = defaultdict(int)
    for set_num in parsed.sets:
        inventory = selected.get(set_num)
        if inventory is None:
            row = parsed.sets[set_num]["row"]
            assert isinstance(row, CsvRow)
            raise row.error(f"no inventory found for set {set_num!r}")
        inventory_id = int(inventory["id"])
        for part in parts_by_inventory[inventory_id]:
            key = (
                set_num,
                str(part["part_num"]),
                int(part["color_id"]),
                bool(part["is_spare"]),
                "set",
                str(inventory_id),
            )
            materialized[key] += int(part["quantity"])

        for figure in figures_by_inventory[inventory_id]:
            fig_num = str(figure["fig_num"])
            figure_inventory = selected.get(fig_num)
            if figure_inventory is None:
                row = figure["row"]
                assert isinstance(row, CsvRow)
                raise row.error(f"no inventory found for minifig {fig_num!r}")
            figure_inventory_id = int(figure_inventory["id"])
            figure_quantity = int(figure["quantity"])
            for part in parts_by_inventory[figure_inventory_id]:
                key = (
                    set_num,
                    str(part["part_num"]),
                    int(part["color_id"]),
                    bool(part["is_spare"]),
                    "minifig",
                    fig_num,
                )
                materialized[key] += int(part["quantity"]) * figure_quantity

    return [
        {
            "set_num": key[0],
            "part_num": key[1],
            "color_id": key[2],
            "is_spare": key[3],
            "source_kind": key[4],
            "source_id": key[5],
            "quantity": quantity,
        }
        for key, quantity in materialized.items()
    ]


def _highest_inventories(
    inventories: Iterable[dict[str, object]],
) -> dict[str, dict[str, object]]:
    selected: dict[str, dict[str, object]] = {}
    for inventory in inventories:
        set_num = str(inventory["set_num"])
        existing = selected.get(set_num)
        if existing is None or int(inventory["version"]) > int(existing["version"]):
            selected[set_num] = inventory
    return selected


def _unique(
    seen: dict[object, CsvRow], identity: object, row: CsvRow
) -> None:
    if identity in seen:
        raise row.error(f"duplicate identity {identity!r}")
    seen[identity] = row


def _required(row: CsvRow, field: str) -> str:
    value = row.values[field].strip()
    if not value:
        raise row.error(f"{field} is required")
    return value


def _integer(row: CsvRow, field: str) -> int:
    value = _required(row, field)
    try:
        return int(value)
    except ValueError as error:
        raise row.error(f"{field} must be an integer") from error


def _optional_integer(row: CsvRow, field: str) -> int | None:
    value = row.values[field].strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise row.error(f"{field} must be an integer") from error


def _boolean(row: CsvRow, field: str) -> bool:
    value = _required(row, field).lower()
    if value in {"t", "true", "1"}:
        return True
    if value in {"f", "false", "0"}:
        return False
    raise row.error(f"{field} must be a boolean")


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)
