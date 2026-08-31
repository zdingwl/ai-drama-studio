"""G2.1 Scene Timeline 的用户可读输出 Contract。

业务定位：
- Scene Timeline 是普通用户阅读“02 拉片”结果的主要数据形态；
- 它只承载已经被 G1/P2 冻结事实确定的 Scene / Shot / 人物出现 / 动作 / 对白 / OCR / 道具 / 镜头信息；
- 技术诊断字段（Evidence、cluster、confidence、subject_A/B、provider metadata）不进入主结果 Contract；
- LocalSubject 只会被映射成 Scene 内临时引用 P1/P2/...，这些引用绝不是 Character identity；
- Final Character / Final Scene / Final Prop 不属于本 Contract。

本文件只定义稳定 JSON 形状，不读取数据库、不调用模型、不修改 G1 数据。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SCENE_TIMELINE_SCHEMA_VERSION = "scene-timeline-v1"


class _StrictTimelineModel(BaseModel):
    """禁止静默接受额外字段，避免技术内部数据意外泄漏进用户结果。"""

    model_config = ConfigDict(extra="forbid")


class SceneTimelineSceneInfoV1(_StrictTimelineModel):
    """用户真正需要理解的 Scene 环境信息；不是 Final Scene Asset。"""

    location: str | None = Field(default=None, description="G1 SceneSegmentDraft 给出的地点提示；不是 Final Scene 名称。")
    interior_exterior: str | None = Field(default=None, description="用户可读的室内/室外信息；未知时为空。")
    time_of_day: str | None = Field(default=None, description="用户可读的白天/夜晚/黎明/黄昏信息；未知时为空。")
    environment: str | None = Field(default=None, description="G1 已有环境视觉描述；G2 不重新看视频补写。")


class SceneTimelinePersonV1(_StrictTimelineModel):
    """一个 Scene 内的匿名出场人物展示项，生命周期只限当前 Scene。"""

    ref: str = Field(pattern=r"^P[1-9][0-9]*$", description="Scene 内临时匿名引用，例如 P1；跨 Scene 不代表同一人。")
    display_name: str = Field(min_length=1, description="普通用户展示名，例如“人物1”；绝不是 Character 名称。")
    appearance: str | None = Field(default=None, description="G1 LocalSubject 已有外观摘要，仅用于帮助用户区分本 Scene 人物。")


class SceneTimelinePerformanceV1(_StrictTimelineModel):
    """Shot 内已经被 G1 明确支持的人物动作/表演事实。"""

    text: str = Field(min_length=1, description="来自 ShotLocalSubject activity 或 ACTION event 的可读动作事实。")
    people: list[str] = Field(default_factory=list, description="参与该动作的 Scene-local P* 引用；无法可靠绑定时为空。")


class SceneTimelineDialogueV1(_StrictTimelineModel):
    """ASR 对白投影；text 必须保持 G1 ASR/Fusion 已落库文本原样。"""

    start_us: int = Field(ge=0, description="对白在原片时间轴的开始微秒。")
    end_us: int = Field(ge=0, description="对白在原片时间轴的结束微秒。")
    text: str = Field(min_length=1, description="ASR 对白文本真相；G2 禁止改写、纠错或总结。")
    speakers: list[str] = Field(default_factory=list, description="仅已有 SPEAKER 关系可映射时填写 Scene-local P*；不允许 G2 猜说话人。")


class SceneTimelineOnScreenTextV1(_StrictTimelineModel):
    """OCR 可见文字；与对白严格分开。"""

    start_us: int = Field(ge=0, description="OCR 文字在原片时间轴的开始微秒。")
    end_us: int = Field(ge=0, description="OCR 文字在原片时间轴的结束微秒。")
    text: str = Field(min_length=1, description="OCR 已识别文字原文；G2 禁止改写。")


class SceneTimelinePropV1(_StrictTimelineModel):
    """当前 Shot 已有 Prop occurrence 的用户展示项；不是 Final Prop。"""

    label: str = Field(min_length=1, description="来自 G1 Exact-Shot/Fusion 的可见道具标签。")
    interaction: str | None = Field(default=None, description="G1 已有道具交互摘要；没有可靠交互时为空。")


class SceneTimelineCinematographyV1(_StrictTimelineModel):
    """只展示 G1 已经存在的镜头语言事实，不让 G2 猜测。"""

    shot_type: str | None = Field(default=None, description="G1 Exact-Shot 已有景别提示；未知时为空。")
    composition: str | None = Field(default=None, description="G1 Exact-Shot composition_hint；未知时为空。")
    camera_motion: str | None = Field(default=None, description="只有 G1 有可靠值时展示；UNKNOWN 转为空，不由 G2 推断。")


class SceneTimelineShotV1(_StrictTimelineModel):
    """普通用户阅读的单个 Shot 拉片结果。"""

    ordinal: int = Field(ge=1, description="历史 ShotRevision 中的镜头顺序号。")
    start_us: int = Field(ge=0, description="Shot 原片开始微秒。")
    end_us: int = Field(ge=0, description="Shot 原片结束微秒。")
    duration_us: int = Field(ge=0, description="Shot 时长微秒，固定为 end_us - start_us。")
    thumbnail_url: str | None = Field(default=None, description="历史 ShotRevisionItem 缩略图读取地址；用于结果卡片。")
    reference_url: str | None = Field(default=None, description="历史 ShotRevisionItem 参考片段读取地址；用于用户回看。")
    visual_description: str | None = Field(default=None, description="Exact-Shot 优先的当前镜头可见事实；缺失时不让 G2 猜。")
    people: list[str] = Field(default_factory=list, description="当前 Shot 已确认出现的 Scene-local P* 引用。")
    performance: list[SceneTimelinePerformanceV1] = Field(default_factory=list, description="当前 Shot 已有动作/表演事实。")
    dialogue: list[SceneTimelineDialogueV1] = Field(default_factory=list, description="按原片时间排序的 ASR 对白。")
    props: list[SceneTimelinePropV1] = Field(default_factory=list, description="当前 Shot 已有可见道具/交互。")
    cinematography: SceneTimelineCinematographyV1 = Field(description="当前 Shot 已有景别、构图、运镜事实。")
    on_screen_text: list[SceneTimelineOnScreenTextV1] = Field(default_factory=list, description="当前 Shot OCR 可见文字。")


class SceneTimelineSceneV1(_StrictTimelineModel):
    """SceneSegmentDraft 的用户阅读形态；仍然不是 Final Scene。"""

    ordinal: int = Field(ge=1, description="SceneSegmentDraft 在当前 Breakdown Run 内的顺序。")
    start_us: int = Field(ge=0, description="Scene 原片开始微秒。")
    end_us: int = Field(ge=0, description="Scene 原片结束微秒。")
    duration_us: int = Field(ge=0, description="Scene 时长微秒，固定为 end_us - start_us。")
    title: str = Field(min_length=1, description="确定性用户标题；G2.2 首版使用地点或“场景 NN”，不是 Final Scene 名称。")
    scene_info: SceneTimelineSceneInfoV1 = Field(description="地点、室内外、时间段和环境信息。")
    people: list[SceneTimelinePersonV1] = Field(default_factory=list, description="本 Scene 匿名出场人物；P* 引用只在本 Scene 有效。")
    story_summary: str | None = Field(default=None, description="G2.2 先使用已有 Scene summary；后续 G2 LLM 只能做有来源的可读整理。")
    shots: list[SceneTimelineShotV1] = Field(default_factory=list, description="按 Shot ordinal 排序的镜头列表。")


class SceneTimelinePayloadV1(_StrictTimelineModel):
    """一个 Breakdown Run 对应的一份 Scene Timeline 用户结果。"""

    schema_version: Literal["scene-timeline-v1"] = Field(default=SCENE_TIMELINE_SCHEMA_VERSION, description="Scene Timeline Contract 版本。")
    source_breakdown_run_id: str = Field(min_length=1, description="只用于结果追溯的 G1 Breakdown Run ID；普通主界面不展示。")
    source_shot_revision_id: str = Field(min_length=1, description="结果绑定的历史 ShotRevision ID；保证 Timeline 不漂移到新镜头版本。")
    episode_id: str = Field(min_length=1, description="Timeline 所属 Episode。")
    status: str = Field(min_length=1, description="继承源 Breakdown Run 状态；G2.2 不自行伪造 READY。")
    is_current: bool = Field(description="源 Breakdown Run 是否仍是当前可消费 Run。")
    scene_count: int = Field(ge=0, description="scenes 数量的确定性摘要。")
    shot_count: int = Field(ge=0, description="全部 Scene 下 shots 数量的确定性摘要。")
    warnings: list[str] = Field(default_factory=list, description="只放用户可理解的降级提示；不暴露 Evidence/cluster/provider 调试细节。")
    scenes: list[SceneTimelineSceneV1] = Field(default_factory=list, description="Scene Timeline 主结果。")


def scene_timeline_json_schema_v1() -> dict[str, object]:
    """给后续 API / 前端契约测试复用同一份 Pydantic JSON Schema。"""

    return SceneTimelinePayloadV1.model_json_schema()


__all__ = [
    "SCENE_TIMELINE_SCHEMA_VERSION",
    "SceneTimelineCinematographyV1",
    "SceneTimelineDialogueV1",
    "SceneTimelineOnScreenTextV1",
    "SceneTimelinePayloadV1",
    "SceneTimelinePerformanceV1",
    "SceneTimelinePersonV1",
    "SceneTimelinePropV1",
    "SceneTimelineSceneInfoV1",
    "SceneTimelineSceneV1",
    "SceneTimelineShotV1",
    "scene_timeline_json_schema_v1",
]
