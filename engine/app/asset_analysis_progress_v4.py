"""03 资产 Evidence 的可观测执行入口。

职责：
- 复用 content_analysis_v2 的正式 Run / 持久化逻辑，不复制业务数据模型；
- 把 Character V5 的逐 Shot progress callback 转换成统一资产进度；
- 明确暴露“准备 / 人物 Track+Gallery / 场景 / 保存”阶段，让 BackgroundTask 有真实心跳；
- 失败时仍由原 ContentAnalysisRun 规则保留旧 Current，不发布半成品。
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

    人物阶段占主要计算量，因此 5%~82% 使用 Character V5 实际 Shot 完成数映射。
    V5 每个 Shot 内会做更密集 Person Detection、Track、代表图与 Gallery 身份匹配；
    Shot 级百分比是真实处理顺序，不伪造模型内部每一次 forward 的百分比。
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
            f"已读取 {total_shots} 个 Current Shots，正在加载人物 V5 GPU-first 模型",
        )

        candidates: list[CandidateDraft] = []

        def character_progress(current: int, total: int, message: str) -> None:
            ratio = max(0.0, min(1.0, current / max(1, total)))
            shot = shots[current - 1] if 1 <= current <= len(shots) else None
            current_item = None
            if shot is not None:
                current_item = f"E{int(shot['episode_order']):02d} · SHOT {int(shot['ordinal']):04d}"
            _report(
                progress,
                5.0 + ratio * 77.0,
                "characters",
                "人物 V5 · Track / Gallery / Identity",
                current_item,
                current,
                total,
                message,
            )

        try:
            candidates = analyze_characters(shots, progress=character_progress)
            component_status["characters"] = "READY" if candidates else "NO_CHARACTER"
        except (ContentModelError, ImportError) as exc:
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
            "人物 Track / Character Gallery 完成，正在计算 Scene Segment",
        )
        scenes: list[SceneDraft] = _cluster_scenes(run_id, project_id, shots)
        component_status["scenes"] = "READY" if scenes else "NO_SCENE"

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
            f"正在保存 {len(candidates)} 个 Character Candidate、单人 Gallery、{len(scenes)} 个 Scene Segment 与 Shot Evidence",
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
            "人物 Track / Character Gallery / 场景基础 Evidence 已完成",
        )
        return get_analysis_run(run_id) or {"id": run_id, "status": "READY"}
    except Exception as exc:
        _fail_run(run_id, str(exc))
        raise
