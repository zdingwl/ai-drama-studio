import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

import httpx
from arkruntime import Ark
from pydantic import SecretStr
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.p15.schemas import (
    GenerationAudioMode,
    GenerationSegment,
    H3ReferenceCondition,
    ReplicaGenerationSegmentsContent,
    StoryboardDialogueRef,
)
from app.projects.enums import ProjectType, SourceUnderstandingProvider
from app.projects.service import get_project
from app.replica_pipeline.models import ReplicaAssetImageRevision, ReplicaH3PromptRevision, ReplicaLocalizedStoryboardRevision
from app.replica_pipeline.character_visual_design import character_visual_design_skill
from app.replica_pipeline.image_model_skills import selected_image_model_prompt_skill
from app.replica_pipeline.schemas import (
    H3_PROMPT_SCHEMA_VERSION,
    H3PromptAuthoringResult,
    H3PromptAuthoredSegment,
    H3PromptProvenance,
    H3PromptsRead,
    PipelineProviderJobProvenance,
    ReplicaAssetImagesContent,
    ReplicaLocalizedStoryboardContent,
    ResultStatus,
)
from app.replica_pipeline.video_model_skills import (
    VideoModelPromptSkillBinding,
    selected_video_model_prompt_skill,
)
from app.skills.models import ArtifactType, Capability
from app.skills.professional import ProfessionalSkillDetail
from app.target_assets.schemas import ReferenceMediaRole, TargetAssetRef, TargetAssetType
from app.workflow.models import Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import TaskCancelled, create_task_from_command, mark_task_failed, mark_task_succeeded
from app.workflow.worker import TaskExecutionContext


TASK_TYPE = "replica.h3-prompts"
MAX_SEGMENT_DURATION_US = 15_000_000
MAX_AUTHORING_BATCH_SIZE = 12
MAX_OUTPUT_TOKENS = 65536


