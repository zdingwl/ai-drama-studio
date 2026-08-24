from engine.app.media_v2 import _normalize_boundaries


def test_normalize_boundaries_filters_noise_and_keeps_full_duration() -> None:
    boundaries = _normalize_boundaries(
        5_000_000,
        [50_000, 1_000_000, 1_050_000, 3_500_000, 4_950_000],
    )
    assert boundaries == [0, 1_000_000, 3_500_000, 5_000_000]


def test_normalize_boundaries_returns_single_shot_when_no_cuts() -> None:
    assert _normalize_boundaries(2_000_000, []) == [0, 2_000_000]
