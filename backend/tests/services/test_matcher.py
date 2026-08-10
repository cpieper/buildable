import pytest

from app.repositories.catalog import EffectivePartRow, EffectiveSet
from app.services.inventory import InventoryItem, InventorySnapshot
from app.services.matcher import match_set


def item(part_num: str, color_id: int, quantity: int) -> InventoryItem:
    return InventoryItem(
        part_num=part_num,
        part_name=f"Part {part_num}",
        color_id=color_id,
        color_name=f"Color {color_id}",
        rgb_hex="FFFFFF",
        quantity=quantity,
        image_url=None,
        source_set_nums=(),
    )


def row(
    part_num: str, color_id: int, quantity: int, *, is_spare: bool = False
) -> EffectivePartRow:
    return EffectivePartRow(
        part_num=part_num,
        part_name=f"Part {part_num}",
        color_id=color_id,
        color_name=f"Color {color_id}",
        rgb_hex="FFFFFF",
        quantity=quantity,
        is_spare=is_spare,
        source_kind="test",
        image_url=None,
    )


def snapshot(items: list[InventoryItem]) -> InventorySnapshot:
    return InventorySnapshot(tuple(items), (), sum(value.quantity for value in items))


def target(parts: list[EffectivePartRow]) -> EffectiveSet:
    return EffectiveSet(
        set_num="target-1",
        name="Target",
        year=None,
        theme_name=None,
        num_parts=sum(value.quantity for value in parts),
        image_url=None,
        external_url=None,
        instructions_url=None,
        has_local_overrides=False,
        parts=parts,
    )


@pytest.mark.parametrize(
    ("available", "required", "status", "exact", "color", "equivalent", "missing"),
    [
        ([item("3001", 5, 2)], [row("3001", 5, 2)], "exact", 2, 0, 0, 0),
        ([item("3001", 1, 2)], [row("3001", 5, 2)], "substitution", 0, 2, 0, 0),
        ([item("3002", 5, 2)], [row("3001", 5, 2)], "substitution", 0, 0, 2, 0),
        ([item("3001", 5, 1)], [row("3001", 5, 2)], "missing", 1, 0, 0, 1),
    ],
)
def test_match_statuses(available, required, status, exact, color, equivalent, missing):
    result = match_set(target(required), snapshot(available), {"3001": frozenset({"3002"})})

    assert result.status == status
    assert (
        result.exact_quantity,
        result.color_substitution_quantity,
        result.equivalence_substitution_quantity,
        result.missing_quantity,
    ) == (exact, color, equivalent, missing)


def test_exact_matches_are_consumed_before_color_substitutions() -> None:
    result = match_set(
        target([row("3001", 5, 2)]),
        snapshot([item("3001", 5, 1), item("3001", 1, 2)]),
        {},
    )

    assert [(value.supplied_color_id, value.quantity, value.kind) for value in result.allocations] == [
        (5, 1, "exact"),
        (1, 1, "color"),
    ]


def test_same_color_equivalents_precede_any_color_equivalents() -> None:
    result = match_set(
        target([row("3001", 5, 2)]),
        snapshot([item("3002", 1, 2), item("3003", 5, 1)]),
        {"3001": frozenset({"3002", "3003"})},
    )

    assert [(value.supplied_part_num, value.quantity, value.kind) for value in result.allocations] == [
        ("3003", 1, "equivalent_exact_color"),
        ("3002", 1, "equivalent_color"),
    ]


def test_one_available_piece_cannot_satisfy_two_requirements() -> None:
    result = match_set(
        target([row("3001", 5, 1), row("3001", 1, 1)]),
        snapshot([item("3001", 5, 1)]),
        {},
    )

    assert result.exact_quantity + result.color_substitution_quantity == 1
    assert result.missing_quantity == 1


def test_target_spares_are_ignored() -> None:
    result = match_set(
        target([row("3001", 5, 1), row("6141", 1, 4, is_spare=True)]),
        snapshot([item("3001", 5, 1)]),
        {},
    )

    assert result.required_quantity == 1
    assert result.status == "exact"
    assert result.missing == ()


def test_quantities_aggregate_across_matching_target_rows() -> None:
    result = match_set(
        target([row("3001", 5, 1), row("3001", 5, 2)]),
        snapshot([item("3001", 5, 3)]),
        {},
    )

    assert result.required_quantity == 3
    assert result.exact_quantity == 3
    assert len(result.allocations) == 1
    assert result.allocations[0].quantity == 3


def test_percentages_use_required_quantity_as_denominator() -> None:
    result = match_set(
        target([row("3001", 5, 4)]),
        snapshot([item("3001", 5, 1), item("3001", 1, 2)]),
        {},
    )

    assert result.percent_exact == 25.0
    assert result.percent_buildable == 75.0


def test_empty_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one non-spare part"):
        match_set(target([]), snapshot([]), {})