def _sha(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _json_object(text: str) -> str:
    value = re.sub(r"<think>.*?</think>", "", text.strip(), flags=re.IGNORECASE | re.DOTALL).strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", value, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        value = fence.group(1).strip()
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        return value[start : end + 1]
    raise AppError("H3_PROMPT_PROVIDER_INVALID", "Prompt Provider 未返回 JSON object", status_code=502)


def _current(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode:
    rows = list(db.scalars(select(ArtifactNode).where(
        ArtifactNode.project_id == project_id,
        ArtifactNode.artifact_type == artifact_type.value,
        ArtifactNode.validity == ArtifactValidity.CURRENT,
        ArtifactNode.is_current.is_(True),
    )).all())
    if not rows:
        raise AppError("H3_PROMPT_INPUT_REQUIRED", f"第 4 步需要 CURRENT {artifact_type.value}", status_code=409)
    if len(rows) != 1:
        raise AppError("H3_PROMPT_INPUT_AMBIGUOUS", f"{artifact_type.value} 存在多个 CURRENT Artifact", status_code=409)
    return rows[0]


def _latest(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(select(ArtifactNode).where(
        ArtifactNode.project_id == project_id,
        ArtifactNode.artifact_type == artifact_type.value,
    ).order_by(ArtifactNode.revision.desc()).limit(1))


def _load_inputs(db: Session, project_id: str) -> tuple[ArtifactNode, ReplicaLocalizedStoryboardContent, ArtifactNode, ReplicaAssetImagesContent]:
    storyboard_artifact = _current(db, project_id, ArtifactType.TARGET_STORYBOARD)
    assets_artifact = _current(db, project_id, ArtifactType.TARGET_ASSETS)
    storyboard_row = db.scalar(select(ReplicaLocalizedStoryboardRevision).where(ReplicaLocalizedStoryboardRevision.artifact_id == storyboard_artifact.id))
    assets_row = db.scalar(select(ReplicaAssetImageRevision).where(ReplicaAssetImageRevision.artifact_id == assets_artifact.id))
    if storyboard_row is None:
        raise AppError("H3_PROMPT_REQUIRES_V2_STORYBOARD", "当前分镜不是第 2 步本土化分镜，请先按五步主链重新生成", status_code=409)
    if assets_row is None:
        raise AppError("H3_PROMPT_REQUIRES_ASSET_IMAGES", "当前资产不是第 3 步真实资产图，请先生成资产图", status_code=409)
    storyboard = ReplicaLocalizedStoryboardContent.model_validate(storyboard_row.content_json)
    assets = ReplicaAssetImagesContent.model_validate(assets_row.content_json)
    if assets.target_storyboard_artifact_id != storyboard_artifact.id:
        raise AppError("H3_PROMPT_LINEAGE_MISMATCH", "资产图不属于当前本土化分镜", status_code=409)
    return storyboard_artifact, storyboard, assets_artifact, assets


def _asset_lookup(assets: ReplicaAssetImagesContent) -> dict[str, object]:
    lookup = {item.target_entity_id: item for item in assets.assets}
    binding, prompt_skill = selected_image_model_prompt_skill()
    visual_skill = character_visual_design_skill()
    for entity_id, asset in lookup.items():
        if (
            asset.image_model_id != binding.model_id
            or asset.prompt_skill_id != prompt_skill.id
            or asset.prompt_skill_version != prompt_skill.version
            or asset.prompt_contract != binding.prompt_contract
        ):
            raise AppError(
                "H3_PROMPT_ASSET_CONTRACT_STALE",
                "当前资产图使用旧图片生成合同，请先在资产页重新生成，再进入 H3 提示词",
                status_code=409,
                details={
                    "target_entity_id": entity_id,
                    "actual_prompt_contract": asset.prompt_contract,
                    "required_prompt_contract": binding.prompt_contract,
                    "actual_prompt_skill_version": asset.prompt_skill_version,
                    "required_prompt_skill_version": prompt_skill.version,
                },
            )
        if not asset.reference_media:
            raise AppError("H3_PROMPT_REFERENCE_MISSING", "H3 Prompt 需要每个目标资产都有正式参考图", status_code=409, details={"target_entity_id": entity_id})
        if asset.asset_type == TargetAssetType.CHARACTER and (
            asset.character_visual_design is None
            or asset.character_visual_skill_id != visual_skill.id
            or asset.character_visual_skill_version != visual_skill.version
        ):
            raise AppError(
                "H3_PROMPT_CHARACTER_VISUAL_CONTRACT_STALE",
                "当前人物资产缺少最新 Character Visual Design 身份合同，请先在步骤 3 重新生成该人物资产",
                status_code=409,
                details={
                    "target_entity_id": entity_id,
                    "required_character_visual_skill": f"{visual_skill.id}@{visual_skill.version}",
                    "actual_character_visual_skill": (
                        f"{asset.character_visual_skill_id}@{asset.character_visual_skill_version}"
                        if asset.character_visual_skill_id and asset.character_visual_skill_version
                        else None
                    ),
                },
            )
        if any(not media.storage_relpath for media in asset.reference_media):
            raise AppError("H3_PROMPT_REFERENCE_PATH_MISSING", "H3 Prompt 参考图缺少受管存储路径", status_code=409, details={"target_entity_id": entity_id})
    return lookup


def _visual_entity_ids(shot) -> list[str]:
    """Return only entities that are visually present in the shot.

    Dialogue speakers that are off-screen/voice-over remain dialogue facts, but feeding their
    character image to Ref2VA can cause identity blending or hallucinate an extra person.
    """
    return list(dict.fromkeys([
        *shot.target_character_ids,
        *shot.target_scene_ids,
        *shot.target_prop_ids,
    ]))


def _media_for_role(asset, role: ReferenceMediaRole):
    return next((media for media in asset.reference_media if media.role == role), None)




def _character_identity_media_priority(asset) -> list[object]:
    """根据 H3 9 reference 限制选择人物身份参考。

    主角身份优先保留脸和正面锚点；视图数量不足时按优先级降级，
    不能静默随机丢弃参考图。
    """
    priority_roles = (
        ReferenceMediaRole.FACE,
        ReferenceMediaRole.FULL_BODY_FRONT,
        ReferenceMediaRole.FULL_BODY_SIDE,
        ReferenceMediaRole.FULL_BODY_BACK,
        ReferenceMediaRole.FULL_BODY,
    )
    result = []
    for role in priority_roles:
        media = _media_for_role(asset, role)
        if media is not None:
            result.append(media)
    return result


def _references(
    shot,
    overlapping_dialogue: list[StoryboardDialogueRef],
    assets_artifact_id: str,
    asset_by_entity: dict[str, object],
) -> tuple[list[H3ReferenceCondition], list[TargetAssetRef]]:
    del overlapping_dialogue  # dialogue facts do not imply visual presence
    visible_character_ids = list(dict.fromkeys(value for value in shot.target_character_ids if value))
    scene_ids = list(dict.fromkeys(value for value in shot.target_scene_ids if value))
    prop_ids = list(dict.fromkeys(value for value in shot.target_prop_ids if value))
    required_ids = _visual_entity_ids(shot)
    missing = [entity_id for entity_id in required_ids if entity_id not in asset_by_entity]
    if missing:
        raise AppError(
            "H3_PROMPT_ASSET_MISSING",
            "本镜头引用的目标实体缺少 CURRENT 正式资产图",
            status_code=409,
            details={"target_entity_ids": missing},
        )

    conditions: list[H3ReferenceCondition] = []
    refs: list[TargetAssetRef] = []
    seen_reference_ids: set[str] = set()

    def add_ref(asset) -> None:
        refs.append(TargetAssetRef(
            target_assets_artifact_id=assets_artifact_id,
            target_asset_id=asset.target_asset_id,
            target_asset_revision=asset.target_asset_revision,
            asset_type=asset.asset_type,
            target_entity_id=asset.target_entity_id,
        ))

    def add_condition(asset, media) -> bool:
        if media.reference_id in seen_reference_ids:
            return True
        if len(conditions) >= 9:
            return False
        assert media.storage_relpath is not None
        seen_reference_ids.add(media.reference_id)
        conditions.append(H3ReferenceCondition(
            picture_index=len(conditions) + 1,
            target_asset_id=asset.target_asset_id,
            target_entity_id=asset.target_entity_id,
            asset_type=asset.asset_type.value,
            reference_id=media.reference_id,
            reference_role=media.role.value,
            reference_uri=media.uri,
            reference_sha256=media.sha256,
            storage_relpath=media.storage_relpath,
        ))
        return True

    # Character identity owns the highest-priority Ref2VA slots. Every visually present
    # character receives the complete identity set (front/side/back/face) when available.
    # This prevents H3 from treating side/back views as unrelated people.
    for entity_id in visible_character_ids:
        asset = asset_by_entity[entity_id]
        if asset.asset_type != TargetAssetType.CHARACTER:
            raise AppError("H3_PROMPT_CHARACTER_ASSET_TYPE_INVALID", "人物引用没有绑定 CHARACTER 资产", status_code=409, details={"target_entity_id": entity_id})
        identity_media = _character_identity_media_priority(asset)
        if not identity_media:
            identity_media = [_media_for_role(asset, ReferenceMediaRole.FULL_BODY), _media_for_role(asset, ReferenceMediaRole.FACE)]
            identity_media = [media for media in identity_media if media is not None]
        if len(identity_media) < 2:
            raise AppError(
                "H3_PROMPT_CHARACTER_IDENTITY_REFERENCES_REQUIRED",
                "人物 H3 Ref2VA 缺少完整身份参考，请重新生成步骤 3 资产图",
                status_code=409,
                details={"target_entity_id": entity_id, "available_roles": [media.role.value for media in asset.reference_media]},
            )
        if len(conditions) + len(identity_media) > 9:
            raise AppError(
                "H3_PROMPT_CHARACTER_REFERENCE_CAPACITY_EXCEEDED",
                "本镜头可见人物过多，9 个 H3 reference slots 无法完整容纳人物身份参考",
                status_code=409,
                details={"target_character_ids": visible_character_ids},
            )
        add_ref(asset)
        for media in identity_media:
            add_condition(asset, media)

    # Scene and prop identity use only the slots left after all character identity pairs.
    for entity_id, preferred_role in [
        *((entity_id, ReferenceMediaRole.LAYOUT) for entity_id in scene_ids),
        *((entity_id, ReferenceMediaRole.DETAIL) for entity_id in prop_ids),
    ]:
        asset = asset_by_entity[entity_id]
        add_ref(asset)
        media = _media_for_role(asset, preferred_role) or asset.reference_media[0]
        add_condition(asset, media)
    return conditions, refs


def _dialogue_refs(shot, start_us: int, end_us: int) -> list[StoryboardDialogueRef]:
    refs: list[StoryboardDialogueRef] = []
    for item in shot.dialogue:
        if item.overlap_start_us >= end_us or item.overlap_end_us <= start_us:
            continue
        refs.append(StoryboardDialogueRef(
            utterance_id=item.utterance_id,
            utterance_number=item.utterance_number,
            delivery=item.delivery,
            target_character_id=item.target_character_id,
            final_target_dialogue=item.target_dialogue,
            target_dialogue_zh=item.target_dialogue_zh,
            planned_speech_start_us=max(start_us, item.overlap_start_us),
            planned_speech_end_us=min(end_us, item.overlap_end_us),
        ))
    return refs


@dataclass(frozen=True)
class H3SegmentDraft:
    generation_segment_id: str
    episode_id: str
    episode_order: int
    segment_number: int
    storyboard_shot_id: str
    start_us: int
    end_us: int
    duration_us: int
    output_ratio: str
    continuation_index: int
    continuation_count: int
    localized_visual_description_zh: str
    camera_description_zh: str
    camera_language: dict
    target_language: str
    dialogue_refs: tuple[StoryboardDialogueRef, ...]
    reference_conditions: tuple[H3ReferenceCondition, ...]
    target_asset_refs: tuple[TargetAssetRef, ...]
    sound_effects: tuple[str, ...]
    ambience: tuple[str, ...]

    def provider_view(self, character_names: dict[str, str]) -> dict:
        identity_groups: dict[str, dict] = {}
        for item in self.reference_conditions:
            if item.asset_type != TargetAssetType.CHARACTER.value:
                continue
            group = identity_groups.setdefault(item.target_entity_id, {
                "target_entity_id": item.target_entity_id,
                "display_name": character_names.get(item.target_entity_id),
                "face_picture_tag": None,
                "front_picture_tag": None,
                "side_picture_tag": None,
                "back_picture_tag": None,
            })
            if item.reference_role == ReferenceMediaRole.FACE.value:
                group["face_picture_tag"] = f"<Picture {item.picture_index}>"
            elif item.reference_role == ReferenceMediaRole.FULL_BODY_FRONT.value:
                group["front_picture_tag"] = f"<Picture {item.picture_index}>"
            elif item.reference_role == ReferenceMediaRole.FULL_BODY_SIDE.value:
                group["side_picture_tag"] = f"<Picture {item.picture_index}>"
            elif item.reference_role == ReferenceMediaRole.FULL_BODY_BACK.value:
                group["back_picture_tag"] = f"<Picture {item.picture_index}>"
            elif item.reference_role == ReferenceMediaRole.FULL_BODY.value:
                group["front_picture_tag"] = f"<Picture {item.picture_index}>"
        for group in identity_groups.values():
            group["identity_lock"] = (
                "FACE, FRONT, SIDE and BACK pictures are the same exact person. The FRONT view is the immutable identity anchor. "
                "Preserve facial geometry, skull shape, hairstyle silhouette, hair length, skin tone, body proportions and wardrobe identity across every frame; never redesign or mix this identity with another character."
            )
        return {
            "generation_segment_id": self.generation_segment_id,
            "duration_seconds": round(self.duration_us / 1_000_000, 3),
            "output_ratio": self.output_ratio,
            "continuation": {"index": self.continuation_index, "count": self.continuation_count},
            "localized_visual_description_zh": self.localized_visual_description_zh,
            "camera_description_zh": self.camera_description_zh,
            "camera_language": self.camera_language,
            "target_language": self.target_language,
            "references": [
                {
                    "picture_tag": f"<Picture {item.picture_index}>",
                    "asset_type": item.asset_type,
                    "target_entity_id": item.target_entity_id,
                    "display_name": character_names.get(item.target_entity_id),
                    "reference_role": item.reference_role,
                }
                for item in self.reference_conditions
            ],
            "character_identity_groups": list(identity_groups.values()),
            "dialogue": [
                {
                    "utterance_id": item.utterance_id,
                    "speaker": character_names.get(item.target_character_id or "", "Actor"),
                    "delivery": item.delivery.value,
                    "target_dialogue": item.final_target_dialogue,
                    "target_dialogue_zh_review_only": item.target_dialogue_zh,
                }
                for item in self.dialogue_refs
            ],
            "ambience": list(self.ambience),
            "sound_effects": list(self.sound_effects),
        }


def _build_drafts(
    storyboard: ReplicaLocalizedStoryboardContent,
    assets_artifact: ArtifactNode,
    assets: ReplicaAssetImagesContent,
) -> tuple[list[H3SegmentDraft], dict[str, str]]:
    asset_by_entity = _asset_lookup(assets)
    entity_names = {
        **{item.target_character_id: item.display_name for item in storyboard.characters},
        **{item.target_scene_id: item.display_name for item in storyboard.scenes},
        **{item.target_prop_id: item.display_name for item in storyboard.props},
    }
    drafts: list[H3SegmentDraft] = []
    episode_counts: dict[str, int] = {}
    for shot in sorted(storyboard.shots, key=lambda item: (item.episode_order, item.shot_number)):
        part_count = max(1, math.ceil(shot.duration_us / MAX_SEGMENT_DURATION_US))
        for part_index in range(part_count):
            start_us = shot.start_us + part_index * MAX_SEGMENT_DURATION_US
            end_us = min(shot.end_us, start_us + MAX_SEGMENT_DURATION_US)
            dialogue_refs = _dialogue_refs(shot, start_us, end_us)
            conditions, asset_refs = _references(shot, dialogue_refs, assets_artifact.id, asset_by_entity)
            episode_counts[shot.episode_id] = episode_counts.get(shot.episode_id, 0) + 1
            segment_number = episode_counts[shot.episode_id]
            drafts.append(H3SegmentDraft(
                generation_segment_id=f"h3:{shot.episode_id}:{segment_number:04d}",
                episode_id=shot.episode_id,
                episode_order=shot.episode_order,
                segment_number=segment_number,
                storyboard_shot_id=shot.storyboard_shot_id,
                start_us=start_us,
                end_us=end_us,
                duration_us=end_us - start_us,
                output_ratio=shot.output_ratio,
                continuation_index=part_index + 1,
                continuation_count=part_count,
                localized_visual_description_zh=shot.localized_visual_description_zh,
                camera_description_zh=shot.camera_description_zh,
                camera_language=shot.camera_language.model_dump(mode="json"),
                target_language=storyboard.target_language,
                dialogue_refs=tuple(dialogue_refs),
                reference_conditions=tuple(conditions),
                target_asset_refs=tuple(asset_refs),
                sound_effects=tuple(shot.sound_effects),
                ambience=tuple(shot.ambience),
            ))
    if not drafts:
        raise AppError("H3_PROMPT_EMPTY", "本土化分镜没有可生成的视频段", status_code=409)
    return drafts, entity_names


@dataclass(frozen=True)
class PromptAuthorInput:
    binding: VideoModelPromptSkillBinding
    skill: ProfessionalSkillDetail
    segments: tuple[dict, ...]


@dataclass(frozen=True)
class PromptAuthorResult:
    content: H3PromptAuthoringResult
    remote_job_id: str | None = None


class PromptAuthorProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self) -> dict: ...
    def author(self, payload: PromptAuthorInput) -> PromptAuthorResult: ...


def _authoring_prompt(payload: PromptAuthorInput) -> str:
    schema = H3PromptAuthoringResult.model_json_schema()
    rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(payload.skill.provider_rules, 1))
    return f"""你正在执行 AI Drama Studio 的视频模型专属 Professional Skill。

目标视频模型：{payload.binding.model_id}
Prompt Skill：{payload.skill.id}@{payload.skill.version}
Prompt Contract：{payload.binding.prompt_contract}

这是 Skill 执行，不是通用提示词润色。你只能把已经定稿的本土化分镜事实与已确认参考资产编译成该视频模型可执行的提示词，不能重新编故事、改对白、替换人物、改变镜头事实或发明参考图。

Professional Skill provider rules：
{rules}

Professional Skill manual：
{payload.skill.manual}

强制输出规则：
- 对每个输入 generation_segment_id 精确输出一次，不得漏项、重复或增加 segment。
- execution_prompt 必须明确使用输入给出的每个 <Picture N>，且不得出现不存在的 Picture slot。
- character_identity_groups 是人物身份硬约束：每组 FACE + FULL_BODY 属于同一个人。execution_prompt 必须按人物姓名同时绑定这两个 Picture，并明确锁定脸型五官比例、年龄感、发型发色、肤色、体态与基础服装身份；镜头只允许改变姿态、表情和观察角度，禁止换脸、年龄漂移、发型漂移、体型漂移、角色互换或把两个人的特征混合。
- 不在 shot.target_character_ids 中的画外音/旁白说话人不得因为有对白就被当作视觉人物参考；其声音事实只通过 dialogue 编译。
- target_dialogue 必须原样、完整、只出现一次；不得翻译、删改、补写或增加其他对白。
- target_dialogue_zh_review_only 只帮助你理解，不允许作为第二句台词写入 execution_prompt。
- 必须要求 native synchronized picture + audio，并让人物口型与所给目标语言对白匹配。
- 镜头运动、构图、动作、环境音和音效都来自输入事实；不要擅自增加剧情事件。
- negative_prompt 只写要避免的生成错误，不加入新的正向剧情要求。
- review_prompt_zh 用简体中文概括该 execution_prompt，供中国用户审核；这里可以展示“目标对白 + 中文理解”，但 execution_prompt 中只能说目标语言对白。
- 只输出符合 JSON Schema 的 JSON object，不要 Markdown，不要解释。

待编译分段：
{json.dumps(payload.segments, ensure_ascii=False, separators=(",", ":"))}

输出 JSON Schema：
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}
"""


def _parse_authoring(text: str) -> H3PromptAuthoringResult:
    try:
        return H3PromptAuthoringResult.model_validate_json(_json_object(text))
    except Exception as exc:
        if isinstance(exc, AppError):
            raise
        raise AppError("H3_PROMPT_PROVIDER_SCHEMA_INVALID", "Prompt Provider 输出不符合 H3 Prompt typed contract", status_code=502) from exc


class _DoubaoPromptAuthor:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError("H3_PROMPT_PROVIDER_NOT_CONFIGURED", "H3 Prompt Skill 的火山引擎执行 Provider 尚未配置", status_code=409)

    def profile(self) -> dict:
        return {"provider": self.provider_name, "model": self.model_name, "mode": "CLOUD_TEXT_SKILL_EXECUTOR"}

    def author(self, payload: PromptAuthorInput) -> PromptAuthorResult:
        assert self.settings.p7_doubao_api_key is not None
        client = Ark(
            api_key=self.settings.p7_doubao_api_key.get_secret_value(),
            base_url=self.settings.p7_doubao_base_url,
            timeout=self.settings.p7_doubao_request_timeout_seconds,
            max_retries=2,
        )
        response = client.responses.create(
            model=self.model_name,
            input=[{"role": "user", "content": [{"type": "input_text", "text": _authoring_prompt(payload)}]}],
            thinking={"type": "enabled"},
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        text = getattr(response, "output_text", None)
        if not isinstance(text, str) or not text.strip():
            chunks: list[str] = []
            for item in getattr(response, "output", None) or []:
                for part in getattr(item, "content", None) or []:
                    if getattr(part, "type", None) == "output_text" and getattr(part, "text", None):
                        chunks.append(str(part.text))
            text = "".join(chunks)
        if not isinstance(text, str) or not text.strip():
            raise AppError("H3_PROMPT_PROVIDER_EMPTY", "H3 Prompt Skill Provider 未返回可用文本", status_code=502)
        return PromptAuthorResult(
            content=_parse_authoring(text),
            remote_job_id=str(getattr(response, "id", "") or "") or None,
        )


class _LocalQwenPromptAuthor:
    provider_name = "local-vllm"

    def __init__(self, settings: Settings, *, model_name: str, base_url: str, api_key: SecretStr | None):
        self.settings = settings
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def profile(self) -> dict:
        return {"provider": self.provider_name, "model": self.model_name, "base_url": self.base_url, "mode": "LOCAL_TEXT_SKILL_EXECUTOR"}

    def author(self, payload: PromptAuthorInput) -> PromptAuthorResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key is not None and self.api_key.get_secret_value().strip():
            headers["Authorization"] = f"Bearer {self.api_key.get_secret_value()}"
        with httpx.Client(timeout=httpx.Timeout(self.settings.p7_qwen_local_request_timeout_seconds)) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": _authoring_prompt(payload)}],
                    "temperature": 0.1,
                    "max_tokens": MAX_OUTPUT_TOKENS,
                },
            )
            response.raise_for_status()
            body = response.json()
        choices = body.get("choices") or []
        text = ((choices[0].get("message") or {}).get("content") if choices else None)
        if not isinstance(text, str) or not text.strip():
            raise AppError("H3_PROMPT_PROVIDER_EMPTY", "H3 Prompt Skill Provider 未返回可用文本", status_code=502)
        return PromptAuthorResult(content=_parse_authoring(text), remote_job_id=str(body.get("id") or "") or None)


