"""03 资产 Evidence V4 的可观测执行入口。

职责：
- 复用 content_analysis_v2 的正式 Run / 持久化逻辑，不复制业务数据模型；
- 把 Character V4 已有的逐 Shot progress callback 转换成统一资产进度；
- 明确暴露“准备 / 人物 / 场景 / 保存”阶段，让 BackgroundTask 有真实心跳；
- 失败时仍由原 ContentAnalysisRun 规则保留旧 Current，不发布半成品。

为什么单独存在：旧 run_content_analysis() 是同步兼容入口，很多测试与历史代码仍依赖它。
正式 03 资产后台任务需要更细进度，因此在这一层增加 orchestration，而不改变旧调用契约。
"""
from __future__ import annotations

from typing import Callable

from engine.app.character_visual_v2 import CandidateDraft, analyze_characters
from engine.app.content_analysis_v2 import (
    ContentModelError,
    SceneDraft,
    _cluster_scenes,
    _create_run,
    _fail_run,
    _load_context,
    _persist_results,
    get_analysis_run,
)

AssetEvidenceProgress = Callable[
    [float, str, str, str | None, int | None, int | None, str],
    None,
]


def _report(
    progress: AssetEvidenceProgress | None,
    percent: float,
    stage_key: str,
    stage_label: str,
    current_item: str | None,
    current_index: int | None,
    total_items: int | None,
    message: str,
) -> None:
    if progress is not None:
        progress(
            max(0.0, min(100.0, float(percent))),
            stage_key,
            stage_label,
            current_item,
            current_index,
            total_items,
            message,
        )


def run_content_analysis_with_progress(
    project_id: str,
    *,
    progress: AssetEvidenceProgress | None = None,
) -> dict[str, object]:
    """执行基础资产 Evidence，并持续报告真实可计算进度。

    人物阶段占主要计算量，因此 5%~82% 使用 Character V4 实际 Shot 完成数映射。
    场景 descriptor / 聚类远轻于 YOLOX + ReID，目前以明确阶段心跳表示；持久化单独占尾段。
    这些百分比只用于同一次 Evidence Workflow 内的阶段权重，人物阶段内部比例来自真实 Shot 进度。
    """

    _project, _episodes, shots = _load_context(project_id)
    run_id = _create_run(project_id)
    component_status: dict[str, str] = {
        "characters": "PENDING",
        "scenes": "PENDING",
        "props": "NOT_CONFIGURED",
    }

    try:
        total_shots = len(shots)
        _report(
            progress,
            2.0,
            "asset_prepare",
            "准备资产 Evidence",
            None,
            0,
            total_shots,
            f"已读取 {total_shots} 个 Current Shots，正在加载人物 V4 模型",
        )

        candidates: list[CandidateDraft] = []

        def character_progress(current: int, total: int, message: str) -> None:
            # Character V4 每完成/开始一个真实 Shot 都会回调。人物是当前最重阶段，
            # 因此给它 5%~82% 的主进度区间。
            ratio = max(0.0, min(1.0, current / max(1, total)))
            shot = shots[current - 1] if 1 <= current <= len(shots) else None
            current_item = None
            if shot is not None:
                current_item = f"E{int(shot['episode_order']):02d} · SHOT {int(shot['ordinal']):04d}"
            _report(
                progress,
                5.0 + ratio * 77.0,
                "characters",
                "人物 V4 · Person / Face / ReID",
                current_item,
                current,
                total,
                message,
            )

        try:
            candidates = analyze_characters(shots, progress=character_progress)
            component_status["characters"] = "READY" if candidates else "NO_CHARACTER"
        except (ContentModelError, ImportError) as exc:
            # 保持旧兼容语义；RequiredCharacterModelError 不属于这里，会向外抛出，
            # 从而让 BackgroundTask FAILED 且旧 Current 保持不动。
            component_status["characters"] = "MODEL_NOT_READY"
            component_status["characters_detail"] = str(exc)

        _report(
            progress,
            84.0,
            "scenes",
            "连续场景 Evidence",
            None,
            0,
            total_shots,
            "人物 Evidence 完成，正在计算 Scene Segment",
        )
        scenes: list[SceneDraft] = _cluster_scenes(run_id, project_id, shots)
        component_status["scenes"] = "READY" if scenes else "NO_SCENE"

        # 03 不做对白/Speaker，保持与正式 content_analysis_v2 一致。
        dialogues: list[dict[str, object]] = []
        speaker_segments: list[dict[str, object]] = []

        _report(
            progress,
            94.0,
            "persist",
            "保存 Asset Evidence",
            None,
            total_shots,
            total_shots,
            f"正在保存 {len(candidates)} 个人物 Candidate、{len(scenes)} 个 Scene Segment 与 Shot Evidence",
        )
        _persist_results(
            run_id=run_id,
            project_id=project_id,
            shots=shots,
            candidates=candidates,
            scenes=scenes,
            dialogues=dialogues,
            speaker_segments=speaker_segments,
            component_status=component_status,
        )

        _report(
            progress,
            100.0,
            "evidence_ready",
            "Asset Evidence 完成",
            None,
            total_shots,
            total_shots,
            "人物 / 场景基础 Evidence 已完成",
        )
        return get_analysis_run(run_id) or {"id": run_id, "status": "READY"}
    except Exception as exc:
        _fail_run(run_id, str(exc))
        raise
