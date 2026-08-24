"""F02 Source Video 导入业务。

当前先实现第一个核心函数 ``generate_source_video_id()``。
后续 F02 的流式写入、FFprobe、导入/读取/恢复继续集中在本文件，避免为了一个
Feature 提前拆出复杂 Media Service / Repository 层。
"""

from __future__ import annotations

from uuid import uuid4

SOURCE_VIDEO_ID_PREFIX = "SOURCE_"


def generate_source_video_id() -> str:
    """生成一份 Source Video 的稳定业务 ID。

    业务作用：
    - 用户正式开始导入原视频时，为这份原片建立与文件名无关的永久身份；
    - 该 ID 后续同时用于 ``source_videos.id`` 和 Workspace 内部目录名；
    - 后续 F03–F35 引用 Source 时应引用稳定 ID，而不是依赖用户原始文件名。

    为什么不能使用文件名：
    用户文件可能叫 ``第1集.mp4``、``final.mp4`` 或包含中文/空格/特殊字符，文件名既
    不唯一也不稳定，不适合作为数据库和目录 Contract。

    Returns:
        str: ``SOURCE_<32位UUID4小写hex>``，例如
        ``SOURCE_86f767c94f2c4f96a1676ce36f615406``。

    明确不负责：
    - 不访问 SQLite；
    - 不检查 Project；
    - 不创建 source/ 或 staging 目录；
    - 不读取视频文件；
    - 不调用 FFprobe；
    - 不负责最终数据库主键冲突处理，数据库 PRIMARY KEY 仍是最后一道保护。
    """

    return f"{SOURCE_VIDEO_ID_PREFIX}{uuid4().hex}"