def _prompt_author_provider(settings: Settings, selection: SourceUnderstandingProvider) -> PromptAuthorProvider:
    if selection == SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API:
        return _DoubaoPromptAuthor(settings)
    if selection == SourceUnderstandingProvider.QWEN3_8_27B_LOCAL:
        return _LocalQwenPromptAuthor(
            settings,
            model_name=settings.p7_qwen38_local_model,
            base_url=settings.p7_qwen38_local_base_url,
            api_key=settings.p7_qwen38_local_api_key,
        )
    if selection in {SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL, SourceUnderstandingProvider.QWEN3_VL_LOCAL}:
        return _LocalQwenPromptAuthor(
            settings,
            model_name=settings.p7_qwen3_vl_8b_local_model,
            base_url=settings.p7_qwen3_vl_8b_local_base_url,
            api_key=settings.p7_qwen3_vl_8b_local_api_key,
        )
    raise AppError("H3_PROMPT_PROVIDER_UNSUPPORTED", "当前 H3 Prompt Skill 执行 Provider 未实现", status_code=422)


def _validate_authored_batch(drafts: list[H3SegmentDraft], authored: H3PromptAuthoringResult) -> dict[str, H3PromptAuthoredSegment]:
    expected_ids = [item.generation_segment_id for item in drafts]
    actual_ids = [item.generation_segment_id for item in authored.segments]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
        raise AppError(
            "H3_PROMPT_PROVIDER_COVERAGE_INVALID",
            "Prompt Skill Provider 必须精确覆盖本批全部 GenerationSegment",
            status_code=502,
            details={"expected": expected_ids, "actual": actual_ids},
        )
    by_id = {item.generation_segment_id: item for item in authored.segments}
    for draft in drafts:
        item = by_id[draft.generation_segment_id]
        picture_tags = {int(value) for value in re.findall(r"<Picture\s+(\d+)>", item.execution_prompt, flags=re.IGNORECASE)}
        expected_tags = set(range(1, len(draft.reference_conditions) + 1))
        if picture_tags != expected_tags:
            raise AppError(
                "H3_PROMPT_REFERENCE_COVERAGE_INVALID",
                "模型专属提示词的 Picture slots 与正式 reference_conditions 不一致",
                status_code=502,
                details={"generation_segment_id": draft.generation_segment_id, "expected": sorted(expected_tags), "actual": sorted(picture_tags)},
            )
        for dialogue in draft.dialogue_refs:
            spoken = dialogue.final_target_dialogue.strip()
            if not spoken or item.execution_prompt.count(spoken) != 1:
                raise AppError(
                    "H3_PROMPT_DIALOGUE_CONTRACT_INVALID",
                    "模型专属提示词必须原样且只包含一次正式目标对白",
                    status_code=502,
                    details={"generation_segment_id": draft.generation_segment_id, "utterance_id": dialogue.utterance_id},
                )
            review_zh = (dialogue.target_dialogue_zh or "").strip()
            if review_zh and review_zh != spoken and review_zh in item.execution_prompt:
                raise AppError(
                    "H3_PROMPT_REVIEW_TRANSLATION_LEAKED",
                    "中文理解翻译不得作为 H3 execution prompt 的第二句对白",
                    status_code=502,
                    details={"generation_segment_id": draft.generation_segment_id, "utterance_id": dialogue.utterance_id},
                )
    return by_id


