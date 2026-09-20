"""Project-scoped human review of script-to-drama asset definitions.

An edit creates new World/Assets revisions and invalidates downstream media; it
never mutates a model-derived source fact or a Replica artifact in place.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactNamespace
from app.artifacts.service import _invalidate_project_plan
from app.core.errors import AppError
from app.script_to_drama import service
from app.skills.models import ArtifactType


class AssetCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["characters", "locations", "props"]
    entity_id: str = Field(min_length=1, max_length=120)
    visual_description: str = Field(min_length=1, max_length=1200)


class ReviewWorldCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_world_artifact_id: str = Field(min_length=1, max_length=160)
    corrections: list[AssetCorrection] = Field(default_factory=list, max_length=100)
    acknowledged_decisions: list[str] = Field(default_factory=list, max_length=100)
    reason: str = Field(min_length=2, max_length=800)

    @model_validator(mode="after")
    def requires_change(self):
        if not self.corrections and not self.acknowledged_decisions:
            raise ValueError("请至少修改一个资产设定或确认一条未决事项")
        keys = [(item.category, item.entity_id) for item in self.corrections]
        if len(set(keys)) != len(keys) or len(set(self.acknowledged_decisions)) != len(self.acknowledged_decisions):
            raise ValueError("重复的资产修改或未决事项")
        return self


def review_world(db: Session, project_id: str, command: ReviewWorldCommand):
    project = service.require_project(db, project_id)
    current = service._require(db, project_id, ArtifactType.TARGET_BIBLE)
    if current.id != command.expected_world_artifact_id:
        raise AppError("SCRIPT_TO_DRAMA_WORLD_CONFLICT", "资产定义已更新，请刷新后重新审核", status_code=409)
    snapshot = service._require(db, project_id, ArtifactType.SOURCE_TEXT_SNAPSHOT)
    story = service._require(db, project_id, ArtifactType.STORY_SKELETON)
    rhythm = service._require(db, project_id, ArtifactType.RHYTHM_SKELETON)
    source = service._content(db, current)
    if source.get("source_snapshot_artifact_id") != snapshot.id:
        raise AppError("SCRIPT_TO_DRAMA_WORLD_STALE", "目标世界与当前原剧本分析不匹配", status_code=409)

    import copy
    reviewed = copy.deepcopy(source)
    for correction in command.corrections:
        matches = [item for item in reviewed.get(correction.category, []) if item.get("id") == correction.entity_id]
        if len(matches) != 1:
            raise AppError("SCRIPT_TO_DRAMA_ENTITY_NOT_FOUND", "资产 ID 不存在或不唯一", status_code=409)
        matches[0]["visual_description"] = correction.visual_description.strip()
        matches[0]["human_reviewed"] = True
    unresolved = reviewed.get("unresolved_decisions", [])
    unknown = set(command.acknowledged_decisions) - set(unresolved)
    if unknown:
        raise AppError("SCRIPT_TO_DRAMA_DECISION_CONFLICT", "待决事项已变化，请刷新后重新确认", status_code=409)
    reviewed["unresolved_decisions"] = [item for item in unresolved if item not in command.acknowledged_decisions]
    reviewed["manual_review"] = {
        "reason": command.reason.strip(),
        "previous_world_artifact_id": current.id,
        "corrected_entity_ids": [item.entity_id for item in command.corrections],
        "acknowledged_decisions": command.acknowledged_decisions,
    }
    common = dict(project_id=project_id, skill_id="script-to-drama-human-review",
                  skill_version="1.0.0", task_id=None, job_id="human-review")
    world = service._publish_one(
        db, kind=ArtifactType.TARGET_BIBLE, namespace=ArtifactNamespace.TARGET,
        label="剧本生成短剧·人工核定目标世界", content=reviewed,
        sources=[snapshot, story, rhythm], **common,
    )
    service._publish_one(
        db, kind=ArtifactType.TARGET_ASSETS, namespace=ArtifactNamespace.TARGET,
        label="剧本生成短剧·人工核定资产定义",
        content={"characters": reviewed.get("characters", []), "locations": reviewed.get("locations", []),
                 "props": reviewed.get("props", []), "target_bible_artifact_id": world.id,
                 "status": "DEFINITIONS_ONLY", "manual_review": reviewed["manual_review"]},
        sources=[world], **common,
    )
    _invalidate_project_plan(db, project)
    db.commit()
    return service.state(db, project_id)
