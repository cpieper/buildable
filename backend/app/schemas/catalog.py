from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ManualCatalogPart(BaseModel):
    part_num: str
    part_name: str
    color_id: int
    color_name: str
    rgb_hex: str
    quantity: int = Field(gt=0)
    is_spare: bool = False


class ManualCatalogSetCreate(BaseModel):
    set_num: str = Field(pattern=r"^[0-9]+-[1-9][0-9]*$")
    name: str
    year: int | None = None
    theme_name: str | None = None
    image_url: HttpUrl | None = None
    external_url: HttpUrl | None = None
    instructions_url: HttpUrl | None = None
    parts: list[ManualCatalogPart] = Field(min_length=1)


class ImportSummary(BaseModel):
    sets: int
    parts: int
    colors: int
    warnings: list[str]
    started_at: datetime
    completed_at: datetime
    sync_run_id: int


class CatalogDiscoveryImportSummary(BaseModel):
    sets_imported: int
    rows_skipped: int
    skipped_set_nums: list[str]
    warnings: list[str]
    started_at: datetime
    completed_at: datetime


class CatalogSetSummary(BaseModel):
    set_num: str
    name: str
    year: int | None
    theme_name: str | None
    num_parts: int
    image_url: str | None
    has_local_overrides: bool


class CatalogPartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    part_num: str
    part_name: str
    color_id: int
    color_name: str
    rgb_hex: str
    quantity: int
    is_spare: bool
    source_kind: str
    image_url: str | None


class CatalogSetDetail(CatalogSetSummary):
    model_config = ConfigDict(from_attributes=True)

    external_url: str | None
    instructions_url: str | None
    parts: list[CatalogPartResponse]


class RemoteSetSummary(BaseModel):
    set_num: str
    name: str
    year: int | None
    theme_id: int | None
    num_parts: int
    image_url: str | None
    external_url: str | None


class CatalogLookupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    set: CatalogSetDetail
    summary: ImportSummary
