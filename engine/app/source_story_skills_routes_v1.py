"""Explicit command API for the source story Skill chain.

The compile endpoint is POST-only because episode_understanding may dispatch the local
Qwen runtime. No GET/page-read path is allowed to trigger this work.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engine.app.breakdown_read_model_v1 import BreakdownReadModelError
from engine.app.breakdown_scene_timeline_assembler_v1 import SceneTimelineAssemblyError
from engine.app.breakdown_scene_timeline_result_v1 import SceneTimelineResultError
from engine.app.local_qwen_text_v1 import LocalQwenTextError
from engine.app.source_drama_snapshot_v1 import (
    SourceDramaSnapshotError,
    load_episode_source_drama_snapshot_v1,
)
from engine.app.source_story_skills_v1 import (
    SourceScreenplayCompilationV1,
    SourceStorySkillError,
    compile_source_screenplay_v1,
)

router = APIRouter(prefix="/api", tags=["source-screenplay"])


@router.post(
    "/episodes/{episode_id}/source-screenplay/compile",
    response_model=SourceScreenplayCompilationV1,
)
def api_compile_episode_source_screenplay(episode_id: str):
    try:
        snapshot = load_episode_source_drama_snapshot_v1(episode_id)
        if snapshot is None:
            raise SourceDramaSnapshotError(
                "当前 Episode 尚未形成可消费的 SourceDramaSnapshot"
            )
        return compile_source_screenplay_v1(snapshot)
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
            detail="原片剧情理解运行时当前不可用或输出未通过事实门禁；没有修改任何原片事实。",
        ) from exc


__all__ = ["api_compile_episode_source_screenplay", "router"]
