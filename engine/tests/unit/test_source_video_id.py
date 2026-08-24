"""F02 generate_source_video_id() 测试。"""

import re
from uuid import UUID

from engine.app.source_videos import generate_source_video_id

SOURCE_ID_PATTERN = re.compile(r"^SOURCE_[0-9a-f]{32}$")


def test_generate_source_video_id_has_stable_format() -> None:
    """Source ID 必须使用固定 SOURCE_ 前缀和 32 位小写 hex。"""

    source_id = generate_source_video_id()

    assert SOURCE_ID_PATTERN.fullmatch(source_id)


def test_generate_source_video_id_uses_uuid4() -> None:
    """去掉业务前缀后必须是 UUID4，而不是名称哈希或时间戳 ID。"""

    source_id = generate_source_video_id()
    uuid_value = UUID(hex=source_id.removeprefix("SOURCE_"))

    assert uuid_value.version == 4


def test_generate_source_video_id_does_not_repeat_in_batch() -> None:
    """批量生成时不应出现重复；数据库主键仍保留最终冲突保护。"""

    source_ids = {generate_source_video_id() for _ in range(5000)}

    assert len(source_ids) == 5000
