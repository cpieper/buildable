import csv
import re
from collections.abc import Callable
from io import TextIOWrapper
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.models import utc_now
from app.schemas.catalog import CatalogDiscoveryImportSummary
from app.services.catalog_import import CatalogImportError
from app.services.rebrickable import (
    CatalogLookupError,
    ImportedSet,
    import_rebrickable_set,
)

_SET_NUMBER = re.compile(r"^[0-9]+-[1-9][0-9]*$")
_SET_HEADERS = ("Set Number", "set_num", "Set Num", "set number")


def import_discovery_csv(
    stream: BinaryIO,
    session: Session,
    *,
    lookup_set: Callable[[str], ImportedSet],
) -> CatalogDiscoveryImportSummary:
    started_at = utc_now()
    set_nums = _read_set_numbers(stream)
    imported = 0
    skipped: list[str] = []
    warnings: list[str] = []

    for set_num in set_nums:
        if not _SET_NUMBER.fullmatch(set_num):
            skipped.append(set_num)
            warnings.append(f"{set_num} is not an official set number.")
            continue
        try:
            import_rebrickable_set(lookup_set(set_num), session)
        except (CatalogLookupError, CatalogImportError) as error:
            skipped.append(set_num)
            message = getattr(error, "message", str(error))
            warnings.append(f"{set_num} could not be imported from Rebrickable: {message}")
            continue
        imported += 1

    return CatalogDiscoveryImportSummary(
        sets_imported=imported,
        rows_skipped=len(skipped),
        skipped_set_nums=skipped,
        warnings=warnings,
        started_at=started_at,
        completed_at=utc_now(),
    )


def _read_set_numbers(stream: BinaryIO) -> list[str]:
    try:
        text_stream = TextIOWrapper(stream, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_stream)
        if reader.fieldnames is None:
            raise CatalogImportError("discovery.csv:1: missing CSV header")
        duplicates = sorted(
            {
                header
                for header in reader.fieldnames
                if reader.fieldnames.count(header) > 1
            }
        )
        if duplicates:
            raise CatalogImportError(
                f"discovery.csv:1: duplicate CSV header: {', '.join(duplicates)}"
            )
        set_header = next((header for header in _SET_HEADERS if header in reader.fieldnames), None)
        if set_header is None:
            raise CatalogImportError(
                "discovery.csv:1: missing required column: Set Number"
            )

        rows: list[str] = []
        seen: set[str] = set()
        for number, values in enumerate(reader, start=2):
            if None in values:
                raise CatalogImportError(
                    f"discovery.csv:{number}: row has more values than columns"
                )
            set_num = (values[set_header] or "").strip()
            if not set_num:
                continue
            if set_num not in seen:
                rows.append(set_num)
                seen.add(set_num)
        return rows
    except (csv.Error, UnicodeError, OSError) as error:
        raise CatalogImportError(f"discovery.csv: unable to read CSV: {error}") from error
