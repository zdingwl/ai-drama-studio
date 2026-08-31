import pytest

from scripts import diagnose_breakdown_exact_shot_batches as diagnostic


def test_parse_batch_numbers_deduplicates_and_preserves_order() -> None:
    assert diagnostic._parse_batch_numbers("1,4,6,4") == (1, 4, 6)


def test_selected_batches_preserve_original_batch_identity() -> None:
    shots = tuple(range(1, 31))
    selected = diagnostic._selected_batches(
        shots,
        batch_size=5,
        requested=(1, 4, 6),
    )

    assert selected == (
        (1, (1, 2, 3, 4, 5)),
        (4, (16, 17, 18, 19, 20)),
        (6, (26, 27, 28, 29, 30)),
    )


def test_selected_batches_reject_out_of_range_batch() -> None:
    with pytest.raises(ValueError, match="outside valid range"):
        diagnostic._selected_batches(tuple(range(1, 31)), batch_size=5, requested=(7,))