def _compile_segments(
    storyboard_artifact: ArtifactNode,
    assets_artifact: ArtifactNode,
    binding: VideoModelPromptSkillBinding,
    skill: ProfessionalSkillDetail,
    drafts: list[H3SegmentDraft],
    authored_by_id: dict[str, H3PromptAuthoredSegment],
) -> ReplicaGenerationSegmentsContent:
    segments: list[GenerationSegment] = []
    for draft in drafts:
        authored = authored_by_id[draft.generation_segment_id]
        segments.append(GenerationSegment(
            generation_segment_id=draft.generation_segment_id,
            episode_id=draft.episode_id,
            episode_order=draft.episode_order,
            segment_number=draft.segment_number,
            storyboard_shot_ids=[draft.storyboard_shot_id],
            start_us=draft.start_us,
            end_us=draft.end_us,
            duration_us=draft.duration_us,
            output_ratio=draft.output_ratio,
            continuation_index=draft.continuation_index,
            continuation_count=draft.continuation_count,
            generation_prompt=authored.execution_prompt,
            negative_prompt=authored.negative_prompt,
            prompt_skill_id=skill.id,
            prompt_skill_version=skill.version,
            prompt_contract=binding.prompt_contract,
            model_id=binding.model_id,
            review_prompt_zh=authored.review_prompt_zh,
            reference_conditions=list(draft.reference_conditions),
            target_asset_refs=list(draft.target_asset_refs),
            audio_generation_mode=GenerationAudioMode.NATIVE_AUDIO_VIDEO,
            dialogue_refs=list(draft.dialogue_refs),
            sound_effects=list(draft.sound_effects),
            ambience=list(draft.ambience),
            requires_lip_sync=False,
        ))
    return ReplicaGenerationSegmentsContent(
        schema_version=H3_PROMPT_SCHEMA_VERSION,
        title="MiniMax H3 多参考音画同步提示词",
        target_storyboard_artifact_id=storyboard_artifact.id,
        target_assets_artifact_id=assets_artifact.id,
        max_segment_duration_us=MAX_SEGMENT_DURATION_US,
        segments=segments,
    )


