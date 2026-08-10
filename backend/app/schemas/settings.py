from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SetOverrideWrite(BaseModel):
    name: str | None = None
    year: int | None = None
    theme_name: str | None = None
    num_parts: int | None = Field(default=None, ge=0)
    image_url: str | None = None
    external_url: str | None = None
    instructions_url: str | None = None
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value.strip()


class PartOverrideWrite(BaseModel):
    operation: Literal["upsert", "delete"]
    quantity: int | None = Field(default=None, ge=1)
    is_spare: bool
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def operation_and_quantity_match(self) -> "PartOverrideWrite":
        if self.operation == "upsert" and self.quantity is None:
            raise ValueError("upsert requires quantity")
        if self.operation == "delete" and self.quantity is not None:
            raise ValueError("delete requires quantity=null")
        return self


class OverrideDelete(BaseModel):
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value.strip()


class PartOverrideDelete(OverrideDelete):
    is_spare: bool


class SetCorrectionResponse(BaseModel):
    imported: dict[str, object]
    override: dict[str, object] | None
    effective: dict[str, object]
    has_local_overrides: bool


class PartCorrectionResponse(BaseModel):
    imported: dict[str, object] | None
    override: dict[str, object]
    effective: dict[str, object] | None
    has_local_overrides: bool


class SetCorrectionsResponse(BaseModel):
    metadata: SetCorrectionResponse
    parts: list[PartCorrectionResponse]


class EquivalenceGroupWrite(BaseModel):
    name: str = Field(min_length=1)
    part_nums: list[str] = Field(min_length=2)
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def members_must_be_distinct(self) -> "EquivalenceGroupWrite":
        if len(set(self.part_nums)) != len(self.part_nums):
            raise ValueError("part_nums must be distinct")
        return self


class EquivalenceGroupResponse(BaseModel):
    id: int
    name: str
    part_nums: list[str]
    notes: str | None
    created_at: datetime
    updated_at: datetime
