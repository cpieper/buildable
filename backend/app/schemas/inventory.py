from pydantic import BaseModel, ConfigDict


class InventoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    part_num: str
    part_name: str
    color_id: int
    color_name: str
    rgb_hex: str
    quantity: int
    image_url: str | None
    source_set_nums: tuple[str, ...]


class InventoryWarningResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    owned_set_id: int
    set_num: str
    set_name: str
    unknown_missing_count: int | None
    note: str | None


class InventoryResponse(BaseModel):
    items: list[InventoryItemResponse]
    warnings: list[InventoryWarningResponse]
    total_quantity: int
