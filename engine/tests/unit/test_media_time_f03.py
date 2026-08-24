"""F03 公共媒体时间换算测试。"""

from decimal import Decimal

import pytest

from engine.app.core.media_time import (
    derived_to_source_microseconds,
    microseconds_to_pts,
    pts_to_microseconds,
    seconds_to_microseconds,
    source_to_derived_microseconds,
)


def test_seconds_to_microseconds_keeps_decimal_precision_and_half_up_rule() -> None:
    """FFprobe 十进制秒值必须稳定转换，半微秒正负都远离 0 取整。"""

    assert seconds_to_microseconds("12.345678") == 12_345_678
    assert seconds_to_microseconds(Decimal("0.0000005")) == 1
    assert seconds_to_microseconds(Decimal("-0.0000005")) == -1


def test_seconds_to_microseconds_rejects_nonfinite_value() -> None:
    """NaN/Infinity 不能进入权威 Source Timeline。"""

    with pytest.raises(ValueError):
        seconds_to_microseconds("NaN")


def test_pts_round_trip_for_90khz_time_base() -> None:
    """常见 1/90000 time_base 的可表示时间点必须 PTS→us→PTS 稳定。"""

    assert pts_to_microseconds(90_090, 1, 90_000) == 1_001_000
    assert microseconds_to_pts(1_001_000, 1, 90_000) == 90_090


def test_negative_pts_round_trip_is_supported() -> None:
    """媒体可能存在负起始 timestamp，公共换算不能强制截断为 0。"""

    microseconds = pts_to_microseconds(-45_045, 1, 90_000)
    assert microseconds == -500_500
    assert microseconds_to_pts(microseconds, 1, 90_000) == -45_045


def test_source_derived_offset_mapping_is_exactly_reversible() -> None:
    """纯整数 offset 映射本身必须 0 误差 round-trip。"""

    offset_us = 1_250_000
    for derived_us in (0, 1, 999, 5_000_000, 123_456_789):
        source_us = derived_to_source_microseconds(derived_us, offset_us)
        assert source_to_derived_microseconds(source_us, offset_us) == derived_us


def test_invalid_time_base_is_rejected() -> None:
    """0 分子/非正分母不能被当成合法媒体 time_base。"""

    with pytest.raises(ValueError):
        pts_to_microseconds(1, 0, 1000)
    with pytest.raises(ValueError):
        microseconds_to_pts(1, 1, 0)
