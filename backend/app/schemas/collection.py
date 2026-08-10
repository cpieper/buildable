from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OwnedSetCreate(BaseModel):
    set_num: str
    quantity: int = Field(default=1, ge=1)
    completeness: str = Field(default="complete", pattern="^(complete|incomplete)$")
    unknown_missing_count: int = Field(default=0, ge=0)
    unknown_missing_note: str | None = None
    notes: str | None = None


class OwnedSetUpdate(BaseModel):
    quantity: int | None = Field(default=None, ge=1)
    completeness: str | None = Field(default=None, pattern="^(complete|incomplete)$")
    unknown_missing_count: int | None = Field(default=None, ge=0)
    unknown_missing_note: str | None = None
    notes: str | None = None


class MissingPartCreate(BaseModel):
    part_num: str
    color_id: int
    quantity: int = Field(ge=1)
    note: str | None = None


class MissingPartUpdate(BaseModel):
    quantity: int | None = Field(default=None, ge=1)
    note: str | None = None


class MissingPartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owned_set_id: int
    part_num: str
    color_id: int
    quantity: int
    note: str | None


class OwnedSetResponse(BaseModel):
    id: int
    set_num: str
    set_name: str
    quantity: int
    completeness: str
    unknown_missing_count: int
    unknown_missing_note: str | None
    notes: str | None
    known_missing_total: int
    has_local_overrides: bool
    added_at: datetime
    updated_at: datetime
