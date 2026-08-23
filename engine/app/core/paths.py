"""F01 创建项目所需的应用路径基础函数。

当前文件只负责解析路径，不创建目录、不写数据库、不创建项目。
F01 第一阶段先从应用数据目录开始，后续 ``app.db`` 会保存在这里。
"""

from __future__ import annotations

import os
from pathlib import Path

APP_DATA_OVERRIDE_ENV = "AI_DRAMA_APP_DATA_DIR"
WINDOWS_LOCAL_APP_DATA_ENV = "LOCALAPPDATA"
APP_DATA_FOLDER_NAME = "AI Drama Studio"


def get_app_data_path() -> Path:
    """返回 AI Drama Studio 的应用级数据目录。

    业务作用：
    - 后续 F01 的 ``app.db`` 和应用级日志都从这个目录定位；
    - 测试环境可以通过 ``AI_DRAMA_APP_DATA_DIR`` 指向临时目录，避免污染真实用户数据；
    - 正式 Windows 环境未设置覆盖值时，使用 ``%LOCALAPPDATA%/AI Drama Studio``。

    为什么这里只“解析路径”而不创建目录：
    路径解析和文件系统写入是两件事。这个函数保持无副作用，便于单独测试，
    真正创建目录由后续数据库初始化流程负责。

    Returns:
        Path: 规范化后的应用数据目录绝对路径。

    Raises:
        RuntimeError: 没有测试覆盖路径，且当前系统无法读取 ``LOCALAPPDATA`` 时抛出。
            F01 以 Windows 为正式运行环境，因此这种情况应明确暴露，而不是偷偷写到未知位置。
    """

    override = os.getenv(APP_DATA_OVERRIDE_ENV)
    if override and override.strip():
        return Path(override.strip()).expanduser().resolve(strict=False)

    local_app_data = os.getenv(WINDOWS_LOCAL_APP_DATA_ENV)
    if not local_app_data or not local_app_data.strip():
        raise RuntimeError(
            "无法确定 AI Drama Studio 应用数据目录："
            "未设置 AI_DRAMA_APP_DATA_DIR，且当前环境缺少 LOCALAPPDATA。"
        )

    return (Path(local_app_data.strip()) / APP_DATA_FOLDER_NAME).expanduser().resolve(
        strict=False
    )
