"""One-click automatic source understanding + localized remake preparation.

Accepted internal modules stay hidden behind one task. The task now runs through R7.1:
source understanding -> target assets -> target dialogue/TTS -> target remake timeline ->
H3-sized GenerationSegments. Only uncertain content becomes ReviewIssue; missing runtime
audio remains WAITING_AUDIO and blocks H3 submission without discarding prepared facts.
"""
from __future__ import annotations

from typing import Any

from engine.app.asset_analysis_progress_v4 import run_content_analysis_with_progress
from engine.app.asset_final_gate_v10 import apply_analysis_to_assets
from engine.app.asset_semantics_p4_v1 import enrich_asset_run, semantic_model_status
from engine.app.breakdown_p2_pipeline_v1 import run_episode_breakdown_p2
from engine.app.breakdown_serializer_v1 import get_current_breakdown
from engine.app.character_review_issue_sync_v1 import sync_character_review_issues
from engine.app.generation_segment_v1 import compile_generation_segments_v1
from engine.app.media_v2 import detect_episode_shots, preprocess_episode
from engine.app.remake_timeline_v1 import generate_remake_timeline_v1
from engine.app.review_issue_sync_v1 import sync_asset_review_issues, sync_shot_review_issues
from engine.app.review_issue_v1 import list_review_issues
from engine.app.source_drama_review_issue_sync_v1 import sync_source_drama_speaker_issues
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import get_episode, list_episode_records
from engine.app.target_dialogue_pipeline_v1 import run_target_dialogue_pipeline_v1
from engine.app.target_localization_runtime_guard_v1 import (
    require_target_localization_runtime_v1,
    validate_target_localization_generation_v1,
)
from engine.app.target_localization_v1 import generate_target_localization_v1
from engine.app.task_progress_v2 import fail_task, finish_task, start_task, update_task


def _has_current_breakdown(episode_id: str) -> bool:
    current = get_current_breakdown(episode_id)
    if not current:
        return False
    revision = current.get("source_shot_revision") or {}
    return bool(current.get("is_current")) and revision.get("is_current") is True


