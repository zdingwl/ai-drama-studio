"""用户级 Workflow 01「导入原片」编排层。

用户只点击一次“创建并导入”，但底层继续复用已经冻结的 F01/F02/F03 业务能力：

create_project()
→ import_source_video()
→ preprocess_source_video()

本文件只负责编排，不复制 Project SQL、上传写盘、FFprobe、FFmpeg 或预处理算法。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from starlette.concurrency import run_in_threadpool

from engine.app.preprocess import SourcePreprocessRecord, preprocess_source_video
from engine.app.projects import ProjectRecord, create_project
from engine.app.source_videos import AsyncReadableUpload, SourceVideoRecord, import_source_video


@dataclass(frozen=True)
class ProjectImportWorkflowRecord:
    """一次完整“创建项目 + 导入原片 + 初始化分析资产”的用户级结果。

    业务含义：只有返回该对象时，Workflow 01 才算完成。Project / Source / Preprocess
    仍然各自保持原有稳定业务 ID 和数据库记录，本对象不创建第四份重复 Source of Truth。
    """

    status: str
    project: ProjectRecord
    source_video: SourceVideoRecord
    preprocess: SourcePreprocessRecord

    def to_dict(self) -> dict[str, Any]:
        """转换为 Controller 可直接返回的嵌套字典。"""

        return {
            "status": self.status,
            "project": asdict(self.project),
            "source_video": asdict(self.source_video),
            "preprocess": asdict(self.preprocess),
        }


async def import_project_source_workflow(
    *,
    name: str,
    target_language: str,
    target_region: str,
    upload_file: AsyncReadableUpload,
    original_filename: str,
    source_language: str | None = None,
    workspace_root: str | Path | None = None,
    app_data_path: Path | None = None,
) -> ProjectImportWorkflowRecord:
    """一次完成新项目的创建、原片导入和分析资产初始化。

    输入：
    - 项目名称、语言/地区、Workspace Root；
    - 用户选择的原片上传流和原始文件名。

    输出：
    - ready Project；
    - ready Source Video；
    - ready Source Preprocess（Proxy / WAV / Thumbnail / Time Mapping）。

    为什么存在：
    用户流程不应该暴露 F01/F02/F03 三个技术步骤。这个函数把它们编排成一个用户动作，
    但每一步仍由原 Feature Service 自己负责校验、事务、文件发布与恢复。

    线程规则：
    - ``import_source_video()`` 保持 async，继续按上传流分块读写；
    - ``create_project()`` 和 ``preprocess_source_video()`` 是同步文件/FFmpeg 工作，放入线程池，
      避免一个长视频初始化期间把 FastAPI 事件循环完全堵住。

    失败规则：
    - 不在这里递归删除 Project Workspace，也不绕过 F01/F02/F03 的安全恢复规则；
    - 如果后一步失败，前一步已经安全发布的数据继续保留，便于启动恢复或后续重试；
    - 不为了制造“伪原子性”删除已经正式发布的 Source Video。

    不能做：
    - 不直接 SQL；
    - 不自己 FFprobe / FFmpeg；
    - 不执行 Shot Detection；
    - 不修改 F01/F02/F03 的冻结数据 Contract。
    """

    project = await run_in_threadpool(
        create_project,
        name=name,
        source_language=source_language,
        target_language=target_language,
        target_region=target_region,
        workspace_root=workspace_root,
        app_data_path=app_data_path,
    )

    source_video = await import_source_video(
        project_id=project.id,
        upload_file=upload_file,
        original_filename=original_filename,
        app_data_path=app_data_path,
    )

    preprocess = await run_in_threadpool(
        preprocess_source_video,
        project_id=project.id,
        app_data_path=app_data_path,
    )

    return ProjectImportWorkflowRecord(
        status="ready",
        project=project,
        source_video=source_video,
        preprocess=preprocess,
    )
