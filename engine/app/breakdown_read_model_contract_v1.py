"""P6 最终 Breakdown 阅读模型 Contract。

P6 只组合两个已经冻结的事实层：
- G2 Scene Timeline：场景 / 镜头 / 动作 / 对白 / OCR / 道具 / 镜头语言事实；
- P5 Breakdown ↔ Character Bridge：只有 RESOLVED 的 Scene-local 人物才可指向 Final Character。

关键边界：
- ``timeline`` 必须完整保留 ``scene-timeline-v1``，P6 不改写其中任何字段；
- Scene-local P1/P2/... 仍然不是 Character identity，本 Contract 只提供独立 display overlay；
- UNRESOLVED 人物保持原来的“人物N”；
- 不暴露 LocalSubject ID、support Shot、resolution basis、confidence 等工程证据；
- Final Character 只允许展示当前资产版本中已有的 id/name/cover_url。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1


BREAKDOWN_READ_MODEL_SCHEMA_VERSION = "breakdown-read-model-v1"


class _StrictReadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FinalCharacterDisplayV1(_StrictReadModel):
    """普通用户可以看到的 Final Character 最小展示信息。"""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    cover_url: str | None = None


class BreakdownReadPersonV1(_StrictReadModel):
    """一个 Scene-local P* 的最终显示方式。"""

    ref: str = Field(pattern=r"^P[1-9][0-9]*$")
    display_name: str = Field(min_length=1)
    character: FinalCharacterDisplayV1 | None = None


class BreakdownReadSceneIdentityV1(_StrictReadModel):
    scene_ordinal: int = Field(ge=1)
    people: list[BreakdownReadPersonV1] = Field(default_factory=list)


class BreakdownReadIdentityOverlayV1(_StrictReadModel):
    """P6 人物展示 overlay；不会反向写入 G2/P5。"""

    asset_revision_id: str | None = None
    resolved_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    scenes: list[BreakdownReadSceneIdentityV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _counts_match_people(self) -> "BreakdownReadIdentityOverlayV1":
        people = [person for scene in self.scenes for person in scene.people]
        resolved = sum(person.character is not None for person in people)
        if resolved != self.resolved_count:
            raise ValueError("resolved_count 与人物 overlay 不一致")
        if len(people) - resolved != self.unresolved_count:
            raise ValueError("unresolved_count 与人物 overlay 不一致")
        return self


class BreakdownReadModelV1(_StrictReadModel):
    """P6 普通用户最终拉片阅读模型。

    ``timeline`` 是冻结 G2.5 输出原对象；``identity`` 只是独立显示 overlay。
    """

    schema_version: Literal["breakdown-read-model-v1"] = BREAKDOWN_READ_MODEL_SCHEMA_VERSION
    timeline: SceneTimelinePayloadV1
    identity: BreakdownReadIdentityOverlayV1


__all__ = [
    "BREAKDOWN_READ_MODEL_SCHEMA_VERSION",
    "BreakdownReadIdentityOverlayV1",
    "BreakdownReadModelV1",
    "BreakdownReadPersonV1",
    "BreakdownReadSceneIdentityV1",
    "FinalCharacterDisplayV1",
]
