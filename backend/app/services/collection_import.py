import csv
from collections.abc import Callable
from dataclasses import dataclass
from io import TextIOWrapper
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import OwnedSet
from app.repositories.catalog import CatalogRepository
from app.schemas.collection import CollectionImportSummary
from app.services.catalog_import import CatalogImportError
from app.services.rebrickable import (
    CatalogLookupError,
    ImportedSet,
    import_rebrickable_set,
)

REBRICKABLE_COLLECTION_COLUMNS = {"Set Number", "Quantity"}


class CollectionImportError(ValueError):
    pass


@dataclass(frozen=True)
class CollectionCsvRow:
    number: int
    set_num: str
    quantity: int


def import_rebrickable_collection_csv(
    stream: BinaryIO,
    session: Session,
    *,
    lookup_missing: Callable[[str], ImportedSet] | None = None,
) -> CollectionImportSummary:
    rows = _read_collection_rows(stream)
    lookup_warnings = _import_missing_catalog_sets(rows, session, lookup_missing)
    imported = 0
    quantity_added = 0
    missing_set_nums: list[str] = []

    try:
        repository = CatalogRepository(session)
        for row in rows:
            if repository.get_effective_set(row.set_num) is None:
                missing_set_nums.append(row.set_num)
                continue
            owned = session.scalar(select(OwnedSet).where(OwnedSet.set_num == row.set_num))
            if owned is None:
                owned = OwnedSet(set_num=row.set_num, quantity=row.quantity)
                session.add(owned)
            else:
                owned.quantity += row.quantity
            imported += 1
            quantity_added += row.quantity
        session.commit()
    except SQLAlchemyError as error:
        session.rollback()
        raise CollectionImportError(f"collection import failed: {error}") from error

    unique_missing = sorted(set(missing_set_nums))
    missing_warnings = [
        lookup_warnings.get(set_num) or f"{set_num} is not in the local catalog."
        for set_num in unique_missing
    ]
    return CollectionImportSummary(
        rows_imported=imported,
        quantity_added=quantity_added,
        rows_skipped=len(missing_set_nums),
        missing_set_nums=unique_missing,
        warnings=missing_warnings,
    )


def _import_missing_catalog_sets(
    rows: list[CollectionCsvRow],
    session: Session,
    lookup_missing: Callable[[str], ImportedSet] | None,
) -> dict[str, str]:
    repository = CatalogRepository(session)
    missing = sorted(
        {
            row.set_num
            for row in rows
            if repository.get_effective_set(row.set_num) is None
        }
    )
    if lookup_missing is None:
        return {}

    warnings: dict[str, str] = {}
    for set_num in missing:
        try:
            import_rebrickable_set(lookup_missing(set_num), session)
        except (CatalogImportError, CatalogLookupError) as error:
            message = getattr(error, "message", str(error))
            warnings[set_num] = (
                f"{set_num} could not be imported from Rebrickable: {message}"
            )
    return warnings


def _read_collection_rows(stream: BinaryIO) -> list[CollectionCsvRow]:
    try:
        text_stream = TextIOWrapper(stream, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_stream)
        if reader.fieldnames is None:
            raise CollectionImportError("sets.csv:1: missing CSV header")
        duplicates = sorted(
            {
                header
                for header in reader.fieldnames
                if reader.fieldnames.count(header) > 1
            }
        )
        if duplicates:
            raise CollectionImportError(
                f"sets.csv:1: duplicate CSV header: {', '.join(duplicates)}"
            )
        missing = REBRICKABLE_COLLECTION_COLUMNS.difference(reader.fieldnames)
        if missing:
            raise CollectionImportError(
                f"sets.csv:1: missing required columns: {', '.join(sorted(missing))}"
            )

        rows: list[CollectionCsvRow] = []
        for number, values in enumerate(reader, start=2):
            if None in values:
                raise CollectionImportError(
                    f"sets.csv:{number}: row has more values than columns"
                )
            set_num = (values["Set Number"] or "").strip()
            if not set_num:
                raise CollectionImportError(f"sets.csv:{number}: Set Number is required")
            rows.append(
                CollectionCsvRow(
                    number=number,
                    set_num=set_num,
                    quantity=_positive_integer(number, values["Quantity"] or ""),
                )
            )
        return rows
    except (csv.Error, UnicodeError, OSError) as error:
        raise CollectionImportError(f"sets.csv: unable to read CSV: {error}") from error


def _positive_integer(number: int, value: str) -> int:
    try:
        quantity = int(value)
    except ValueError as error:
        raise CollectionImportError(
            f"sets.csv:{number}: Quantity must be a positive integer"
        ) from error
    if quantity <= 0:
        raise CollectionImportError(
            f"sets.csv:{number}: Quantity must be a positive integer"
        )
    return quantity
