from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.inventory import InventoryWarningResponse


class MatchPartResponse(BaseModel):
    part_num: str
    name: str
    image_url: str | None


class MatchColorResponse(BaseModel):
    id: int
    name: str
    rgb_hex: str


class MatchCountsResponse(BaseModel):
    required: int
    exact: int
    color_substitution: int
    equivalence_substitution: int
    missing: int


class SubstitutionResponse(BaseModel):
    required_part: MatchPartResponse
    required_color: MatchColorResponse
    supplied_part: MatchPartResponse
    supplied_color: MatchColorResponse
    quantity: int
    kind: Literal["color", "equivalent_exact_color", "equivalent_color"]


class MissingRequirementResponse(BaseModel):
    part_num: str
    part_name: str
    color_id: int
    color_name: str
    quantity: int


class MatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    set_num: str
    name: str
    year: int | None
    theme_name: str | None
    num_parts: int
    image_url: str | None
    external_url: str | None
    instructions_url: str | None
    has_local_overrides: bool
    status: Literal["exact", "substitution", "missing"]
    counts: MatchCountsResponse
    percent_exact: float
    percent_buildable: float
    substitutions: list[SubstitutionResponse]
    missing: list[MissingRequirementResponse]
    warnings: list[InventoryWarningResponse]


class RecommendationItemResponse(BaseModel):
    set_num: str
    name: str
    year: int | None
    theme_name: str | None
    num_parts: int
    image_url: str | None
    has_local_overrides: bool
    status: Literal["exact", "substitution", "missing"]
    counts: MatchCountsResponse
    percent_exact: float
    percent_buildable: float


class RecommendationsResponse(BaseModel):
    items: list[RecommendationItemResponse]
    total_candidates: int
    offset: int
    limit: int
    max_pieces: int
    theme: str | None
    year_from: int | None
    year_to: int | None
    hide_owned: bool
    status: list[Literal["exact", "substitution", "missing"]] | None
    sort: Literal["buildability", "pieces", "year", "mismatches", "missing"]
    direction: Literal["asc", "desc"]
