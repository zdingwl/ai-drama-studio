"""F01 Project ID 生成函数测试。"""

import uuid

from engine.app.core.ids import (
    PROJECT_ID_HEX_LENGTH,
    PROJECT_ID_PREFIX,
    generate_project_id,
)


def test_generate_project_id_has_stable_format() -> None:
    """Project ID 必须始终保持已确认的 PROJECT_<32位hex> Contract。"""

    project_id = generate_project_id()
    suffix = project_id.removeprefix(PROJECT_ID_PREFIX)

    assert project_id.startswith(PROJECT_ID_PREFIX)
    assert len(suffix) == PROJECT_ID_HEX_LENGTH
    assert suffix == suffix.lower()
    assert all(character in "0123456789abcdef" for character in suffix)


def test_generate_project_id_contains_uuid4() -> None:
    """前缀后的 32 位内容必须来自 UUID4，而不是名称、时间戳或路径。"""

    project_id = generate_project_id()
    suffix = project_id[len(PROJECT_ID_PREFIX) :]
    parsed = uuid.UUID(hex=suffix)

    assert parsed.version == 4


def test_generate_project_id_is_unique_in_batch() -> None:
    """批量生成时不应出现重复；数据库主键仍负责最终冲突保护。"""

    generated_ids = {generate_project_id() for _ in range(5000)}

    assert len(generated_ids) == 5000
