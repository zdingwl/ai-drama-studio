"""03 资产 Evidence 的可观测执行入口。

职责：
- 复用 content_analysis_v2 的正式 Run / Scene 数据模型；
- 人物正式身份链路为 Character V9C：Person Instance Split → Crop Safety → Multi-channel Person Features → Mature MOT → Person Gallery Identity；
- V9D Final Gate 只允许 Confirmed Person Gallery 物化 Final Character，Face 不是发布必需条件；
- 一帧多人先拆成独立 Person Instance，禁止整帧作为人物身份图；
- 每个单人人物图分别保留 ReID / clothing / body / optional Face 通道；
- 正式 Gallery 只允许 CLEAN Person Instance crop，并保存独立 feature sidecar；
- 身份采用 Confirm-then-Absorb：先确认 A，剩余全部先比 A；再确认 B，剩余全部比 A+B；
- MATCH 吸收，AMBIGUOUS 保留 UNRESOLVED，只有明确 DIFFERENT 且自身多 Shot 稳定的 Gallery 才能创建新人；
- partial / occluded / contaminated 只能挂回已确认 Gallery 或保留 Evidence，不能增加人物数量；
- 新 Run 完整成功后才切 Current，失败保留旧结果。
"""
from __future__ import annotations

import json
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

FORMAL_ASSET_PROFILE_VERSION = "f05-assets-v9d-confirmed-person-gallery-final-gate"
FORMAL_CHARACTER_COMPONENT_PROFILE = "V9D_CONFIRMED_PERSON_GALLERY_FINAL_GATE"


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
    """Keep both Run and component profile truthful after legacy persistence."""

    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None:
            return
        run.profile_version = FORMAL_ASSET_PROFILE_VERSION
        try:
            status = json.loads(run.component_status_json or "{}")
        except (json.JSONDecodeError, TypeError):
            status = {}
        if not isinstance(status, dict):
            status = {}
        status["characters_profile"] = FORMAL_CHARACTER_COMPONENT_PROFILE
        run.component_status_json = json.dumps(status, ensure_ascii=False)
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
        "characters_profile": FORMAL_CHARACTER_COMPONENT_PROFILE,
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
            f"已读取 {total_shots} 个 Current Shots，正在加载人物 V9C Person Gallery Identity / V9D Final Gate",
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
                "人物 V9C · Person Gallery / Confirm-then-Absorb",
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
            "人物 Gallery 身份确认完成",
            None,
            total_shots,
            total_shots,
            f"V9C Person Gallery：{resolved_count} 个已确认人物 · {unresolved_count} 个待解析 Evidence；V9D 仅发布已确认 Gallery",
        )

        _report(
            progress,
            87.0,
            "scenes",
            "连续场景 Evidence",
            None,
            0,
            total_shots,
            "人物 V9C 完成，正在计算 Scene Segment",
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
            f"正在保存 {resolved_count} 个 Confirmed Person Gallery、{unresolved_count} 个 Unresolved Evidence、{len(scenes)} 个 Scene Segment",
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
        # Legacy persistence writes its historical profile; restore the formal V9D asset contract.
        _mark_formal_profile(run_id)

        _report(
            progress,
            100.0,
            "evidence_ready",
            "Asset Evidence 完成",
            None,
            total_shots,
            total_shots,
            f"人物 V9D：{resolved_count} 个 Final-ready Confirmed Gallery · {unresolved_count} 个待解析 Evidence",
        )
        return get_analysis_run(run_id) or {"id": run_id, "status": "READY"}
    except Exception as exc:
        _fail_run(run_id, str(exc))
        raise