def create_h3_prompt_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project = get_project(db, project_id)
    if project.project_type != ProjectType.REPLICA:
        raise AppError("H3_PROMPT_PROJECT_UNSUPPORTED", "当前五步主生产链只正式支持 REPLICA", status_code=422)
    storyboard_artifact, _, assets_artifact, _ = _load_inputs(db, project_id)
    settings = get_settings()
    binding, skill = selected_video_model_prompt_skill(settings)
    provider = _prompt_author_provider(settings, project.source_understanding_provider)
    fingerprint = _sha({
        "storyboard": [storyboard_artifact.id, storyboard_artifact.revision, storyboard_artifact.input_fingerprint],
        "assets": [assets_artifact.id, assets_artifact.revision, assets_artifact.input_fingerprint],
        "video_model": binding.model_id,
        "prompt_skill": [skill.id, skill.version],
        "prompt_contract": binding.prompt_contract,
        "prompt_provider": provider.profile(),
        "generation_request": idempotency_key.strip(),
    })
    task = create_task_from_command(db, project_id=project_id, idempotency_key=idempotency_key, payload=TaskCommandCreate(
        task_type=TASK_TYPE,
        task_name="用 MiniMax H3 Prompt Skill 生成多参考音画提示词",
        input_fingerprint=fingerprint,
        input_artifact_ids=[storyboard_artifact.id, assets_artifact.id],
        max_attempts=3,
    ))
    if task.status == TaskStatus.QUEUED and not (task.checkpoint_json or {}).get("h3_prompt_generation_sequence"):
        sequence = int(db.scalar(select(func.count(Task.id)).where(Task.project_id == project_id, Task.task_type == TASK_TYPE)) or 0)
        task.checkpoint_json = {**(task.checkpoint_json or {}), "h3_prompt_generation_sequence": max(1, sequence)}
        db.add(task)
        db.commit()
        db.refresh(task)
    return task


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != TASK_TYPE or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
        return None
    now = utc_now()
    result = db.execute(update(Task).where(
        Task.id == task_id,
        Task.task_type == TASK_TYPE,
        Task.status == TaskStatus.QUEUED,
        Task.attempt < Task.max_attempts,
    ).values(
        status=TaskStatus.RUNNING,
        attempt=task.attempt + 1,
        worker_id=worker_id,
        heartbeat_at=now,
        started_at=task.started_at if task.started_at is not None else now,
        finished_at=None,
        updated_at=now,
    ))
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    return db.get(Task, task_id)


