"""Product-facing SourceDramaSnapshot reads plus explicit source-screenplay commands."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engine.app.breakdown_read_model_v1 import BreakdownReadModelError
from engine.app.breakdown_scene_timeline_assembler_v1 import SceneTimelineAssemblyError
from engine.app.breakdown_scene_timeline_result_v1 import SceneTimelineResultError
from engine.app.local_qwen_text_v1 import LocalQwenTextError
from engine.app.source_drama_snapshot_contract_v1 import (
    SourceDramaEpisodeSnapshotV1,
    SourceDramaProjectSnapshotV1,
)
from engine.app.source_drama_snapshot_v1 import (
    SourceDramaSnapshotError,
    load_episode_source_drama_snapshot_v1,
    load_project_source_drama_snapshot_v1,
)
from engine.app.source_screenplay_runtime_v2 import (
    SourceScreenplayReadV1,
    compile_source_screenplay_v2,
    persist_source_screenplay_v1,
    read_source_screenplay_v1,
)
from engine.app.source_story_skills_v1 import SourceScreenplayCompilationV1, SourceStorySkillError


router = APIRouter(prefix="/api", tags=["source-drama-snapshot"])


def _unavailable(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(
        status_code=409,
        detail="SourceDramaSnapshot 当前不可用，请先完成自动理解并处理阻塞性的镜头/资产问题。",
    )


def _load_current_snapshot(episode_id: str) -> SourceDramaEpisodeSnapshotV1:
    snapshot = load_episode_source_drama_snapshot_v1(episode_id)
    if snapshot is None:
        raise SourceDramaSnapshotError("当前 Episode 尚未形成可消费的 SourceDramaSnapshot")
    return snapshot


@router.get(
    "/episodes/{episode_id}/source-drama-snapshot",
    response_model=SourceDramaEpisodeSnapshotV1,
)
def api_get_episode_source_drama_snapshot(episode_id: str):
    try:
        return _load_current_snapshot(episode_id)
    except (
        LookupError,
        SourceDramaSnapshotError,
        BreakdownReadModelError,
        SceneTimelineResultError,
        SceneTimelineAssemblyError,
        ValueError,
    ) as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/projects/{project_id}/source-drama-snapshot",
    response_model=SourceDramaProjectSnapshotV1,
)
def api_get_project_source_drama_snapshot(project_id: str):
    try:
        return load_project_source_drama_snapshot_v1(project_id)
    except (
        LookupError,
        SourceDramaSnapshotError,
        BreakdownReadModelError,
        SceneTimelineResultError,
        SceneTimelineAssemblyError,
        ValueError,
    ) as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/episodes/{episode_id}/source-screenplay",
    response_model=SourceScreenplayReadV1,
)
def api_get_episode_source_screenplay(episode_id: str):
    """Read the latest materialized screenplay without starting any model."""

    try:
        snapshot = _load_current_snapshot(episode_id)
        return read_source_screenplay_v1(snapshot)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        SourceDramaSnapshotError,
        BreakdownReadModelError,
        SceneTimelineResultError,
        SceneTimelineAssemblyError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail="原片事实尚未冻结，当前不能读取原片还原剧本。",
        ) from exc
    except SourceStorySkillError as exc:
        raise HTTPException(
            status_code=409,
            detail="已保存的原片还原剧本无效，请显式重新生成。",
        ) from exc


@router.post(
    "/episodes/{episode_id}/source-screenplay/compile",
    response_model=SourceScreenplayCompilationV1,
)
def api_compile_episode_source_screenplay(episode_id: str):
    """Explicitly run shot facts -> episode understanding -> grounded screenplay plan.

    This is intentionally POST-only because the understanding and screenplay-planning
    steps may invoke local Qwen. The accepted derived artifact is materialized separately;
    no model output is ever written back into SourceDramaSnapshot/source fact tables.
    """

    try:
        snapshot = _load_current_snapshot(episode_id)
        compilation = compile_source_screenplay_v2(snapshot)
        persist_source_screenplay_v1(snapshot, compilation)
        return compilation
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        SourceDramaSnapshotError,
        BreakdownReadModelError,
        SceneTimelineResultError,
        SceneTimelineAssemblyError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail="原片事实尚未冻结，当前不能生成原剧本。请先处理阻塞性的原片问题。",
        ) from exc
    except (LocalQwenTextError, SourceStorySkillError) as exc:
        raise HTTPException(
            status_code=503,
            detail="原片剧情理解或剧本整理当前不可用，或输出未通过事实门禁；没有修改任何原片事实。",
        ) from exc


__all__ = [
    "api_compile_episode_source_screenplay",
    "api_get_episode_source_drama_snapshot",
    "api_get_episode_source_screenplay",
    "api_get_project_source_drama_snapshot",
    "router",
]
