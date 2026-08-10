from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    CatalogColor,
    CatalogPart,
    CatalogSet,
    CatalogSetOverride,
    CatalogSetPart,
    CatalogSetPartOverride,
)


@dataclass(frozen=True)
class EffectivePartRow:
    part_num: str
    part_name: str
    color_id: int
    color_name: str
    rgb_hex: str
    quantity: int
    is_spare: bool
    source_kind: str
    image_url: str | None


@dataclass(frozen=True)
class EffectiveSet:
    set_num: str
    name: str
    year: int | None
    theme_name: str | None
    num_parts: int
    image_url: str | None
    external_url: str | None
    instructions_url: str | None
    has_local_overrides: bool
    parts: list[EffectivePartRow]


class CatalogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def search_sets(self, query: str, limit: int) -> list[EffectiveSet]:
        if limit <= 0:
            return []

        normalized = query.strip().lower()
        effective_name = func.coalesce(CatalogSetOverride.name, CatalogSet.name)
        statement = select(CatalogSet.set_num).outerjoin(CatalogSetOverride)
        if normalized:
            statement = statement.where(
                or_(
                    func.lower(CatalogSet.set_num).contains(
                        normalized, autoescape=True
                    ),
                    func.lower(effective_name).contains(normalized, autoescape=True),
                )
            )
        statement = statement.order_by(
            func.lower(effective_name), CatalogSet.set_num
        ).limit(limit)

        results: list[EffectiveSet] = []
        for set_num in self._session.scalars(statement):
            effective_set = self.get_effective_set(set_num)
            if effective_set is not None:
                results.append(effective_set)
        return results

    def get_effective_set(self, set_num: str) -> EffectiveSet | None:
        catalog_set = self._session.get(CatalogSet, set_num)
        if catalog_set is None:
            return None

        metadata_override = self._session.get(CatalogSetOverride, set_num)
        part_rows = self._load_imported_parts(set_num)
        part_override_count = self._apply_part_overrides(set_num, part_rows)

        parts = sorted(
            part_rows.values(),
            key=lambda row: (
                row.part_name.casefold(),
                row.color_name.casefold(),
                row.part_num,
                row.color_id,
                row.is_spare,
            ),
        )
        return EffectiveSet(
            set_num=catalog_set.set_num,
            name=self._override(metadata_override, "name", catalog_set.name),
            year=self._override(metadata_override, "year", catalog_set.year),
            theme_name=self._override(
                metadata_override, "theme_name", catalog_set.theme_name
            ),
            num_parts=self._override(
                metadata_override, "num_parts", catalog_set.num_parts
            ),
            image_url=self._override(
                metadata_override, "image_url", catalog_set.image_url
            ),
            external_url=self._override(
                metadata_override, "external_url", catalog_set.external_url
            ),
            instructions_url=self._override(
                metadata_override,
                "instructions_url",
                catalog_set.instructions_url,
            ),
            has_local_overrides=(
                metadata_override is not None or part_override_count > 0
            ),
            parts=parts,
        )

    def _load_imported_parts(
        self, set_num: str
    ) -> dict[tuple[str, int, bool], EffectivePartRow]:
        statement = (
            select(CatalogSetPart, CatalogPart, CatalogColor)
            .join(CatalogPart, CatalogPart.part_num == CatalogSetPart.part_num)
            .join(CatalogColor, CatalogColor.id == CatalogSetPart.color_id)
            .where(CatalogSetPart.set_num == set_num)
        )
        result: dict[tuple[str, int, bool], EffectivePartRow] = {}
        for source_row, part, color in self._session.execute(statement):
            key = (source_row.part_num, source_row.color_id, source_row.is_spare)
            existing = result.get(key)
            if existing is None:
                result[key] = EffectivePartRow(
                    part_num=part.part_num,
                    part_name=part.name,
                    color_id=color.id,
                    color_name=color.name,
                    rgb_hex=color.rgb_hex,
                    quantity=source_row.quantity,
                    is_spare=source_row.is_spare,
                    source_kind=source_row.source_kind,
                    image_url=part.image_url,
                )
                continue

            source_kind = (
                existing.source_kind
                if existing.source_kind == source_row.source_kind
                else "mixed"
            )
            result[key] = EffectivePartRow(
                part_num=existing.part_num,
                part_name=existing.part_name,
                color_id=existing.color_id,
                color_name=existing.color_name,
                rgb_hex=existing.rgb_hex,
                quantity=existing.quantity + source_row.quantity,
                is_spare=existing.is_spare,
                source_kind=source_kind,
                image_url=existing.image_url,
            )
        return result

    def _apply_part_overrides(
        self,
        set_num: str,
        parts: dict[tuple[str, int, bool], EffectivePartRow],
    ) -> int:
        statement = (
            select(CatalogSetPartOverride, CatalogPart, CatalogColor)
            .join(CatalogPart, CatalogPart.part_num == CatalogSetPartOverride.part_num)
            .join(CatalogColor, CatalogColor.id == CatalogSetPartOverride.color_id)
            .where(CatalogSetPartOverride.set_num == set_num)
        )
        count = 0
        for override, part, color in self._session.execute(statement):
            count += 1
            key = (override.part_num, override.color_id, override.is_spare)
            if override.operation == "delete":
                parts.pop(key, None)
                continue

            if override.quantity is None:
                raise ValueError("upsert inventory overrides require a quantity")
            parts[key] = EffectivePartRow(
                part_num=part.part_num,
                part_name=part.name,
                color_id=color.id,
                color_name=color.name,
                rgb_hex=color.rgb_hex,
                quantity=override.quantity,
                is_spare=override.is_spare,
                source_kind="override",
                image_url=part.image_url,
            )
        return count

    @staticmethod
    def _override(override: object | None, attribute: str, original: object):
        if override is None:
            return original
        value = getattr(override, attribute)
        return original if value is None else value
