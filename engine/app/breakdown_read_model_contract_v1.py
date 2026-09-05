"""P6 最终 Breakdown 阅读模型 Contract。

P6 只组合已经存在的事实/最终资产层：
- G2 Scene Timeline：场景 / 镜头 / 动作 / 对白 / OCR / 道具 / 镜头语言事实；
- P5 Breakdown ↔ Character Bridge：只有 RESOLVED 的 Scene-local 人物才可指向 Final Character；
- current Final ShotSceneBinding / ShotPropBinding：只用于独立的 Final Scene / Prop 展示 overlay。

关键边界：
- ``timeline`` 必须完整保留 ``scene-timeline-v1``，P6 不改写其中任何字段；
- Scene-local P1/P2/... 仍然不是 Character identity，本 Contract 只提供独立 display overlay；
- UNRESOLVED 人物保持原来的“人物N”；
- Final Scene 只在 Scene 内全部 current Shot 精确绑定同一个 Final Scene 时展示；
- Final Prop 只按 current ShotPropBinding 展示，不把 G2 道具文字硬匹配成 Prop；
- 不暴露 LocalSubject ID、support Shot、resolution basis、confidence 等工程证据；
- Final assets 只允许展示当前资产版本中已有的 id/name/cover_url。
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
    cover_box: list[float] | None = Field(default=None, min_length=4, max_length=4)


class FinalSceneDisplayV1(_StrictReadModel):
    """普通用户可以看到的 Final Scene 最小展示信息。"""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    cover_url: str | None = None


class FinalPropDisplayV1(_StrictReadModel):
    """普通用户可以看到的 Final Prop 最小展示信息。"""

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


class BreakdownReadSceneAssetV1(_StrictReadModel):
    """一个 G2 Scene 对应的 Final Scene 展示；无法严格收敛时 scene=null。"""

    scene_ordinal: int = Field(ge=1)
    scene: FinalSceneDisplayV1 | None = None


class BreakdownReadShotAssetV1(_StrictReadModel):
    """一个 G2 Shot 当前 Final Prop bindings 的展示投影。"""

    scene_ordinal: int = Field(ge=1)
    shot_ordinal: int = Field(ge=1)
    props: list[FinalPropDisplayV1] = Field(default_factory=list)


class BreakdownReadAssetOverlayV1(_StrictReadModel):
    """P6 Final Scene / Prop display overlay；与人物 identity overlay 独立 fail-closed。"""

    asset_revision_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    scenes: list[BreakdownReadSceneAssetV1] = Field(default_factory=list)
    shots: list[BreakdownReadShotAssetV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_surface(self) -> "BreakdownReadAssetOverlayV1":
        scene_keys = [item.scene_ordinal for item in self.scenes]
        shot_keys = [(item.scene_ordinal, item.shot_ordinal) for item in self.shots]
        if len(set(scene_keys)) != len(scene_keys):
            raise ValueError("Scene asset overlay 不允许重复 scene_ordinal")
        if len(set(shot_keys)) != len(shot_keys):
            raise ValueError("Shot asset overlay 不允许重复 Scene/Shot ordinal")
        has_assets = any(item.scene is not None for item in self.scenes) or any(item.props for item in self.shots)
        if has_assets and not self.asset_revision_id:
            raise ValueError("存在 Final Scene/Prop 展示时必须携带 asset_revision_id")
        for item in self.shots:
            prop_ids = [prop.id for prop in item.props]
            if len(set(prop_ids)) != len(prop_ids):
                raise ValueError("同一 Shot 不允许重复 Final Prop")
        return self


class BreakdownReadModelV1(_StrictReadModel):
    """P6 普通用户最终拉片阅读模型。

    ``timeline`` 是冻结 G2.5 输出原对象；``identity`` 与 ``assets`` 都只是独立显示 overlay。
    """

    schema_version: Literal["breakdown-read-model-v1"] = BREAKDOWN_READ_MODEL_SCHEMA_VERSION
    timeline: SceneTimelinePayloadV1
    identity: BreakdownReadIdentityOverlayV1
    assets: BreakdownReadAssetOverlayV1 | None = None
    speaker_overrides: dict[str, str] = Field(default_factory=dict)
    manual_presence: dict[str, list[str]] = Field(default_factory=dict)
    presence_review: dict[str, str] = Field(default_factory=dict)
    shot_characters: dict[str, list[FinalCharacterDisplayV1]] = Field(default_factory=dict)


__all__ = [
    "BREAKDOWN_READ_MODEL_SCHEMA_VERSION",
    "BreakdownReadAssetOverlayV1",
    "BreakdownReadIdentityOverlayV1",
    "BreakdownReadModelV1",
    "BreakdownReadPersonV1",
    "BreakdownReadSceneAssetV1",
    "BreakdownReadSceneIdentityV1",
    "BreakdownReadShotAssetV1",
    "FinalCharacterDisplayV1",
    "FinalPropDisplayV1",
    "FinalSceneDisplayV1",
]