def run_auto_remake_prepare_task(task_id: str, project_id: str) -> None:
    try:
        episodes = list_episode_records(project_id)
        if not episodes:
            raise ValueError("项目还没有剧集")

        total = len(episodes)
        start_task(
            task_id,
            stage_key="auto_prepare",
            stage_label="自动理解并规划本土化短剧",
            message="将自动完成素材、拉片、目标人物/场景、目标对白/TTS、目标镜头时间轴和 H3 生成分段",
        )

        # 0-72%: episode media + source understanding.
        for index, episode_record in enumerate(episodes, start=1):
            episode = get_episode(episode_record.id)
            if episode is None:
                raise LookupError(f"剧集不存在：{episode_record.id}")
            base = (index - 1) / total * 72.0
            span = 72.0 / total
            label = f"第{int(episode['sort_order']):02d}集 · {episode['title']}"

            if episode.get("preprocess_status") != "READY":
                def media_progress(
                    percent: float,
                    stage_key: str,
                    message: str,
                    current: int | None,
                    inner_total: int | None,
                ) -> None:
                    update_task(
                        task_id,
                        progress_percent=base + span * 0.18 * (percent / 100.0),
                        stage_key=f"auto_{stage_key}",
                        stage_label="自动准备素材",
                        current_item=label,
                        current_index=index,
                        total_items=total,
                        message=message,
                    )

                preprocess_episode(episode["id"], progress=media_progress)

            episode = get_episode(episode_record.id) or episode
            if int(episode.get("shot_count") or 0) <= 0:
                def shot_progress(
                    percent: float,
                    stage_key: str,
                    message: str,
                    current: int | None,
                    inner_total: int | None,
                ) -> None:
                    update_task(
                        task_id,
                        progress_percent=base + span * (0.18 + 0.32 * (percent / 100.0)),
                        stage_key=f"auto_{stage_key}",
                        stage_label="自动识别镜头",
                        current_item=label,
                        current_index=index,
                        total_items=total,
                        message=message,
                    )

                detect_episode_shots(episode["id"], progress=shot_progress)
            else:
                update_task(
                    task_id,
                    progress_percent=base + span * 0.50,
                    stage_key="auto_reuse_shots",
                    stage_label="复用已确认镜头",
                    current_item=label,
                    current_index=index,
                    total_items=total,
                    message=f"{label} 已有 Current Shots，不重复切镜",
                )

            if not _has_current_breakdown(episode["id"]):
                def breakdown_progress(percent: float, stage: str, message: str) -> None:
                    update_task(
                        task_id,
                        progress_percent=base + span * (0.50 + 0.50 * (percent / 100.0)),
                        stage_key=f"auto_{stage}",
                        stage_label="自动理解剧情与镜头",
                        current_item=label,
                        current_index=index,
                        total_items=total,
                        message=message,
                    )

                run_episode_breakdown_p2(episode["id"], progress=breakdown_progress)
            else:
                update_task(
                    task_id,
                    progress_percent=base + span,
                    stage_key="auto_reuse_breakdown",
                    stage_label="复用当前拉片结果",
                    current_item=label,
                    current_index=index,
                    total_items=total,
                    message=f"{label} 当前拉片结果仍匹配 Current Shots，直接复用",
                )

        # 72-96%: project-level Character / Scene / Prop extraction.
        def asset_progress(
            percent: float,
            stage_key: str,
            stage_label: str,
            current_item: str | None,
            current_index: int | None,
            total_items: int | None,
            message: str,
        ) -> None:
            update_task(
                task_id,
                progress_percent=72.0 + percent * 0.18,
                stage_key=f"auto_{stage_key}",
                stage_label=stage_label,
                current_item=current_item,
                current_index=current_index,
                total_items=total_items,
                message=message,
            )

        analysis = run_content_analysis_with_progress(project_id, progress=asset_progress)
        run_id = str(analysis["id"])
        semantic = semantic_model_status()
        semantic_result: dict[str, Any] = {"status": "NOT_CONFIGURED"}
        if semantic.get("ready"):
            update_task(
                task_id,
                progress_percent=90.0,
                stage_key="auto_asset_semantics",
                stage_label="自动验证场景与道具",
                message="正在结合拉片上下文验证场景 / 道具",
            )

            def semantic_progress(current: int, semantic_total: int, message: str) -> None:
                update_task(
                    task_id,
                    progress_percent=90.0 + current / max(1, semantic_total) * 5.0,
                    stage_key="auto_asset_semantics",
                    stage_label="自动验证场景与道具",
                    current_item=f"Shot {current} / {semantic_total}",
                    current_index=current,
                    total_items=semantic_total,
                    message=message,
                )

            semantic_result = enrich_asset_run(run_id, project_id, progress=semantic_progress)

        update_task(
            task_id,
            progress_percent=96.0,
            stage_key="auto_review_sync",
            stage_label="整理源片待确认问题",
            message="高置信度结果自动通过；原始人物 Evidence 只保留在内部，只有真实镜头/资产冲突才进入待确认",
        )
        workspace = apply_analysis_to_assets(project_id, run_id)
        shot_issue_count = sync_shot_review_issues(project_id)
        character_issue_count = sync_character_review_issues(project_id, run_id)
        asset_issue_count = sync_asset_review_issues(project_id, workspace)

        update_task(
            task_id,
            progress_percent=97.0,
            stage_key="auto_source_snapshot",
            stage_label="形成统一原片快照",
            message="正在把 Scene / Shot / 人物 / 场景 / 道具 / 对白 / Reference Video 收敛为 SourceDramaSnapshot",
        )
        source_snapshot = load_project_source_drama_snapshot_v1(project_id)
        speaker_issue_count = sync_source_drama_speaker_issues(project_id, source_snapshot)

        update_task(
            task_id,
            progress_percent=97.8,
            stage_key="auto_target_localization",
            stage_label="自动设计目标人物与场景",
            message="正在按目标语言、地区和场景策略生成 TargetCharacter / SceneLocalizationMapping",
        )
        require_target_localization_runtime_v1(project_id)
        target_localization = validate_target_localization_generation_v1(
            project_id,
            generate_target_localization_v1(project_id),
        )
        target_review_count = int(target_localization.get("review_count") or 0)

        update_task(
            task_id,
            progress_percent=98.6,
            stage_key="auto_target_dialogue",
            stage_label="自动生成目标对白与声音",
            message="正在翻译/本土化对白；READY 台词会尽量生成固定角色声音和真实语音时长",
        )
        target_dialogue = run_target_dialogue_pipeline_v1(project_id, synthesize_audio=True)
        dialogue_review_count = int(target_dialogue.get("review_count") or 0)

        update_task(
            task_id,
            progress_percent=99.2,
            stage_key="auto_remake_timeline",
            stage_label="自动规划目标镜头时间",
            message="正在根据真实目标语音时长自动 KEEP / TRIM / 借反应镜 / EXTEND；极端时长才进入待确认",
        )
        remake_timeline = generate_remake_timeline_v1(project_id)
        timing_review_count = int(remake_timeline.get("review_count") or 0)
        timing_waiting_audio_count = int(remake_timeline.get("waiting_audio_count") or 0)

        update_task(
            task_id,
            progress_percent=99.7,
            stage_key="auto_generation_segments",
            stage_label="编译 H3 生成分段",
            message="正在把目标时间轴编译为符合 H3 4-15 秒运行约束的 GenerationSegment；长镜头自动拆段，短镜头保留后裁剪计划",
        )
        generation_segments = compile_generation_segments_v1(project_id)
        generation_segment_review_count = int(generation_segments.get("review_count") or 0)
        generation_segment_waiting_audio_count = int(generation_segments.get("waiting_audio_count") or 0)

        # Timing generation may add DIALOGUE_TIMING issues, so count the final open queue here.
        open_issues = list_review_issues(project_id, status="OPEN")
        review_issue_count = len(open_issues)

        warnings: list[str] = []
        unresolved = int((analysis.get("counts") or {}).get("unresolved_character_candidates") or character_issue_count)
        if unresolved:
            warnings.append(f"{unresolved} 个人物 Evidence 尚未形成安全身份，已保留为内部证据；不会仅因此增加人工待确认")
        if semantic_result.get("status") in {"FAILED", "READY_WITH_WARNINGS", "NOT_CONFIGURED"}:
            warnings.append("场景 / 道具语义验证存在降级")
        if source_snapshot.get("status") == "READY_WITH_WARNINGS":
            warnings.append("SourceDramaSnapshot 已形成，但仍包含需要下游尊重的源片警告")
        if speaker_issue_count:
            warnings.append(f"{speaker_issue_count} 条对白在自动上下文解析后仍需要确认说话人")
        if target_review_count:
            warnings.append(f"{target_review_count} 项目标人物/场景本土化需要人工确认")
        if dialogue_review_count:
            warnings.append(f"{dialogue_review_count} 条目标对白尚未形成安全可用文本")
        if target_dialogue.get("audio_ready_count", 0) < target_dialogue.get("dialogue_count", 0):
            warnings.append("部分目标对白 TTS 音频尚未生成；已完成文本继续保留")
        if timing_waiting_audio_count:
            warnings.append(f"{timing_waiting_audio_count} 个镜头等待真实 TTS 时长后再确定目标时长")
        if timing_review_count:
            warnings.append(f"{timing_review_count} 个镜头时长变化过大，需要人工确认")
        if generation_segment_waiting_audio_count:
            warnings.append(f"{generation_segment_waiting_audio_count} 个 H3 生成分段等待目标语音 READY")
        if generation_segment_review_count:
            warnings.append(f"{generation_segment_review_count} 个 H3 生成分段仍有上游阻塞，不能提交生成")

        result = {
            "project_id": project_id,
            "episode_count": total,
            "asset_run_id": run_id,
            "review_issue_count": review_issue_count,
            "shot_review_issue_count": shot_issue_count,
            "character_review_issue_count": character_issue_count,
            "asset_review_issue_count": asset_issue_count,
            "speaker_review_issue_count": speaker_issue_count,
            "target_localization_review_item_count": target_review_count,
            "target_dialogue_review_item_count": dialogue_review_count,
            "dialogue_timing_review_item_count": timing_review_count,
            "dialogue_timing_waiting_audio_count": timing_waiting_audio_count,
            "generation_segment_review_item_count": generation_segment_review_count,
            "generation_segment_waiting_audio_count": generation_segment_waiting_audio_count,
            "unresolved_character_evidence": unresolved,
            "semantic": semantic_result,
            "source_snapshot": {
                "schema_version": source_snapshot["schema_version"],
                "status": source_snapshot["status"],
                "source_fingerprint": source_snapshot["source_fingerprint"],
                "scene_count": source_snapshot["scene_count"],
                "shot_count": source_snapshot["shot_count"],
                "resolved_character_count": source_snapshot["resolved_character_count"],
                "source_dialogue_count": source_snapshot["source_dialogue_count"],
            },
            "target_localization": {
                "schema_version": target_localization["schema_version"],
                "status": target_localization["status"],
                "target_character_count": target_localization["target_character_count"],
                "scene_mapping_count": target_localization["scene_mapping_count"],
                "review_count": target_review_count,
            },
            "target_dialogue": {
                "schema_version": target_dialogue["schema_version"],
                "status": target_dialogue["status"],
                "voice_profile_count": target_dialogue["voice_profile_count"],
                "dialogue_count": target_dialogue["dialogue_count"],
                "review_count": dialogue_review_count,
                "audio_ready_count": target_dialogue["audio_ready_count"],
            },
            "remake_timeline": {
                "schema_version": remake_timeline["schema_version"],
                "status": remake_timeline["status"],
                "episode_count": remake_timeline["episode_count"],
                "review_count": timing_review_count,
                "waiting_audio_count": timing_waiting_audio_count,
                "target_dialogue_fingerprint": remake_timeline["target_dialogue_fingerprint"],
            },
            "generation_segments": {
                "schema_version": generation_segments["schema_version"],
                "status": generation_segments["status"],
                "episode_count": generation_segments["episode_count"],
                "segment_count": generation_segments["segment_count"],
                "review_count": generation_segment_review_count,
                "waiting_audio_count": generation_segment_waiting_audio_count,
                "upstream_fingerprint": generation_segments["upstream_fingerprint"],
            },
        }
        finish_task(
            task_id,
            result=result,
            message=(
                f"自动处理已完成到 H3 生成分段：{review_issue_count} 项需要人工确认"
                if review_issue_count
                else "自动处理已完成到 H3 生成分段：当前无需人工确认"
            ),
            status="READY_WITH_WARNINGS" if warnings or review_issue_count else "READY",
        )
    except Exception as exc:
        fail_task(task_id, exc)


__all__ = ["run_auto_remake_prepare_task"]
