"""G2.3/G2.4 Scene 文本整理的内部 Grounding / Narrative Contract。

业务边界：
- 本 Contract 建立在已经 FINAL PASS / FROZEN 的 ``scene-timeline-v1`` 之上；
- LLM 只允许生成 Scene 标题与“这一段发生了什么”，不允许回写 Shot 事实；
- 每段 LLM 文本必须携带当前 Scene 内的 ``Fxxxx`` support refs；
- support refs 只用于内部校验/追溯，后续普通用户 UI 不展示；
- LocalSubject 仍然只是 Scene-local P1/P2/...，绝不是 Character identity；
- 本文件不读取视频、不调用模型、不创建 Final Character / Scene / Prop。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SCENE_GROUNDING_SCHEMA_VERSION = "scene-grounding-v1"
SCENE_NARRATIVE_SCHEMA_VERSION = "scene-narrative-v1"

GroundingFactKindV1 = Literal[
    "SCENE_LOCATION",
    "SCENE_SPACE",
    "SCENE_TIME",
    "SCENE_ENVIRONMENT",
    "SCENE_BASE_SUMMARY",
    "PERSON_APPEARANCE",
    "SHOT_VISUAL",
    "SHOT_PERFORMANCE",
    "DIALOGUE",
    "PROP",
    "PROP_INTERACTION",
    "SHOT_TYPE",
    "COMPOSITION",
    "CAMERA_MOTION",
    "OCR",
]


class _StrictNarrativeModel(BaseModel):
    """G2 Narrative 内部协议同样禁止静默吞掉未知字段。"""

    model_config = ConfigDict(extra="forbid")


class SceneGroundingInfoV1(_StrictNarrativeModel):
    """传给纯文本 LLM 的 Scene 环境信息；全部来自冻结 Timeline。"""

    location: str | None = None
    interior_exterior: str | None = None
    time_of_day: str | None = None
    environment: str | None = None


class SceneGroundingPersonV1(_StrictNarrativeModel):
    """LLM 只可使用这些 Scene-local 匿名人物引用。"""

    ref: str = Field(pattern=r"^P[1-9][0-9]*$")
    display_name: str = Field(min_length=1, max_length=80)
    appearance: str | None = Field(default=None, max_length=1200)


class SceneGroundingFactV1(_StrictNarrativeModel):
    """一个可被 Narrative claim 引用的冻结事实原子。"""

    fact_id: str = Field(pattern=r"^F[0-9]{4}$")
    kind: GroundingFactKindV1
    shot_ordinal: int | None = Field(default=None, ge=1)
    people: list[str] = Field(default_factory=list)
    text: str = Field(min_length=1, max_length=4000)


class SceneGroundingPacketV1(_StrictNarrativeModel):
    """一次 Scene-level 文本 LLM 调用的完整、可指纹化输入。"""

    schema_version: Literal["scene-grounding-v1"] = SCENE_GROUNDING_SCHEMA_VERSION
    source_breakdown_run_id: str = Field(min_length=1)
    source_shot_revision_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    scene_ordinal: int = Field(ge=1)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    deterministic_title: str = Field(min_length=1, max_length=300)
    scene_info: SceneGroundingInfoV1
    people: list[SceneGroundingPersonV1] = Field(default_factory=list)
    facts: list[SceneGroundingFactV1] = Field(default_factory=list)


class SceneNarrativeClaimV1(_StrictNarrativeModel):
    """LLM 可提交的一个用户可读文本 claim，必须声明支持事实。"""

    text: str = Field(min_length=1, max_length=800)
    support: list[str] = Field(min_length=1, max_length=64)


class SceneNarrativeCandidateV1(_StrictNarrativeModel):
    """LLM 原始结构化候选；不经过 G2.4 Validator 不能用于用户结果。"""

    scene_ordinal: int = Field(ge=1)
    readable_title: SceneNarrativeClaimV1 | None = None
    story_summary: SceneNarrativeClaimV1 | None = None


class SceneNarrativeSceneV1(_StrictNarrativeModel):
    """G2.4 校验后的 Scene overlay；只覆盖标题/摘要，不拥有其它事实。"""

    scene_ordinal: int = Field(ge=1)
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    readable_title: SceneNarrativeClaimV1 | None = None
    story_summary: SceneNarrativeClaimV1 | None = None


class SceneNarrativeOverlayPayloadV1(_StrictNarrativeModel):
    """一份 Timeline 对应的受校验 Narrative overlay。"""

    schema_version: Literal["scene-narrative-v1"] = SCENE_NARRATIVE_SCHEMA_VERSION
    source_breakdown_run_id: str = Field(min_length=1)
    source_shot_revision_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    status: Literal["READY", "READY_WITH_WARNINGS"]
    scenes: list[SceneNarrativeSceneV1] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


__all__ = [
    "GroundingFactKindV1",
    "SCENE_GROUNDING_SCHEMA_VERSION",
    "SCENE_NARRATIVE_SCHEMA_VERSION",
    "SceneGroundingFactV1",
    "SceneGroundingInfoV1",
    "SceneGroundingPacketV1",
    "SceneGroundingPersonV1",
    "SceneNarrativeCandidateV1",
    "SceneNarrativeClaimV1",
    "SceneNarrativeOverlayPayloadV1",
    "SceneNarrativeSceneV1",
]
