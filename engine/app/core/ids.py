"""F01 创建项目所需的稳定业务 ID 生成函数。

当前文件只负责生成 Project ID，不访问数据库、不创建目录、不写入项目文件。
项目 ID 一旦写入数据库和 ``project.json``，后续项目改名、移动素材或切换模型都不能改变它。
"""

from __future__ import annotations

import uuid

PROJECT_ID_PREFIX = "PROJECT_"
PROJECT_ID_HEX_LENGTH = 32


def generate_project_id() -> str:
    """生成一个新的稳定 Project 业务 ID。

    业务作用：
    - 为新项目提供与项目名称、视频名称、保存路径完全解耦的稳定主键；
    - 生成结果后续同时用于 ``projects.id`` 和 Project Workspace 目录名；
    - 用户创建同名项目时，仍然能够得到不同的项目身份。

    为什么使用 UUID4：
    F01 是本地单用户工具，不需要为了 ID 排序额外引入 ULID/雪花算法等依赖。
    UUID4 由 Python 标准库提供，足够简单且碰撞概率极低；数据库主键仍是最终冲突保护。

    Returns:
        str: ``PROJECT_`` 前缀加 32 位小写 UUID4 十六进制字符串，
        例如 ``PROJECT_86f767c94f2c4f96a1676ce36f615406``。

    安全边界：
    - 不读取或修改数据库；
    - 不检查 Workspace；
    - 不创建目录；
    - 不使用项目名称参与 ID 计算。
    """

    return f"{PROJECT_ID_PREFIX}{uuid.uuid4().hex}"