def _publish(
    db: Session,
    task: TaskWorkerRead,
    content: ReplicaGenerationSegmentsContent,
    *,
    binding: VideoModelPromptSkillBinding,
    skill: ProfessionalSkillDetail,
    provider: PromptAuthorProvider,
    provider_jobs: list[PipelineProviderJobProvenance],
) -> ArtifactNode:
    project = get_project(db, task.project_id)
    storyboard_artifact, _, assets_artifact, _ = _load_inputs(db, task.project_id)
    if content.target_storyboard_artifact_id != storyboard_artifact.id or content.target_assets_artifact_id != assets_artifact.id:
        raise AppError("H3_PROMPT_STALE_INPUT", "Prompt 编译期间上游分镜或资产已经变化", status_code=409)
    previous = db.scalar(select(ArtifactNode).where(
        ArtifactNode.project_id == task.project_id,
        ArtifactNode.artifact_type == ArtifactType.GENERATION_SEGMENTS.value,
        ArtifactNode.is_current.is_(True),
        ArtifactNode.validity == ArtifactValidity.CURRENT,
    ))
    latest = _latest(db, task.project_id, ArtifactType.GENERATION_SEGMENTS)
    generation_sequence = int((task.checkpoint_json or {}).get("h3_prompt_generation_sequence") or 1)
    if previous is not None:
        _mark_stale_with_downstream(db, [previous])
    artifact = ArtifactNode(
        project_id=task.project_id,
        artifact_type=ArtifactType.GENERATION_SEGMENTS.value,
        namespace=ArtifactNamespace.PRODUCTION,
        label="MiniMax H3 多参考音画提示词",
        revision=(latest.revision if latest else 0) + 1,
        input_fingerprint=_sha({"task": task.input_fingerprint, "content": content.model_dump(mode="json")}),
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={
            "schema_version": H3_PROMPT_SCHEMA_VERSION,
            "prompt_contract": binding.prompt_contract,
            "model_id": binding.model_id,
            "prompt_skill_id": skill.id,
            "prompt_skill_version": skill.version,
            "segment_count": len(content.segments),
            "reference_count": sum(len(item.reference_conditions) for item in content.segments),
            "prompt_provider": provider.provider_name,
            "prompt_model": provider.model_name,
            "generation_sequence": generation_sequence,
        },
    )
    db.add(artifact)
    db.flush()
    provenance = H3PromptProvenance(
        target_storyboard_artifact_id=storyboard_artifact.id,
        target_storyboard_revision=storyboard_artifact.revision,
        target_storyboard_fingerprint=storyboard_artifact.input_fingerprint,
        target_assets_artifact_id=assets_artifact.id,
        target_assets_revision=assets_artifact.revision,
        target_assets_fingerprint=assets_artifact.input_fingerprint,
        generation_sequence=generation_sequence,
        professional_skill_id=skill.id,
        professional_skill_version=skill.version,
        model_id=binding.model_id,
        prompt_contract=binding.prompt_contract,
        prompt_provider=provider.provider_name,
        prompt_model=provider.model_name,
        provider_jobs=provider_jobs,
        generated_by_task_id=task.id,
    )
    db.add(ReplicaH3PromptRevision(
        project_id=task.project_id,
        artifact_id=artifact.id,
        target_storyboard_artifact_id=storyboard_artifact.id,
        target_assets_artifact_id=assets_artifact.id,
        generated_by_task_id=task.id,
        schema_version=H3_PROMPT_SCHEMA_VERSION,
        content_json=content.model_dump(mode="json"),
        provenance_json=provenance.model_dump(mode="json"),
    ))
    db.add(ArtifactEdge(project_id=task.project_id, source_node_id=storyboard_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
    db.add(ArtifactEdge(project_id=task.project_id, source_node_id=assets_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.USES))
    if latest is not None:
        db.add(ArtifactEdge(project_id=task.project_id, source_node_id=artifact.id, target_node_id=latest.id, relation_type=ArtifactRelationType.SUPERSEDES))
    _invalidate_project_plan(db, project)
    db.commit()
    db.refresh(artifact)
    return artifact


def run_h3_prompt_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"h3-prompt-{uuid4()}"
    with session_factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        task = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=task.id, worker_id=worker_id)
    try:
        settings = get_settings()
        with session_factory() as db:
            project = get_project(db, task.project_id)
            storyboard_artifact, storyboard, assets_artifact, assets = _load_inputs(db, task.project_id)
        binding, skill = selected_video_model_prompt_skill(settings)
        provider = _prompt_author_provider(settings, project.source_understanding_provider)
        drafts, entity_names = _build_drafts(storyboard, assets_artifact, assets)
        authored_by_id: dict[str, H3PromptAuthoredSegment] = {}
        provider_job_refs: list[PipelineProviderJobProvenance] = []
        batches = [drafts[index : index + MAX_AUTHORING_BATCH_SIZE] for index in range(0, len(drafts), MAX_AUTHORING_BATCH_SIZE)]
        for batch_index, batch in enumerate(batches, 1):
            payload = PromptAuthorInput(
                binding=binding,
                skill=skill,
                segments=tuple(item.provider_view(entity_names) for item in batch),
            )
            provider_payload = {
                "video_model": binding.model_id,
                "prompt_skill": [skill.id, skill.version],
                "prompt_contract": binding.prompt_contract,
                "target_storyboard_artifact_id": storyboard_artifact.id,
                "target_assets_artifact_id": assets_artifact.id,
                "batch_index": batch_index,
                "batch_count": len(batches),
                "generation_segment_ids": [item.generation_segment_id for item in batch],
                "semantic_payload_fingerprint": _sha(payload.segments),
                "provider_profile": provider.profile(),
            }

            def _remote_call(_):
                result = provider.author(payload)
                return ProviderDispatchResult(value=result, remote_job_id=result.remote_job_id)

            with session_factory() as db:
                job, dispatched = dispatch_provider_call(
                    db,
                    task_id=task.id,
                    provider=provider.provider_name,
                    model=provider.model_name,
                    capability=Capability.MODEL_PROMPTING,
                    payload=provider_payload,
                    artifact_id=storyboard_artifact.id,
                    remote_call=_remote_call,
                )
            result: PromptAuthorResult = dispatched.value
            authored_by_id.update(_validate_authored_batch(batch, result.content))
            provider_job_refs.append(PipelineProviderJobProvenance(
                provider_job_id=job.id,
                provider=job.provider,
                model=job.model,
                payload_fingerprint=job.payload_fingerprint,
            ))
            context.checkpoint(
                {
                    "stage": "prompt-skill-execution",
                    "prompt_skill": f"{skill.id}@{skill.version}",
                    "provider_job_ids": [item.provider_job_id for item in provider_job_refs],
                    "batch": batch_index,
                    "batch_count": len(batches),
                },
                progress_percent=min(88, 10 + int(batch_index / len(batches) * 78)),
            )
        content = _compile_segments(storyboard_artifact, assets_artifact, binding, skill, drafts, authored_by_id)
        context.checkpoint({"stage": "publish", "segment_count": len(content.segments)}, progress_percent=94)
        with session_factory() as db:
            _publish(
                db,
                task,
                content,
                binding=binding,
                skill=skill,
                provider=provider,
                provider_jobs=provider_job_refs,
            )
            mark_task_succeeded(db, task.id, worker_id=worker_id)
    except TaskCancelled:
        return
    except AppError as exc:
        with session_factory() as db:
            mark_task_failed(db, task.id, safe_error=f"H3 提示词生成失败（{exc.code}）：{exc.message}", worker_id=worker_id)
    except Exception as exc:
        with session_factory() as db:
            mark_task_failed(db, task.id, safe_error=f"H3 提示词生成失败（{type(exc).__name__}）", worker_id=worker_id)


def _read_h3_prompt_provenance(raw: dict, artifact: ArtifactNode) -> H3PromptProvenance:
    payload = dict(raw or {})
    if "generation_sequence" not in payload:
        metadata = artifact.metadata_json or {}
        metadata_sequence = metadata.get("generation_sequence")
        if isinstance(metadata_sequence, int) and not isinstance(metadata_sequence, bool) and metadata_sequence >= 1:
            payload["generation_sequence"] = metadata_sequence
        else:
            payload["generation_sequence"] = max(1, artifact.revision)
    return H3PromptProvenance.model_validate(payload)


def get_h3_prompts(db: Session, project_id: str) -> H3PromptsRead:
    get_project(db, project_id)
    current = db.scalar(select(ArtifactNode).where(
        ArtifactNode.project_id == project_id,
        ArtifactNode.artifact_type == ArtifactType.GENERATION_SEGMENTS.value,
        ArtifactNode.is_current.is_(True),
        ArtifactNode.validity == ArtifactValidity.CURRENT,
    ))
    latest = current or _latest(db, project_id, ArtifactType.GENERATION_SEGMENTS)
    if latest is None:
        return H3PromptsRead(project_id=project_id, status=ResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaH3PromptRevision).where(ReplicaH3PromptRevision.artifact_id == latest.id))
    if row is None:
        return H3PromptsRead(project_id=project_id, status=ResultStatus.NOT_BUILT)
    return H3PromptsRead(
        project_id=project_id,
        status=ResultStatus.CURRENT if current is not None else ResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=ReplicaGenerationSegmentsContent.model_validate(row.content_json).model_dump(mode="json"),
        provenance=_read_h3_prompt_provenance(row.provenance_json, latest),
    )
