"""Breakdown-first Phase P1 的匿名结构化拉片 Draft 数据模型。

职责：
- 在 Reference Video V2 的正式 ``studio_v2.Base`` 上定义 P1 Draft 表；
- 把一次 Breakdown Run 永久绑定到一个 ShotRevision；
- 把每个 ShotSemanticDraft 永久绑定到一个 ShotRevisionItem；
- 保存匿名 LocalSubject、SceneSegmentDraft、TimelineEvent 与 DraftPropHint；
- 为未来 P2 原始 ASR/OCR/VLM Evidence 预留通用 provenance link。

不负责：
- 不运行 ASR / OCR / VLM；
- 不创建 Character / Scene / Prop Final Asset；
- 不写 ShotCharacterBinding / ShotSceneBinding / ShotPropBinding；
- 不修改 Character V10.1 identity、阈值、explicit Shot assignment 或 Final Gate；
- 不实现 Run lifecycle、validator、API、serializer 或 Shot Revision STALE 联动。

稳定依赖：
- ``engine.app.studio_v2.Base`` / ``data_v2/studio_v2.sqlite3``；
- ``ShotRevision`` / ``ShotRevisionItem`` 历史快照；
- 正式时间单位统一为 integer microseconds。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem  # noqa: F401
from engine.app.studio_v2 import Base, utcnow

BREAKDOWN_DRAFT_SCHEMA_VERSION = "breakdown-draft-v1"


class BreakdownRun(Base):
    """一次 Episode 级匿名结构化拉片证据快照。

    ``source_shot_revision_id`` 是 Run 的历史媒体锚点；Current Shot 改变后，
    后续 P1.6 只把旧 Run 标记为 STALE，绝不改写或迁移旧 Draft。
    """

    __tablename__ = "v2_breakdown_runs"
    __table_args__ = {
        "comment": "Breakdown-first P1：Episode 级匿名结构化拉片 Run，绑定一个不可歧义的 ShotRevision。"
    }

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="Breakdown Run 稳定业务 ID。")
    project_id: Mapped[str] = mapped_column(
        ForeignKey("v2_projects.id", ondelete="CASCADE"),
        index=True,
        comment="Run 所属 Project；用于项目级查询，不替代 episode_id。",
    )
    episode_id: Mapped[str] = mapped_column(
        ForeignKey("v2_episodes.id", ondelete="CASCADE"),
        index=True,
        comment="本次匿名拉片解释的 Episode。",
    )
    source_shot_revision_id: Mapped[str] = mapped_column(
        ForeignKey("v2_shot_revisions.id", ondelete="CASCADE"),
        index=True,
        comment="本 Run 冻结解释的 ShotRevision；不能只依赖 Current Shot。",
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PROCESSING", index=True,
        comment="Run 状态：PROCESSING/READY/READY_WITH_WARNINGS/FAILED/STALE。",
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True,
        comment="是否为 Episode 当前可消费的 READY 类 Breakdown Run；切换规则由 P1.2 实现。",
    )
    schema_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default=BREAKDOWN_DRAFT_SCHEMA_VERSION,
        comment="Draft 数据 Contract 版本；P1 首版固定 breakdown-draft-v1。",
    )
    pipeline_profile: Mapped[str | None] = mapped_column(
        String(160), nullable=True,
        comment="实际生成 Draft 的 provider/profile/version 摘要；P1.1 只建模，不运行推理。",
    )
    component_status_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}",
        comment="ASR/OCR/VLM/segmenter 等组件状态摘要；P1.2/P2 再写入。",
    )
    provider_metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}",
        comment="模型、版本、设备和参数等可扩展 provider metadata。",
    )
    counts_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}",
        comment="segment/shot/subject/event/prop 等数量摘要，不替代明细表。",
    )
    warning_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}",
        comment="非致命警告；READY_WITH_WARNINGS 的可追溯说明。",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Run 失败时的可读错误；成功 Run 为空。",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow,
        comment="Run 开始时间。",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Run 完成或失败时间；PROCESSING 时为空。",
    )


class SceneSegmentDraft(Base):
    """一个 Run 内剧情意义上的连续场景段，不是 Final Scene Asset。"""

    __tablename__ = "v2_scene_segment_drafts"
    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_v2_scene_segment_draft_run_ordinal"),
        {"comment": "Breakdown-first P1：连续剧情 Scene Segment Draft；禁止当作 Final Scene。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="Scene Segment Draft 稳定 ID。")
    run_id: Mapped[str] = mapped_column(
        ForeignKey("v2_breakdown_runs.id", ondelete="CASCADE"), index=True,
        comment="生成该 Segment 的 Breakdown Run。",
    )
    episode_id: Mapped[str] = mapped_column(
        ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True,
        comment="Segment 所属 Episode；便于时间轴查询和跨 Run 校验。",
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, comment="Segment 在当前 Run 内的 1-based 顺序。")
    source_start_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="Segment 在原片时间轴的开始微秒。")
    source_end_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="Segment 在原片时间轴的结束微秒。")
    location_hint: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="地点语义提示，不是 Final Scene 名称。")
    interior_exterior: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNKNOWN",
        comment="室内外提示：INTERIOR/EXTERIOR/MIXED/UNKNOWN。",
    )
    time_of_day: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNKNOWN",
        comment="时间段提示：DAY/NIGHT/DAWN/DUSK/UNKNOWN。",
    )
    scene_function_hint: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="剧情功能提示，例如 confrontation/transition/setup。")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="该连续剧情段的简要语义概述。")
    environment_description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="环境视觉事实/描述，不是 Scene Asset prompt。")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Segment 语义置信度；只作为 soft prior。")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", comment="可扩展软语义 metadata。")


class ShotSemanticDraft(Base):
    """对一个历史 ShotRevisionItem 的结构化第一遍理解。"""

    __tablename__ = "v2_shot_semantic_drafts"
    __table_args__ = (
        UniqueConstraint("run_id", "source_shot_revision_item_id", name="uq_v2_shot_semantic_draft_run_item"),
        {"comment": "Breakdown-first P1：逐 ShotRevisionItem 的匿名结构化语义 Draft。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="Shot Semantic Draft 稳定 ID。")
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_breakdown_runs.id", ondelete="CASCADE"), index=True, comment="生成本 Shot Draft 的 Breakdown Run。")
    scene_segment_id: Mapped[str] = mapped_column(ForeignKey("v2_scene_segment_drafts.id", ondelete="CASCADE"), index=True, comment="该 Shot 在本 Run 中唯一所属的 Scene Segment Draft。")
    source_shot_revision_item_id: Mapped[str] = mapped_column(
        ForeignKey("v2_shot_revision_items.id", ondelete="CASCADE"), index=True,
        comment="永久历史锚点：实际被分析的 ShotRevisionItem。",
    )
    source_shot_id_snapshot: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="分析时原 v2_shots.id 的快照，仅供追踪；故意不做 Current Shot FK。",
    )
    shot_ordinal_snapshot: Mapped[int] = mapped_column(Integer, nullable=False, comment="分析时 Shot ordinal 快照，用于展示/校验，不做历史主锚点。")
    source_start_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="分析时 Shot 起点微秒快照。")
    source_end_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="分析时 Shot 终点微秒快照。")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="该 Shot 发生了什么的简要描述。")
    visual_description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="尽量只描述可见画面事实的文本。")
    shot_language: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="该 Shot 主要语言提示；未知时为空。")
    shot_type_hint: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="景别提示，例如 CLOSE_UP/MEDIUM/WIDE；不覆盖 Shot.shot_type。")
    camera_motion_hint: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="运镜提示；不覆盖 Shot.camera_motion。")
    narrative_function_hint: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="叙事功能 soft hint，例如 reaction/dialogue/insert。")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, comment="该 Shot Draft 总体语义置信度，只是 soft prior。")
    model_metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", comment="生成该 Shot Draft 的模型辅助 metadata。")


class LocalSubject(Base):
    """Scene Segment 内匿名人物，例如“人物A”，绝不是 Character 身份。"""

    __tablename__ = "v2_local_subjects"
    __table_args__ = (
        UniqueConstraint("scene_segment_id", "ordinal", name="uq_v2_local_subject_segment_ordinal"),
        {"comment": "Breakdown-first P1：Scene Segment 局部匿名人物；表内禁止 Character FK。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="LocalSubject 稳定 ID。")
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_breakdown_runs.id", ondelete="CASCADE"), index=True, comment="生成该匿名人物的 Breakdown Run。")
    scene_segment_id: Mapped[str] = mapped_column(ForeignKey("v2_scene_segment_drafts.id", ondelete="CASCADE"), index=True, comment="LocalSubject 的局部身份作用域；跨 Segment 默认不声明同一人。")
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, comment="匿名人物在本 Segment 内的 1-based 顺序。")
    display_label: Mapped[str] = mapped_column(String(100), nullable=False, comment="用户可读匿名标签，例如 人物A/人物B。")
    role_hint: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="角色语义提示，只是 hint，不能当 Character identity。")
    appearance_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="外观摘要，用于后续定向寻找 Person Evidence。")
    appearance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", comment="服装/发型/配饰等可扩展 soft appearance hints。")
    first_seen_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="该 LocalSubject 在 Segment 中首次出现的原片微秒。")
    last_seen_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="该 LocalSubject 在 Segment 中最后出现的原片微秒。")
    speaking_state_summary: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="跨 Segment Shot 汇总的 speaking/silent/mixed/unknown 语义提示。")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, comment="匿名主体存在/描述的 soft 置信度。")


class ShotLocalSubject(Base):
    """LocalSubject 在一个具体 Shot Draft 中的出现状态。"""

    __tablename__ = "v2_shot_local_subjects"
    __table_args__ = (
        UniqueConstraint("shot_draft_id", "local_subject_id", name="uq_v2_shot_local_subject_draft_subject"),
        {"comment": "Breakdown-first P1：匿名人物在具体 Shot 中的 presence/活动 soft hints。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="ShotLocalSubject 关联记录 ID。")
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_breakdown_runs.id", ondelete="CASCADE"), index=True, comment="关联记录所属 Breakdown Run。")
    shot_draft_id: Mapped[str] = mapped_column(ForeignKey("v2_shot_semantic_drafts.id", ondelete="CASCADE"), index=True, comment="匿名人物出现的 Shot Semantic Draft。")
    local_subject_id: Mapped[str] = mapped_column(ForeignKey("v2_local_subjects.id", ondelete="CASCADE"), index=True, comment="出现于该 Shot 的 LocalSubject。")
    first_seen_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="该 Shot 内首次出现的原片微秒。")
    last_seen_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="该 Shot 内最后出现的原片微秒。")
    screen_position: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN", comment="LEFT/CENTER/RIGHT/MIXED/UNKNOWN 的 soft 画面位置。")
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN", comment="FULL/PARTIAL/OCCLUDED/BACK_VIEW/UNKNOWN 的可见度提示。")
    speaking_state: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN", comment="SPEAKING/NOT_SPEAKING/POSSIBLE/UNKNOWN；不是 Speaker identity。")
    activity_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="该匿名人物在 Shot 内的活动语义摘要。")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, comment="该 Shot presence/状态的 soft 置信度。")
    search_hint_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", comment="后续 Person Evidence 定向搜索提示；不是 bbox/Track Evidence。")


class TimelineEvent(Base):
    """Shot 内带绝对时间和 Shot 相对时间的统一视听语义事件。"""

    __tablename__ = "v2_timeline_events"
    __table_args__ = (
        UniqueConstraint("shot_draft_id", "ordinal", name="uq_v2_timeline_event_shot_ordinal"),
        {"comment": "Breakdown-first P1：Shot 内 VISUAL/ACTION/DIALOGUE/OCR/AUDIO_EVENT 语义事件。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="TimelineEvent 稳定 ID。")
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_breakdown_runs.id", ondelete="CASCADE"), index=True, comment="事件所属 Breakdown Run。")
    shot_draft_id: Mapped[str] = mapped_column(ForeignKey("v2_shot_semantic_drafts.id", ondelete="CASCADE"), index=True, comment="事件所属 Shot Semantic Draft。")
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, comment="事件在当前 Shot Draft 内的 1-based 顺序。")
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="VISUAL/ACTION/DIALOGUE/OCR/AUDIO_EVENT。")
    source_start_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="事件在原片时间轴的开始微秒。")
    source_end_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="事件在原片时间轴的结束微秒。")
    shot_relative_start_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="相对 Shot Draft 起点的开始微秒。")
    shot_relative_end_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="相对 Shot Draft 起点的结束微秒。")
    content_text: Mapped[str] = mapped_column(Text, nullable=False, comment="统一可读事件文本；DIALOGUE/OCR 不替代未来原始 Evidence。")
    language: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="事件文本语言；未知时为空。")
    emotion_hint: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="情绪 soft hint；不写 Final Dialogue/Voice。")
    speaking_style_hint: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="说话方式 soft hint；不写 Final Voice。")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, comment="该语义事件的 soft 置信度。")
    origin: Mapped[str] = mapped_column(String(32), nullable=False, comment="VLM/ASR/OCR/FUSION/RULE，标记语义事件来源类别。")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", comment="事件扩展 metadata。")


class TimelineEventSubject(Base):
    """TimelineEvent 与 LocalSubject 的多参与者角色关系。"""

    __tablename__ = "v2_timeline_event_subjects"
    __table_args__ = (
        UniqueConstraint("event_id", "local_subject_id", "role", name="uq_v2_timeline_event_subject_role"),
        {"comment": "Breakdown-first P1：TimelineEvent 的匿名参与者及 ACTOR/TARGET/SPEAKER 等角色。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="TimelineEventSubject 关联记录 ID。")
    event_id: Mapped[str] = mapped_column(ForeignKey("v2_timeline_events.id", ondelete="CASCADE"), index=True, comment="被参与的 TimelineEvent。")
    local_subject_id: Mapped[str] = mapped_column(ForeignKey("v2_local_subjects.id", ondelete="CASCADE"), index=True, comment="参与事件的匿名 LocalSubject。")
    role: Mapped[str] = mapped_column(String(32), nullable=False, comment="ACTOR/TARGET/SPEAKER/LISTENER/WITNESS/OTHER。")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, comment="参与者角色判断的 soft 置信度。")


class DraftPropHint(Base):
    """剧情上值得后续验证的匿名道具提示，不是 Final Prop。"""

    __tablename__ = "v2_draft_prop_hints"
    __table_args__ = (
        UniqueConstraint("scene_segment_id", "ordinal", name="uq_v2_draft_prop_hint_segment_ordinal"),
        {"comment": "Breakdown-first P1：Scene Segment 内剧情相关 Prop soft hint；表内禁止 Final prop_id。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="DraftPropHint 稳定 ID。")
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_breakdown_runs.id", ondelete="CASCADE"), index=True, comment="生成该 Prop Hint 的 Breakdown Run。")
    scene_segment_id: Mapped[str] = mapped_column(ForeignKey("v2_scene_segment_drafts.id", ondelete="CASCADE"), index=True, comment="Prop Hint 所属 Scene Segment Draft。")
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, comment="Prop Hint 在 Segment 内的 1-based 顺序。")
    label_hint: Mapped[str] = mapped_column(String(255), nullable=False, comment="用户可读道具提示，例如 蓝玫瑰/合同/手机。")
    normalized_hint: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="可选规范化文本，只用于搜索/聚合，不是 Final Prop 名称。")
    importance: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN", comment="KEY/SUPPORTING/AMBIENT/UNKNOWN 的剧情重要性提示。")
    narrative_reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="为什么认为该物体值得后续专用 Prop Evidence 验证。")
    first_seen_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="该 Prop Hint 首次出现的原片微秒。")
    last_seen_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="该 Prop Hint 最后出现的原片微秒。")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Prop Hint 的 soft 置信度。")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", comment="Prop Hint 扩展 soft metadata。")


class DraftPropOccurrence(Base):
    """DraftPropHint 在具体 Shot/时间段的定向搜索位置提示。"""

    __tablename__ = "v2_draft_prop_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "prop_hint_id", "shot_draft_id", "source_start_us", "source_end_us",
            name="uq_v2_draft_prop_occurrence_range",
        ),
        {"comment": "Breakdown-first P1：Prop Hint 在 Shot Draft 内的时间范围与 soft 搜索提示。"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="DraftPropOccurrence 稳定 ID。")
    prop_hint_id: Mapped[str] = mapped_column(ForeignKey("v2_draft_prop_hints.id", ondelete="CASCADE"), index=True, comment="本次出现对应的 DraftPropHint。")
    shot_draft_id: Mapped[str] = mapped_column(ForeignKey("v2_shot_semantic_drafts.id", ondelete="CASCADE"), index=True, comment="应该定向寻找该道具的 Shot Semantic Draft。")
    source_start_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="出现范围在原片时间轴的开始微秒。")
    source_end_us: Mapped[int] = mapped_column(Integer, nullable=False, comment="出现范围在原片时间轴的结束微秒。")
    screen_position_hint: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="可选画面位置 soft hint。")
    interaction_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="谁拿着/看向/放在哪里等互动语义摘要。")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, comment="本次出现位置/互动提示的 soft 置信度。")
    search_region_hint_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", comment="后续对象检测定向搜索提示；不是正式 bbox/mask Evidence。")


class BreakdownEvidenceLink(Base):
    """Semantic Draft 到未来原始 Evidence/artifact 的通用 provenance 关系。"""

    __tablename__ = "v2_breakdown_evidence_links"
    __table_args__ = {
        "comment": "Breakdown-first P1：Draft owner 与未来 ASR/OCR/VLM/frame/audio Evidence 的可追溯连接。"
    }

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="EvidenceLink 稳定 ID。")
    run_id: Mapped[str] = mapped_column(ForeignKey("v2_breakdown_runs.id", ondelete="CASCADE"), index=True, comment="该 provenance link 所属 Breakdown Run。")
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="SCENE_SEGMENT/SHOT_DRAFT/LOCAL_SUBJECT/TIMELINE_EVENT/PROP_HINT。")
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="对应 Draft owner 的 ID；P1 不做 polymorphic FK。")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="ASR_SEGMENT/ASR_WORD/OCR_OBSERVATION/VLM_OUTPUT/FRAME/AUDIO_RANGE/RULE。")
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True, comment="未来原始 Evidence 实体 ID；P1 表尚不存在时允许为空。")
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True, comment="可追踪 artifact/ref URI；没有实体 ID 时也可记录来源。")
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="SUPPORT", comment="SUPPORT/PRIMARY/CONFLICT/CONTEXT。")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, comment="该 Evidence 与 Draft owner 关系的置信度。")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", comment="Provenance 扩展 metadata。")
