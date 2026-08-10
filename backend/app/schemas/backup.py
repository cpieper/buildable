from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MissingPartBackup(BaseModel):
    set_num: str
    part_num: str
    color_id: int
    quantity: int = Field(ge=1)
    note: str | None = None


class OwnedSetBackup(BaseModel):
    set_num: str
    quantity: int = Field(ge=1)
    completeness: Literal["complete", "incomplete"]
    unknown_missing_count: int = Field(ge=0)
    unknown_missing_note: str | None = None
    notes: str | None = None


class SetOverrideBackup(BaseModel):
    set_num: str
    name: str | None = None
    year: int | None = None
    theme_name: str | None = None
    num_parts: int | None = Field(default=None, ge=0)
    image_url: str | None = None
    external_url: str | None = None
    instructions_url: str | None = None
    reason: str | None = None


class SetPartOverrideBackup(BaseModel):
    set_num: str
    part_num: str
    color_id: int
    is_spare: bool = False
    operation: Literal["upsert", "delete"]
    quantity: int | None = Field(default=None, ge=1)
    reason: str | None = None


class EquivalenceGroupBackup(BaseModel):
    name: str
    part_nums: list[str] = Field(min_length=1)
    notes: str | None = None


class BackupV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )

    schema_name: str = Field(default="what2build.backup/v1", alias="schema")
    exported_at: datetime
    owned_sets: list[OwnedSetBackup] = Field(default_factory=list)
    missing_parts: list[MissingPartBackup] = Field(default_factory=list)
    set_overrides: list[SetOverrideBackup] = Field(default_factory=list)
    set_part_overrides: list[SetPartOverrideBackup] = Field(default_factory=list)
    equivalence_groups: list[EquivalenceGroupBackup] = Field(default_factory=list)
    settings: dict[str, str] = Field(default_factory=dict)


class RestoreSummary(BaseModel):
    owned_sets: int = 0
    missing_parts: int = 0
    set_overrides: int = 0
    set_part_overrides: int = 0
    equivalence_groups: int = 0
    settings: int = 0
    changed: int = 0
    skipped: int = 0
    conflicting: int = 0
    safety_backup: str | None = None


class BackupValidationResponse(BaseModel):
    valid: bool
    missing_dependencies: dict[str, list[str | int]] = Field(default_factory=dict)
