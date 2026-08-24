"""AI Drama Studio Source Domain 公共媒体时间换算工具。

业务目的：
- 统一 FFprobe/FFmpeg 秒值 → 整数微秒；
- 统一 PTS + rational time_base ↔ 整数微秒；
- 统一 Proxy/Audio ↔ Source Timeline 的 offset 映射；
- 防止 F03/F04/F08 等模块各自重复实现时间换算并产生舍入差异。

权威规则来自 ``docs/MEDIA_TIMEBASE_CONTRACT.md``：数据库和业务层以整数微秒为权威，
不能把 float 秒或 ``frame_index / fps`` 当作唯一时间依据。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction

MICROSECONDS_PER_SECOND = 1_000_000


def seconds_to_microseconds(value: str | int | float | Decimal) -> int:
    """把 FFprobe/FFmpeg 秒值稳定转换为整数微秒。

    为什么使用 Decimal：
    FFprobe JSON 经常以字符串输出 ``12.345678``。如果先转成二进制 float 再乘 1e6，
    会把本来可以精确表示的十进制时间引入额外误差。因此公共入口统一通过 Decimal。

    舍入规则：
    精确落在半微秒时使用 ROUND_HALF_UP，也就是正负数都远离 0 取整。这个规则必须
    在所有 Feature 中保持一致，禁止业务模块自己 ``round(seconds, 2)``。
    """

    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"无效秒值: {value!r}") from exc

    if not decimal_value.is_finite():
        raise ValueError("秒值必须是有限数")

    return int(
        (decimal_value * MICROSECONDS_PER_SECOND).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def _round_fraction_half_away_from_zero(value: Fraction) -> int:
    """把 Fraction 按 half-away-from-zero 规则舍入为整数。

    这是内部 helper，只用于 rational time_base 的精确整数换算，不承担业务语义。
    """

    numerator = value.numerator
    denominator = value.denominator
    sign = -1 if numerator < 0 else 1
    absolute_numerator = abs(numerator)
    quotient, remainder = divmod(absolute_numerator, denominator)
    if remainder * 2 >= denominator:
        quotient += 1
    return sign * quotient


def pts_to_microseconds(
    pts: int,
    time_base_num: int,
    time_base_den: int,
) -> int:
    """将媒体 PTS 按 rational time_base 转为权威整数微秒。

    例如 time_base=1/90000 时，不能先转 float 秒再计算；这里直接用 Fraction 保留精度。
    支持负 PTS，因为部分媒体流可能存在负起始 timestamp。
    """

    if time_base_num == 0 or time_base_den <= 0:
        raise ValueError("time_base 必须满足 num != 0 且 den > 0")

    return _round_fraction_half_away_from_zero(
        Fraction(
            pts * time_base_num * MICROSECONDS_PER_SECOND,
            time_base_den,
        )
    )


def microseconds_to_pts(
    microseconds: int,
    time_base_num: int,
    time_base_den: int,
) -> int:
    """把整数微秒映射到最接近的媒体 PTS。

    主要用于边界定位和 Source↔Proxy round-trip 测试。由于媒体 time_base 本身存在量化粒度，
    任意微秒值不保证可以无损变回同一个微秒，但“PTS → us → PTS”应在可表示点稳定。
    """

    if time_base_num == 0 or time_base_den <= 0:
        raise ValueError("time_base 必须满足 num != 0 且 den > 0")

    return _round_fraction_half_away_from_zero(
        Fraction(
            microseconds * time_base_den,
            time_base_num * MICROSECONDS_PER_SECOND,
        )
    )


def derived_to_source_microseconds(derived_us: int, offset_us: int) -> int:
    """把 Proxy/Audio 的局部时间映射回 Source Timeline。

    F03 冻结线性 offset 公式：

    ``source_us = derived_us + offset_us``

    本函数不判断 derived_us 是否落在具体媒体时长内；资产边界由调用它的业务函数校验。
    """

    return derived_us + offset_us


def source_to_derived_microseconds(source_us: int, offset_us: int) -> int:
    """把 Source Timeline 时间映射到 Proxy/Audio 局部时间。

    F03 冻结逆公式：

    ``derived_us = source_us - offset_us``
    """

    return source_us - offset_us
