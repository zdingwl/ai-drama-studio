"""03 资产 Evidence 的可观测执行入口。

职责：
- 复用 content_analysis_v2 的正式 Run / Scene 数据模型；
- 人物正式链路为 Character V7：12fps Person + Partial → Safe Face Ownership → Mature MOT → Face-first Global Identity；
- Face observation 是唯一身份节点；Person Track 数量不再决定 Final Character 数量；
- partial/body-only 只能在稳定 Face Identity 建立以后挂回，否则只保留 UNRESOLVED Evidence；
- RESOLVED / UNRESOLVED 在持久化时明确分层，只有 RESOLVED 后续可形成 Final Character；
- 新 Run 完整成功后才切 Current，失败保留旧结果。
"""
from __future__ import annotations

from typing import Callable

from engine.app.character_visual_v2 import CandidateDraft, analyze_characters
from engine.app.character_persistence_v6 import persist_results_v6
from engine.app.content_analysis_v2 import (
    ContentAnalysisRun,
    SceneDraft,
    _cluster_scenes,
    _create_run,
    _fail_run,
    _load_context,
    get_analysis_run,
)
from engine.app.studio_v2 import get_session

AssetEvidenceProgress = Callable[
    [float, str, str, str | None, int | None, int | None, str],
    None,
]

FORMAL_ASSET_PROFILE_VERSION = "f05-assets-v7-face-first-global-identity"


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


def _mark_formal_profile(run_id: str) -> None:
    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None:
            return
        run.profile_version = FORMAL_ASSET_PROFILE_VERSION
        session.commit()


def run_content_analysis_with_progress(
    project_id: str,
    *,
    progress: AssetEvidenceProgress | None = None,
) -> dict[str, object]:
    """执行基础资产 Evidence，并持续报告真实可计算进度。"""

    _project, _episodes, shots = _load_context(project_id)
    run_id = _create_run(project_id)
    _mark_formal_profile(run_id)
    component_status: dict[str, str] = {
        "characters": "PENDING",
        "characters_profile": "V7_FACE_FIRST_GLOBAL_IDENTITY",
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
            f"已读取 {total_shots} 个 Current Shots，正在加载人物 V7 Safe Face / MOT / Face-first Identity",
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
                "人物 V7 · Safe Face / MOT / Face-first Global Identity",
                current_item,
                current,
                total,
                message,
            )

        candidates = analyze_characters(shots, progress=character_progress)
        resolved_count = sum(1 for item in candidates if item.identity_status == "RESOLVED")
        unresolved_count = len(candidates) - resolved_count
        component_status["characters"] = "READY" if candidates else "NO_CHARACTER"
        component_status["resolved_characters"] = str(resolved_count)
        component_status["unresolved_character_evidence"] = str(unresolved_count)

        _report(
            progress,
            84.0,
            "identity_resolve",
            "全局人物身份解析完成",
            None,
            total_shots,
            total_shots,
            f"Face-first Identity V7：{resolved_count} 个可发布人物 · {unresolved_count} 个待解析 Evidence",
        )

        _report(
            progress,
            87.0,
            "scenes",
            "连续场景 Evidence",
            None,
            0,
            total_shots,
            "人物 V7 完成，正在计算 Scene Segment",
        )
        scenes: list[SceneDraft] = _cluster_scenes(run_id, project_id, shots)
        component_status["scenes"] = "READY" if scenes else "NO_SCENE"

        dialogues: list[dict[str, object]] = []
        speaker_segments: list[dict[str, object]] = []

        _report(
            progress,
            95.0,
            "persist",
            "保存 Asset Evidence",
            None,
            total_shots,
            total_shots,
            f"正在保存 {resolved_count} 个 RESOLVED Character、{unresolved_count} 个 Unresolved Evidence、{len(scenes)} 个 Scene Segment",
        )
        persist_results_v6(
            run_id=run_id,
            project_id=project_id,
            shots=shots,
            candidates=candidates,
            scenes=scenes,
            dialogues=dialogues,
            speaker_segments=speaker_segments,
            component_status=component_status,
        )
        # persistence 模块仍兼容历史调用；正式入口最终覆盖为 V7 profile。
        _mark_formal_profile(run_id)

        _report(
            progress,
            100.0,
            "evidence_ready",
            "Asset Evidence 完成",
            None,
            total_shots,
            total_shots,
            f"人物 V7 完成：{resolved_count} Final-ready · {unresolved_count} 待解析 Evidence",
        )
        return get_analysis_run(run_id) or {"id": run_id, "status": "READY"}
    except Exception as exc:
        _fail_run(run_id, str(exc))
        raise
