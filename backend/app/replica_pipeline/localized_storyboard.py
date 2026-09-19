import hashlib
import json
import re
from dataclasses import dataclass, replace
from itertools import groupby
from typing import Any, Protocol
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
from app.projects.enums import ProjectType, SourceUnderstandingProvider
from app.projects.service import get_project
from app.replica_pipeline.models import ReplicaAssetImageRevision, ReplicaLocalizedStoryboardCandidate, ReplicaLocalizedStoryboardRevision
from app.replica_pipeline.h3_audit import dialogue_owner_windows, estimate_spoken_seconds, estimated_speech_fits
from app.replica_pipeline.schemas import (
    CandidateStatus,
    LOCALIZED_STORYBOARD_SCHEMA_VERSION,
    LocalizedShotDialogueRef,
    LocalizedStoryboardCandidateRead,
    LocalizedStoryboardDialogue,
    LocalizedStoryboardProvenance,
    LocalizedStoryboardRead,
    LocalizedStoryboardShotEditCommand,
    LocalizedStoryboardSemantic,
    LocalizedStoryboardShot,
    LocalizedTargetCharacter,
    LocalizedTargetProp,
    LocalizedTargetScene,
    PipelineProviderJobProvenance,
    PipelineReviewCommand,
    ReplicaLocalizedStoryboardContent,
    ReplicaAssetImagesContent,
    ResultStatus,
)
from app.shot_breakdown.schemas import DialogueDelivery
from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill
from app.source_snapshot.models import SourceVideoSnapshotRevision
from app.source_snapshot.schemas import SourceVideoSnapshotContent
from app.workflow.models import ProviderJob, Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import TaskCancelled, create_task_from_command, mark_task_failed, mark_task_succeeded
from app.workflow.worker import TaskExecutionContext


TASK_TYPE = "replica.localized-storyboard"
SKILL_ID = "storyboard-localization"
MAX_OUTPUT_TOKENS = 65536
LOCALIZATION_BATCH_SHOTS = 8


def _sha(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _stable_target_id(project_id: str, kind: str, source_id: str, target_region: str) -> str:
    digest = hashlib.sha256(f"{project_id}|{kind}|{source_id}|{target_region}".encode()).hexdigest()[:20]
    return f"target:{kind}:{digest}"


def _nearest_h3_ratio(width: int, height: int) -> str:
    ratios = {"21:9": 21 / 9, "16:9": 16 / 9, "4:3": 4 / 3, "1:1": 1.0, "3:4": 3 / 4, "9:16": 9 / 16}
    actual = width / height
    return min(ratios, key=lambda key: abs(ratios[key] - actual))


def _json_object(text: str) -> str:
    value = re.sub(r"<think>.*?</think>", "", text.strip(), flags=re.IGNORECASE | re.DOTALL).strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", value, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        value = fence.group(1).strip()
    start, end = value.find("{"), value.rfind("}")
    if start >= 0 and end > start:
        return value[start : end + 1]
    raise AppError("LOCALIZED_STORYBOARD_PROVIDER_INVALID", "本土化分镜 Provider 未返回 JSON object", status_code=502)


def _assert_chinese(label: str, value: str, *, minimum_cjk: int = 4) -> None:
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", value))
    if cjk < minimum_cjk:
        raise AppError(
            "LOCALIZED_STORYBOARD_REVIEW_LANGUAGE_INVALID",
            f"{label} 必须提供可供中国用户理解的简体中文描述",
            status_code=502,
        )


@dataclass(frozen=True)
class LocalizationProviderInput:
    target_language: str
    target_region: str
    scene_strategy: str
    visual_style: str
    source_view: dict
    expected_character_ids: tuple[str, ...]
    expected_scene_ids: tuple[str, ...]
    expected_prop_ids: tuple[str, ...]
    expected_dialogue_ids: tuple[str, ...]
    expected_shot_ids: tuple[str, ...]
    frozen_identity_names: dict[str, str] | None = None
    operation: str = "LOCALIZE_SHOTS"
    frozen_world_plan: LocalizedStoryboardSemantic | None = None


@dataclass(frozen=True)
class LocalizationProviderResult:
    semantic: LocalizedStoryboardSemantic
    remote_job_id: str | None = None


class LocalizationProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self) -> dict: ...
    def localize(self, payload: LocalizationProviderInput, *, correction_issues: list[dict] | None = None) -> LocalizationProviderResult: ...


def _provider_prompt(payload: LocalizationProviderInput, correction_issues: list[dict] | None = None) -> str:
    skill = get_professional_skill(SKILL_ID)
    rules = "\n".join(f"{idx}. {rule}" for idx, rule in enumerate(skill.provider_rules, 1))
    schema = LocalizedStoryboardSemantic.model_json_schema()
    phase = (
        "先规划全部剧集共用的目标世界。输入中的所有镜头与对白仅供了解剧情，"
        "本次不得逐镜改写：shots 和 dialogue 必须返回空数组。"
        "必须输出 world_design_zh、非空 continuity_rules_zh，以及完整 characters/scenes/props 定义。"
        "先确定人物完整姓名、家庭关系和称谓、外形服装、场景地址房号与空间关系、装修、道具和金额规则，"
        "再自查整套设定一致。必须根据目标语言和地区重新设计，不得默认沿用原片演员外形、姓氏和家具。"
        "目标语言不等于族裔，不强制任何种族，也不得自动把整部剧改为移民故事。"
        "人物肤色、脸型、发型、体型、服装须有具体可执行的目标设定；场景必须有具体布局、材质和装修。"
        "所有中文审核描述以目标版本自身为主，不写‘保留原设定’或‘对应原剧情金额’等代替具体设计。"
        if payload.operation == "PLAN_WORLD" else
        "按冻结目标世界逐镜改写。characters/scenes/props 返回空数组，由服务端从规划绑定。"
        "world_design_zh 返回空字符串，continuity_rules_zh 返回空数组，不重复或改写规划。"
        "仅输出本批 shots/dialogue。画面必须落实冻结人物外形、服装和场景装修，不能照抄原片视觉。"
        "人名、称谓、家庭关系、地址房号、物件和金额严格使用同一规划；禁止自行起别名或换住宅类型。"
    )
    return f"""你正在执行 AI Drama Studio Professional Skill：{skill.name}（{skill.id}@{skill.version}）。

任务不是写一份独立 Target Bible，也不是只翻译对白；你必须直接把正式原片分镜表改写成目标地区成立的本土化分镜。

当前操作：{payload.operation}
{phase}

目标：
- target_language: {payload.target_language}
- target_region: {payload.target_region}
- scene_strategy: {payload.scene_strategy}
- visual_style: {payload.visual_style}

硬规则：
- 本次要求输出的实体/镜头/对白必须严格覆盖下方输出 ID 清单；空清单返回空数组。不得漏项、重复、合并、拆分或创造 ID。
- localized_visual_description_zh / camera_description_zh / entity description / target_dialogue_zh 必须使用简体中文，供中国用户理解和审核。
- target_dialogue 必须是 {payload.target_language} 的本土自然对白；target_dialogue_zh 是它的中文意思，不是第二句要说出的对白。
- source start/end/duration 是权威时间轴，服务端确定性绑定；不得输出、规划或修改镜头时长。
- 每条 dialogue 必须在其权威 source overlap 语音窗内自然说完；若直译超时，必须缩短为自然口语，不得把问题留给 H3 Prompt 或视频生成阶段。
- 不改变 shot 顺序、shot anchor、start/end/duration 或结构化 camera facts。
- 必须按目标地区重新规划人物姓名、外形服装、社会身份、地点装修、文化物件和自然表达，但不得改写故事事件顺序、核心关系或动作逻辑。
- 不生成资产图片、H3 prompt、音频、视频或 Artifact/target entity ID。
- frozen_identity_names 是前置批次已冻结的目标实体名称；同一 source identity 在后续批次必须逐字复用，不得另起英文名、昵称、姓氏或家庭名。
- 只输出一个符合 JSON Schema 的 object，不输出 Markdown 或解释。

Professional Skill rules:
{rules}

正式 Source storyboard view：
{json.dumps(payload.source_view, ensure_ascii=False, separators=(",", ":"))}

已冻结目标身份名称：
{json.dumps(payload.frozen_identity_names or {}, ensure_ascii=False, separators=(",", ":"))}

冻结目标世界（目标视觉权威；原片画面仅提供剧情动作与构图依据）：
{payload.frozen_world_plan.model_dump_json() if payload.frozen_world_plan else "null"}

本次输出 ID 清单：
{json.dumps({"characters": list(payload.expected_character_ids) if payload.frozen_world_plan is None else [], "scenes": list(payload.expected_scene_ids) if payload.frozen_world_plan is None else [], "props": list(payload.expected_prop_ids) if payload.frozen_world_plan is None else [], "dialogue": list(payload.expected_dialogue_ids), "shots": list(payload.expected_shot_ids)}, ensure_ascii=False)}

上一次输出的定向修正清单（仅在非空时适用）：
{json.dumps(correction_issues or [], ensure_ascii=False, separators=(",", ":"))}

若修正清单非空：逐项修复。对白超时只能缩短 target_dialogue；目标设定漂移必须恢复冻结规划。

输出 JSON Schema：
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}
"""


def _validate_semantic(payload: LocalizationProviderInput, semantic: LocalizedStoryboardSemantic) -> LocalizedStoryboardSemantic:
    if payload.frozen_world_plan is not None:
        updates = {}
        for field, id_field, expected in (
            ("characters", "source_character_id", payload.expected_character_ids),
            ("scenes", "source_scene_id", payload.expected_scene_ids),
            ("props", "source_prop_id", payload.expected_prop_ids),
        ):
            planned = {getattr(item, id_field): item for item in getattr(payload.frozen_world_plan, field)}
            returned = getattr(semantic, field)
            returned_ids = [getattr(item, id_field) for item in returned]
            if len(set(returned_ids)) != len(returned_ids) or any(
                getattr(item, id_field) not in expected or planned.get(getattr(item, id_field)) != item
                for item in returned
            ):
                raise AppError("LOCALIZED_STORYBOARD_WORLD_PLAN_DRIFT", "镜头批次不得重新设计已冻结人物、场景或道具", status_code=502,
                               details={"issues": [{"field": field, "repair": "使用冻结目标世界，不重新返回实体定义"}]})
            updates[field] = [planned[item] for item in expected]
        updates["world_design_zh"] = payload.frozen_world_plan.world_design_zh
        updates["continuity_rules_zh"] = payload.frozen_world_plan.continuity_rules_zh
        semantic = semantic.model_copy(update=updates)
    if payload.operation == "PLAN_WORLD":
        _assert_chinese("目标世界整体设定", semantic.world_design_zh)
        if not semantic.continuity_rules_zh:
            raise AppError("LOCALIZED_STORYBOARD_WORLD_PLAN_REQUIRED", "目标世界缺少跨镜连续性规则", status_code=502)
        for rule in semantic.continuity_rules_zh:
            _assert_chinese("目标世界连续性规则", rule)
    coverage = (
        (payload.expected_character_ids, [item.source_character_id for item in semantic.characters], "character"),
        (payload.expected_scene_ids, [item.source_scene_id for item in semantic.scenes], "scene"),
        (payload.expected_prop_ids, [item.source_prop_id for item in semantic.props], "prop"),
        (payload.expected_dialogue_ids, [item.utterance_id for item in semantic.dialogue], "dialogue"),
        (payload.expected_shot_ids, [item.shot_anchor_id for item in semantic.shots], "shot"),
    )
    for expected, actual, label in coverage:
        if len(actual) != len(set(actual)) or set(actual) != set(expected):
            expected_set = set(expected)
            actual_set = set(actual)
            duplicates = sorted({item for item in actual if actual.count(item) > 1})
            missing = sorted(expected_set - actual_set)
            unexpected = sorted(actual_set - expected_set)
            raise AppError(
                "LOCALIZED_STORYBOARD_PROVIDER_COVERAGE_INVALID",
                f"本土化分镜 Provider 的 {label} 覆盖不完整",
                status_code=502,
                details={
                    "expected": len(expected),
                    "actual": len(actual),
                    "missing": missing,
                    "unexpected": unexpected,
                    "duplicates": duplicates,
                    "issues": [{
                        "field": label,
                        "missing_ids": missing,
                        "unexpected_ids": unexpected,
                        "duplicate_ids": duplicates,
                        "repair": "严格按本批输出 ID 清单逐项返回；补齐缺失 ID，删除多余或重复 ID，不得改变其他有效内容",
                    }],
                },
            )
    for item in semantic.characters:
        _assert_chinese("人物身份说明", item.identity_description_zh)
        _assert_chinese("人物外形说明", item.appearance_description_zh)
    for item in semantic.scenes:
        _assert_chinese("场景设定说明", item.setting_description_zh)
        _assert_chinese("场景视觉说明", item.visual_description_zh)
    for item in semantic.props:
        _assert_chinese("道具功能说明", item.function_description_zh)
        _assert_chinese("道具视觉说明", item.visual_description_zh)
    for item in semantic.dialogue:
        _assert_chinese("目标对白中文翻译", item.target_dialogue_zh, minimum_cjk=1)
    if payload.operation == "LOCALIZE_SHOTS":
        owner_windows = dialogue_owner_windows(payload.source_view["shots"])
        source_dialogue = {item["utterance_id"]: item for item in payload.source_view["dialogue"]}
        timing_issues = []
        for item in semantic.dialogue:
            owner = next((window for (_, utterance_id), window in owner_windows.items() if utterance_id == item.utterance_id), None)
            available_seconds = 0 if owner is None else (owner[2] - owner[1]) / 1_000_000
            required_seconds = estimate_spoken_seconds(item.target_dialogue)
            if not estimated_speech_fits(item.target_dialogue, available_seconds):
                source = source_dialogue[item.utterance_id]
                timing_issues.append({
                    "utterance_id": item.utterance_id,
                    "authoritative_owner_shot_id": owner[0] if owner else None,
                    "authoritative_available_seconds": round(available_seconds, 3),
                    "max_spoken_words": source.get("max_spoken_words"),
                    "max_spoken_cjk_chars": source.get("max_spoken_cjk_chars"),
                    "estimated_seconds": round(required_seconds, 3),
                    "target_dialogue": item.target_dialogue,
                    "repair": "仅重写并缩短 target_dialogue，英文不得超过 max_spoken_words，CJK 不得超过 max_spoken_cjk_chars；不得修改镜头时长",
                })
        if timing_issues:
            raise AppError("LOCALIZED_STORYBOARD_DIALOGUE_TIMING_INVALID", "目标对白无法在权威原片时间窗内说完，请缩短对白", status_code=502, details={"issues": timing_issues})
    for item in semantic.shots:
        _assert_chinese("本土化镜头描述", item.localized_visual_description_zh)
        _assert_chinese("镜头语言中文说明", item.camera_description_zh)
    frozen_names = payload.frozen_identity_names or {}
    identity_items = [
        *[(item.source_character_id, item.localized_name) for item in semantic.characters],
        *[(item.source_scene_id, item.localized_name) for item in semantic.scenes],
        *[(item.source_prop_id, item.localized_name) for item in semantic.props],
    ]
    drift = [
        {"source_id": source_id, "expected": frozen_names[source_id], "actual": localized_name}
        for source_id, localized_name in identity_items
        if source_id in frozen_names and localized_name != frozen_names[source_id]
    ]
    if drift:
        raise AppError(
            "LOCALIZED_STORYBOARD_IDENTITY_NAME_DRIFT",
            "本土化分镜跨批次人物、场景或道具名称不一致",
            status_code=502,
            details={"issues": drift},
        )
    return semantic


def _validate_content_dialogue_timing(content: ReplicaLocalizedStoryboardContent) -> None:
    owner_windows = dialogue_owner_windows(content.shots)
    issues = []
    for item in content.dialogue:
        owner = next((window for (_, utterance_id), window in owner_windows.items() if utterance_id == item.utterance_id), None)
        available_seconds = 0 if owner is None else (owner[2] - owner[1]) / 1_000_000
        required_seconds = estimate_spoken_seconds(item.target_dialogue)
        if not estimated_speech_fits(item.target_dialogue, available_seconds):
            issues.append({"utterance_id": item.utterance_id, "target_available_seconds": round(available_seconds, 3), "estimated_seconds": round(required_seconds, 3)})
    if issues:
        raise AppError("LOCALIZED_STORYBOARD_DIALOGUE_TIMING_INVALID", "目标对白无法在权威原片时间窗内说完，请缩短对白", status_code=422, details={"issues": issues})


def _visual_projection_fingerprint(content: ReplicaLocalizedStoryboardContent) -> str:
    return _sha({
        "characters": [item.model_dump(mode="json") for item in content.characters],
        "scenes": [item.model_dump(mode="json") for item in content.scenes],
        "props": [item.model_dump(mode="json") for item in content.props],
        "shots": [{
            "storyboard_shot_id": item.storyboard_shot_id,
            "localized_visual_description_zh": item.localized_visual_description_zh,
            "camera_description_zh": item.camera_description_zh,
            "camera_language": item.camera_language.model_dump(mode="json"),
            "target_character_ids": item.target_character_ids,
            "target_scene_ids": item.target_scene_ids,
            "target_prop_ids": item.target_prop_ids,
            "sound_effects": item.sound_effects,
            "ambience": item.ambience,
        } for item in content.shots],
    })


def _dialogue_projection_fingerprint(content: ReplicaLocalizedStoryboardContent) -> str:
    return _sha([{
        "utterance_id": item.utterance_id,
        "target_character_id": item.target_character_id,
        "target_dialogue": item.target_dialogue,
        "target_dialogue_zh": item.target_dialogue_zh,
        "source_start_us": item.source_start_us,
        "source_end_us": item.source_end_us,
    } for item in content.dialogue])


class _DoubaoProvider:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError("LOCALIZED_STORYBOARD_PROVIDER_NOT_CONFIGURED", "火山引擎本土化分镜 Provider 尚未配置", status_code=409)

    def profile(self) -> dict:
        return {"provider": self.provider_name, "model": self.model_name, "mode": "CLOUD_API_TEXT", "skill": SKILL_ID}

    def localize(self, payload: LocalizationProviderInput, *, correction_issues: list[dict] | None = None) -> LocalizationProviderResult:
        assert self.settings.p7_doubao_api_key is not None
        client = Ark(
            api_key=self.settings.p7_doubao_api_key.get_secret_value(),
            base_url=self.settings.p7_doubao_base_url,
            timeout=self.settings.p7_doubao_request_timeout_seconds,
            max_retries=2,
        )
        response = client.responses.create(
            model=self.model_name,
            input=[{"role": "user", "content": [{"type": "input_text", "text": _provider_prompt(payload, correction_issues)}]}],
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
        if not text:
            raise AppError("LOCALIZED_STORYBOARD_PROVIDER_EMPTY", "本土化分镜 Provider 未返回可用文本", status_code=502)
        semantic = LocalizedStoryboardSemantic.model_validate_json(_json_object(text))
        return LocalizationProviderResult(
            semantic=semantic,
            remote_job_id=str(getattr(response, "id", "") or "") or None,
        )


class _LocalQwenProvider:
    provider_name = "local-vllm"

    def __init__(self, settings: Settings, *, model_name: str, base_url: str, api_key: SecretStr | None):
        self.settings = settings
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def profile(self) -> dict:
        return {"provider": self.provider_name, "model": self.model_name, "base_url": self.base_url, "mode": "LOCAL_VLLM_TEXT", "skill": SKILL_ID}

    def localize(self, payload: LocalizationProviderInput, *, correction_issues: list[dict] | None = None) -> LocalizationProviderResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key is not None and self.api_key.get_secret_value().strip():
            headers["Authorization"] = f"Bearer {self.api_key.get_secret_value()}"
        with httpx.Client(timeout=httpx.Timeout(self.settings.p7_qwen_local_request_timeout_seconds)) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": self.model_name, "messages": [{"role": "user", "content": _provider_prompt(payload, correction_issues)}], "temperature": 0.2, "max_tokens": MAX_OUTPUT_TOKENS},
            )
            response.raise_for_status()
            body = response.json()
        choices = body.get("choices") or []
        text = ((choices[0].get("message") or {}).get("content") if choices else None)
        if not isinstance(text, str) or not text.strip():
            raise AppError("LOCALIZED_STORYBOARD_PROVIDER_EMPTY", "本土化分镜 Provider 未返回可用文本", status_code=502)
        semantic = LocalizedStoryboardSemantic.model_validate_json(_json_object(text))
        return LocalizationProviderResult(semantic=semantic, remote_job_id=str(body.get("id") or "") or None)


def _provider(settings: Settings, _selection: SourceUnderstandingProvider) -> LocalizationProvider:
    # Step 2 has its own provider policy. It must not inherit the Step 1 source-understanding
    # provider, otherwise a project configured for local Qwen can make localization wait on
    # a local vLLM runtime. The current product contract uses Volcengine Ark / Doubao directly.
    return _DoubaoProvider(settings)


def _current_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(select(ArtifactNode).where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == artifact_type.value, ArtifactNode.is_current.is_(True), ArtifactNode.validity == ArtifactValidity.CURRENT))


def _latest_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(select(ArtifactNode).where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == artifact_type.value).order_by(ArtifactNode.revision.desc()).limit(1))


def _load_snapshot(db: Session, project_id: str) -> tuple[ArtifactNode, SourceVideoSnapshotContent]:
    artifact = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    if artifact is None:
        raise AppError("LOCALIZED_STORYBOARD_SOURCE_NOT_READY", "请先完成第 1 步：分析视频并确认原片分镜表", status_code=409)
    row = db.scalar(select(SourceVideoSnapshotRevision).where(SourceVideoSnapshotRevision.artifact_id == artifact.id))
    if row is None:
        raise AppError("LOCALIZED_STORYBOARD_SOURCE_CONTENT_MISSING", "SOURCE_VIDEO_SNAPSHOT typed revision 缺失", status_code=500)
    return artifact, SourceVideoSnapshotContent.model_validate(row.content_json)


def _dialogue_provider_view(item, speaker_by_utterance: dict[str, str | None], owner_by_utterance: dict[str, tuple[str, int, int]]) -> dict:
    owner = owner_by_utterance.get(item.utterance_id)
    owner_shot_id, owner_start_us, owner_end_us = owner or (None, item.start_us, item.end_us)
    available_seconds = max(0, owner_end_us - owner_start_us) / 1_000_000
    budget_seconds = available_seconds + 0.15
    return {
        "utterance_id": item.utterance_id,
        "utterance_number": item.utterance_number,
        "text": item.text,
        "language": item.language,
        "speaker_character_id": speaker_by_utterance.get(item.utterance_id),
        "start_us": item.start_us,
        "end_us": item.end_us,
        "duration_us": item.end_us - item.start_us,
        "duration_seconds": round((item.end_us - item.start_us) / 1_000_000, 3),
        "authoritative_owner_shot_id": owner_shot_id,
        "authoritative_speech_start_us": owner_start_us,
        "authoritative_speech_end_us": owner_end_us,
        "authoritative_available_seconds": round(available_seconds, 3),
        "max_spoken_words": max(1, int(budget_seconds * 4)),
        "max_spoken_cjk_chars": max(1, int(budget_seconds * 6)),
    }


def _source_view(snapshot: SourceVideoSnapshotContent) -> tuple[dict, dict[str, str | None]]:
    char_candidate = {candidate: entity.character_id for entity in snapshot.source_characters.entities for candidate in entity.source_candidate_ids}
    prop_candidate = {candidate: entity.prop_id for entity in snapshot.source_props.entities for candidate in entity.source_candidate_ids}
    scene_by_shot = {item.shot_anchor_id: item.scene_id for item in snapshot.source_scenes.assignments if item.scene_id}
    speaker_entities = {item.speaker_id: item for item in snapshot.source_speakers.entities}
    speaker_by_utterance: dict[str, str | None] = {}
    for item in snapshot.source_speakers.attributions:
        speaker = speaker_entities.get(item.speaker_id or "")
        speaker_by_utterance[item.utterance_id] = speaker.character_id if speaker else None

    used_chars: set[str] = set(value for value in speaker_by_utterance.values() if value)
    used_scenes: set[str] = set()
    used_props: set[str] = set()
    shot_view: list[dict] = []
    for episode in sorted(snapshot.source_shot_facts.episodes, key=lambda item: item.episode_order):
        for shot in sorted(episode.shots, key=lambda item: item.shot_number):
            chars = list(dict.fromkeys(char_candidate[ref.id] for ref in shot.bindings.characters if ref.id in char_candidate))
            props = list(dict.fromkeys(prop_candidate[ref.id] for ref in shot.bindings.props if ref.id in prop_candidate))
            scene = scene_by_shot.get(shot.shot_anchor_id)
            used_chars.update(chars)
            used_props.update(props)
            if scene:
                used_scenes.add(scene)
            shot_view.append({
                "episode_id": episode.episode_id,
                "episode_order": episode.episode_order,
                "shot_anchor_id": shot.shot_anchor_id,
                "shot_number": shot.shot_number,
                "start_us": shot.start_us,
                "end_us": shot.end_us,
                "duration_us": shot.duration_us,
                "visual_description": shot.visual_description,
                "camera_language": shot.camera_language.model_dump(mode="json"),
                "character_ids": chars,
                "scene_ids": [scene] if scene else [],
                "prop_ids": props,
                "dialogue": [{"utterance_id": ref.utterance_id, "delivery": ref.delivery.value, "overlap_start_us": ref.overlap_start_us, "overlap_end_us": ref.overlap_end_us} for ref in shot.dialogue],
                "sound_effects": list(shot.sound_effects),
                "ambience": list(shot.ambience),
            })

    characters = [item for item in snapshot.source_characters.entities if item.character_id in used_chars]
    scenes = [item for item in snapshot.source_scenes.entities if item.scene_id in used_scenes]
    props = [item for item in snapshot.source_props.entities if item.prop_id in used_props]
    dialogue = [line for episode in sorted(snapshot.episodes, key=lambda item: item.episode_order) for line in episode.canonical_dialogue]
    owner_windows = dialogue_owner_windows(shot_view)
    owner_by_utterance = {
        utterance_id: (shot_id, start_us, end_us)
        for (_, utterance_id), (shot_id, start_us, end_us) in owner_windows.items()
    }
    return {
        "characters": [{"source_character_id": item.character_id, "name": item.display_name, "aliases": item.aliases, "notes": item.notes} for item in characters],
        "scenes": [{"source_scene_id": item.scene_id, "name": item.display_name, "aliases": item.aliases, "notes": item.notes} for item in scenes],
        "props": [{"source_prop_id": item.prop_id, "name": item.display_name, "aliases": item.aliases, "notes": item.notes} for item in props],
        "dialogue": [_dialogue_provider_view(item, speaker_by_utterance, owner_by_utterance) for item in dialogue],
        "shots": shot_view,
    }, speaker_by_utterance


def _payload(project, snapshot: SourceVideoSnapshotContent) -> LocalizationProviderInput:
    view, _ = _source_view(snapshot)
    return LocalizationProviderInput(
        target_language=project.target_language,
        target_region=project.target_region,
        scene_strategy=project.scene_strategy.value if hasattr(project.scene_strategy, "value") else str(project.scene_strategy),
        visual_style=project.visual_style or "写实电影感",
        source_view=view,
        expected_character_ids=tuple(item["source_character_id"] for item in view["characters"]),
        expected_scene_ids=tuple(item["source_scene_id"] for item in view["scenes"]),
        expected_prop_ids=tuple(item["source_prop_id"] for item in view["props"]),
        expected_dialogue_ids=tuple(item["utterance_id"] for item in view["dialogue"]),
        expected_shot_ids=tuple(item["shot_anchor_id"] for item in view["shots"]),
    )


def _batched_payloads(payload: LocalizationProviderInput) -> list[LocalizationProviderInput]:
    """Bound requests without crossing episodes or splitting one utterance across batches."""
    shots = sorted(payload.source_view["shots"], key=lambda item: (item["episode_order"], item["shot_number"]))
    if not shots:
        return [payload]
    dialogue_by_id = {item["utterance_id"]: item for item in payload.source_view["dialogue"]}
    character_by_id = {item["source_character_id"]: item for item in payload.source_view["characters"]}
    scene_by_id = {item["source_scene_id"]: item for item in payload.source_view["scenes"]}
    prop_by_id = {item["source_prop_id"]: item for item in payload.source_view["props"]}
    shot_groups: list[list[dict]] = []
    for _, episode_iter in groupby(shots, key=lambda item: item["episode_id"]):
        episode_shots = list(episode_iter)
        current: list[dict] = []
        current_dialogue: set[str] = set()
        for shot in episode_shots:
            shot_dialogue = {item["utterance_id"] for item in shot["dialogue"]}
            if current and len(current) >= LOCALIZATION_BATCH_SHOTS and not (current_dialogue & shot_dialogue):
                shot_groups.append(current)
                current = []
                current_dialogue = set()
            current.append(shot)
            current_dialogue.update(shot_dialogue)
        if current:
            shot_groups.append(current)

    batches: list[LocalizationProviderInput] = []
    for batch_shots in shot_groups:
        dialogue_ids = tuple(dict.fromkeys(ref["utterance_id"] for shot in batch_shots for ref in shot["dialogue"]))
        character_ids = tuple(dict.fromkeys(item for shot in batch_shots for item in shot["character_ids"]))
        scene_ids = tuple(dict.fromkeys(item for shot in batch_shots for item in shot["scene_ids"]))
        prop_ids = tuple(dict.fromkeys(item for shot in batch_shots for item in shot["prop_ids"]))
        for dialogue_id in dialogue_ids:
            speaker_id = dialogue_by_id[dialogue_id].get("speaker_character_id")
            if speaker_id and speaker_id not in character_ids:
                character_ids += (speaker_id,)
        batch_view = {
            "characters": [character_by_id[item] for item in character_ids],
            "scenes": [scene_by_id[item] for item in scene_ids],
            "props": [prop_by_id[item] for item in prop_ids],
            "dialogue": [dialogue_by_id[item] for item in dialogue_ids],
            "shots": batch_shots,
        }
        batches.append(LocalizationProviderInput(
            target_language=payload.target_language,
            target_region=payload.target_region,
            scene_strategy=payload.scene_strategy,
            visual_style=payload.visual_style,
            source_view=batch_view,
            expected_character_ids=character_ids,
            expected_scene_ids=scene_ids,
            expected_prop_ids=prop_ids,
            expected_dialogue_ids=dialogue_ids,
            expected_shot_ids=tuple(item["shot_anchor_id"] for item in batch_shots),
            frozen_identity_names=payload.frozen_identity_names,
            frozen_world_plan=payload.frozen_world_plan,
        ))
    return batches


def _merge_semantics(payload: LocalizationProviderInput, parts: list[LocalizedStoryboardSemantic]) -> LocalizedStoryboardSemantic:
    fields_and_ids = (("characters", "source_character_id"), ("scenes", "source_scene_id"), ("props", "source_prop_id"), ("dialogue", "utterance_id"), ("shots", "shot_anchor_id"))
    merged: dict[str, list[dict[str, Any]]] = {}
    for field, id_field in fields_and_ids:
        by_id: dict[str, dict[str, Any]] = {}
        for part in parts:
            for item in getattr(part, field):
                value = item.model_dump(mode="json")
                item_id = str(value[id_field])
                # Entity definitions can appear in more than one shot batch. Keep the
                # first validated definition so later wording drift cannot rename the
                # same stable id halfway through the storyboard.
                by_id.setdefault(item_id, value)
        merged[field] = list(by_id.values())
    return _validate_semantic(payload, LocalizedStoryboardSemantic.model_validate(merged))


def create_localized_storyboard_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project = get_project(db, project_id)
    if project.project_type != ProjectType.REPLICA:
        raise AppError("LOCALIZED_STORYBOARD_PROJECT_UNSUPPORTED", "当前五步主生产链只正式支持 REPLICA", status_code=422)
    snapshot_artifact, snapshot = _load_snapshot(db, project_id)
    provider = _provider(get_settings(), project.source_understanding_provider)
    payload = _payload(project, snapshot)
    latest_task = db.scalar(select(Task).where(
        Task.project_id == project_id,
        Task.task_type == TASK_TYPE,
    ).order_by(Task.created_at.desc()).limit(1))
    restart_after_terminal = None
    if latest_task is not None and latest_task.status in {
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
        TaskStatus.INTERRUPTED,
        TaskStatus.SUCCEEDED,
    }:
        restart_after_terminal = latest_task.id
    fingerprint = _sha({"snapshot": snapshot_artifact.input_fingerprint, "target_language": project.target_language, "target_region": project.target_region, "scene_strategy": str(project.scene_strategy), "visual_style": project.visual_style, "provider": provider.profile(), "skill": get_professional_skill(SKILL_ID).version, "restart_after_terminal": restart_after_terminal})
    return create_task_from_command(db, project_id=project_id, idempotency_key=idempotency_key, payload=TaskCommandCreate(task_type=TASK_TYPE, task_name="生成本土化分镜表", input_fingerprint=fingerprint, input_artifact_ids=[snapshot_artifact.id], max_attempts=3))


def _generation_sequence(db: Session, project_id: str, snapshot_artifact_id: str) -> int:
    latest = db.scalar(select(func.max(ReplicaLocalizedStoryboardCandidate.generation_sequence)).where(ReplicaLocalizedStoryboardCandidate.project_id == project_id, ReplicaLocalizedStoryboardCandidate.source_snapshot_artifact_id == snapshot_artifact_id))
    return int(latest or 0) + 1


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[ReplicaLocalizedStoryboardContent, LocalizedStoryboardProvenance]:
    with context.session_factory() as db:
        project = get_project(db, task.project_id)
        snapshot_artifact, snapshot = _load_snapshot(db, task.project_id)
        provider = _provider(get_settings(), project.source_understanding_provider)
        payload = _payload(project, snapshot)
        sequence = _generation_sequence(db, task.project_id, snapshot_artifact.id)
        profile = provider.profile()
        if task.input_artifact_ids_json != [snapshot_artifact.id]:
            raise AppError("LOCALIZED_STORYBOARD_INPUT_CHANGED", "原片版本已变化，请重新本土化", status_code=409)
        job_payload = {"source_snapshot_artifact_id": snapshot_artifact.id, "source_snapshot_fingerprint": snapshot_artifact.input_fingerprint, "target_language": project.target_language, "target_region": project.target_region, "scene_strategy": payload.scene_strategy, "visual_style": payload.visual_style, "provider_profile": profile, "professional_skill_version": get_professional_skill(SKILL_ID).version}
        planning_fingerprint = _sha(job_payload)
        checkpoint = dict(task.checkpoint_json or {})
        if checkpoint.get("localized_semantic_parts") and not checkpoint.get("localized_world_plan"):
            raise AppError("LOCALIZED_STORYBOARD_REPLAN_REQUIRED", "旧任务未规划完整目标世界，请重新本土化", status_code=409)
        if checkpoint.get("planning_fingerprint") not in (None, planning_fingerprint):
            raise AppError("LOCALIZED_STORYBOARD_INPUT_CHANGED", "本土化配置或合同已变化，请重新本土化", status_code=409)
        sequence = int(checkpoint.get("generation_sequence") or sequence)
        job_payload["generation_sequence"] = sequence
        job_ids = list(checkpoint.get("provider_job_ids") or [])
        jobs: list[ProviderJob] = [db.get(ProviderJob, job_id) for job_id in job_ids]
        if any(job is None or job.task_id != task.id for job in jobs):
            raise AppError("LOCALIZED_STORYBOARD_CHECKPOINT_INVALID", "本土化恢复记录缺少模型调用来源", status_code=409)
        planning_payload = replace(payload, operation="PLAN_WORLD", expected_dialogue_ids=(), expected_shot_ids=())
        checkpoint.update({"planning_fingerprint": planning_fingerprint, "provider": provider.provider_name, "model": provider.model_name, "generation_sequence": sequence, "phase": "PLAN_WORLD"})
        context.checkpoint(checkpoint, progress_percent=max(5, task.progress_percent))
        if checkpoint.get("localized_world_plan"):
            world_plan = _validate_semantic(planning_payload, LocalizedStoryboardSemantic.model_validate(checkpoint["localized_world_plan"]))
        else:
            def _plan_world(_):
                result = provider.localize(planning_payload)
                return ProviderDispatchResult(value=result, remote_job_id=result.remote_job_id)

            job, dispatched = dispatch_provider_call(db, task_id=task.id, provider=provider.provider_name, model=provider.model_name, capability=Capability.STORYBOARD_LOCALIZATION, payload={**job_payload, "operation": "PLAN_WORLD", "planning_fingerprint": planning_fingerprint}, artifact_id=snapshot_artifact.id, remote_call=_plan_world)
            jobs.append(job)
            world_plan = _validate_semantic(planning_payload, dispatched.value.semantic)
            checkpoint.update({"localized_world_plan": world_plan.model_dump(mode="json"), "provider_job_ids": [item.id for item in jobs]})
            context.checkpoint(checkpoint, progress_percent=10)
        payload = replace(payload, frozen_world_plan=world_plan)
        batches = _batched_payloads(payload)
        semantic_parts = [LocalizedStoryboardSemantic.model_validate(item) for item in checkpoint.get("localized_semantic_parts", [])]
        if len(semantic_parts) > len(batches):
            raise AppError("LOCALIZED_STORYBOARD_CHECKPOINT_INVALID", "本土化恢复批次数量不匹配", status_code=409)
        for index, saved in enumerate(semantic_parts):
            _validate_semantic(batches[index], saved)
        frozen_identity_names: dict[str, str] = {}
        for saved in [world_plan]:
            for item in saved.characters:
                frozen_identity_names.setdefault(item.source_character_id, item.localized_name)
            for item in saved.scenes:
                frozen_identity_names.setdefault(item.source_scene_id, item.localized_name)
            for item in saved.props:
                frozen_identity_names.setdefault(item.source_prop_id, item.localized_name)
        for batch_index, batch in enumerate(batches, 1):
            if batch_index <= len(semantic_parts):
                continue
            batch = replace(batch, frozen_identity_names=dict(frozen_identity_names))
            correction_issues: list[dict] | None = None
            validated_semantic = None
            for correction_attempt in range(1, 4):
                def _remote_call(_, current_batch=batch, current_issues=correction_issues):
                    provider_result = provider.localize(current_batch, correction_issues=current_issues)
                    return ProviderDispatchResult(value=provider_result, remote_job_id=provider_result.remote_job_id)

                batch_payload = dict(job_payload)
                batch_payload.update({"operation": "LOCALIZE_SHOTS", "world_plan_fingerprint": _sha(world_plan.model_dump(mode="json")), "batch_index": batch_index, "batch_count": len(batches), "shot_ids": list(batch.expected_shot_ids), "correction_attempt": correction_attempt, "correction_issues": correction_issues or []})
                job, dispatched = dispatch_provider_call(db, task_id=task.id, provider=provider.provider_name, model=provider.model_name, capability=Capability.STORYBOARD_LOCALIZATION, payload=batch_payload, artifact_id=snapshot_artifact.id, remote_call=_remote_call)
                jobs.append(job)
                try:
                    validated_semantic = _validate_semantic(batch, dispatched.value.semantic)
                    break
                except AppError as exc:
                    if exc.code not in {
                        "LOCALIZED_STORYBOARD_PROVIDER_COVERAGE_INVALID",
                        "LOCALIZED_STORYBOARD_DIALOGUE_TIMING_INVALID",
                        "LOCALIZED_STORYBOARD_IDENTITY_NAME_DRIFT",
                        "LOCALIZED_STORYBOARD_WORLD_PLAN_DRIFT",
                    } or correction_attempt >= 3:
                        raise
                    correction_issues = list((exc.details or {}).get("issues") or [])
            assert validated_semantic is not None
            semantic_parts.append(validated_semantic)
            for item in validated_semantic.characters:
                frozen_identity_names.setdefault(item.source_character_id, item.localized_name)
            for item in validated_semantic.scenes:
                frozen_identity_names.setdefault(item.source_scene_id, item.localized_name)
            for item in validated_semantic.props:
                frozen_identity_names.setdefault(item.source_prop_id, item.localized_name)
            progress = 10 + int(60 * batch_index / len(batches))
            checkpoint.update({"phase": "LOCALIZE_SHOTS", "provider_job_ids": [item.id for item in jobs], "generation_sequence": sequence, "completed_batches": batch_index, "batch_count": len(batches), "localized_semantic_parts": [item.model_dump(mode="json") for item in semantic_parts]})
            context.checkpoint(checkpoint, progress_percent=progress)

        db.refresh(project)
        db.refresh(snapshot_artifact)
        current_project = get_project(db, task.project_id)
        current_snapshot, _ = _load_snapshot(db, task.project_id)
        current_payload = _payload(current_project, snapshot)
        if current_snapshot.id != snapshot_artifact.id or (current_payload.target_language, current_payload.target_region, current_payload.scene_strategy, current_payload.visual_style) != (payload.target_language, payload.target_region, payload.scene_strategy, payload.visual_style):
            raise AppError("LOCALIZED_STORYBOARD_INPUT_CHANGED", "生成期间原片或目标设定已变化，请重新本土化", status_code=409)

    semantic = _merge_semantics(payload, semantic_parts)
    char_sem = {item.source_character_id: item for item in semantic.characters}
    scene_sem = {item.source_scene_id: item for item in semantic.scenes}
    prop_sem = {item.source_prop_id: item for item in semantic.props}
    dialogue_sem = {item.utterance_id: item for item in semantic.dialogue}
    shot_sem = {item.shot_anchor_id: item for item in semantic.shots}
    source_view, speaker_by_utterance = _source_view(snapshot)
    target_char = {item["source_character_id"]: _stable_target_id(task.project_id, "character", item["source_character_id"], project.target_region) for item in source_view["characters"]}
    target_scene = {item["source_scene_id"]: _stable_target_id(task.project_id, "scene", item["source_scene_id"], project.target_region) for item in source_view["scenes"]}
    target_prop = {item["source_prop_id"]: _stable_target_id(task.project_id, "prop", item["source_prop_id"], project.target_region) for item in source_view["props"]}
    source_chars = {item["source_character_id"]: item for item in source_view["characters"]}
    source_scenes = {item["source_scene_id"]: item for item in source_view["scenes"]}
    source_props = {item["source_prop_id"]: item for item in source_view["props"]}

    characters = [LocalizedTargetCharacter(source_character_id=sid, target_character_id=target_char[sid], source_name=source_chars[sid]["name"], display_name=char_sem[sid].localized_name, identity_description_zh=char_sem[sid].identity_description_zh, appearance_description_zh=char_sem[sid].appearance_description_zh) for sid in payload.expected_character_ids]
    scenes = [LocalizedTargetScene(source_scene_id=sid, target_scene_id=target_scene[sid], source_name=source_scenes[sid]["name"], display_name=scene_sem[sid].localized_name, setting_description_zh=scene_sem[sid].setting_description_zh, visual_description_zh=scene_sem[sid].visual_description_zh) for sid in payload.expected_scene_ids]
    props = [LocalizedTargetProp(source_prop_id=sid, target_prop_id=target_prop[sid], source_name=source_props[sid]["name"], display_name=prop_sem[sid].localized_name, function_description_zh=prop_sem[sid].function_description_zh, visual_description_zh=prop_sem[sid].visual_description_zh) for sid in payload.expected_prop_ids]

    dialogue_lines: list[LocalizedStoryboardDialogue] = []
    dialogue_by_id: dict[str, LocalizedStoryboardDialogue] = {}
    for item in source_view["dialogue"]:
        localized = dialogue_sem[item["utterance_id"]]
        source_character_id = speaker_by_utterance.get(item["utterance_id"])
        line = LocalizedStoryboardDialogue(utterance_id=item["utterance_id"], utterance_number=item["utterance_number"], source_start_us=next(x.start_us for ep in snapshot.episodes for x in ep.canonical_dialogue if x.utterance_id == item["utterance_id"]), source_end_us=next(x.end_us for ep in snapshot.episodes for x in ep.canonical_dialogue if x.utterance_id == item["utterance_id"]), source_text=item["text"], source_language=item["language"], target_character_id=target_char.get(source_character_id or ""), target_dialogue=localized.target_dialogue, target_dialogue_zh=localized.target_dialogue_zh)
        dialogue_lines.append(line)
        dialogue_by_id[line.utterance_id] = line

    source_shots = {shot.shot_anchor_id: (episode, shot) for episode in snapshot.source_shot_facts.episodes for shot in episode.shots}
    episode_media = {episode.episode_id: episode for episode in snapshot.episodes}
    view_shots = {item["shot_anchor_id"]: item for item in source_view["shots"]}
    shots: list[LocalizedStoryboardShot] = []
    for shot_id in payload.expected_shot_ids:
        episode, shot = source_shots[shot_id]
        view = view_shots[shot_id]
        localized = shot_sem[shot_id]
        target_start_us = shot.start_us
        target_end_us = shot.end_us
        target_duration_us = shot.duration_us
        refs: list[LocalizedShotDialogueRef] = []
        for source_ref in shot.dialogue:
            line = dialogue_by_id[source_ref.utterance_id]
            overlap_start = max(target_start_us, source_ref.overlap_start_us)
            overlap_end = min(target_end_us, source_ref.overlap_end_us)
            refs.append(LocalizedShotDialogueRef(utterance_id=line.utterance_id, utterance_number=line.utterance_number, delivery=source_ref.delivery, target_character_id=line.target_character_id, target_dialogue=line.target_dialogue, target_dialogue_zh=line.target_dialogue_zh, overlap_start_us=overlap_start, overlap_end_us=overlap_end, source_overlap_start_us=source_ref.overlap_start_us, source_overlap_end_us=source_ref.overlap_end_us))
        media = episode_media.get(episode.episode_id)
        if media is None:
            raise AppError("LOCALIZED_STORYBOARD_EPISODE_MEDIA_MISSING", "Source Snapshot 缺少 Episode 媒体尺寸", status_code=500)
        shots.append(LocalizedStoryboardShot(storyboard_shot_id=f"localized:{episode.episode_id}:{shot.shot_anchor_id}", episode_id=episode.episode_id, episode_order=episode.episode_order, source_shot_anchor_id=shot.shot_anchor_id, shot_number=shot.shot_number, start_us=target_start_us, end_us=target_end_us, duration_us=target_duration_us, source_start_us=shot.start_us, source_end_us=shot.end_us, source_duration_us=shot.duration_us, output_ratio=_nearest_h3_ratio(media.width, media.height), camera_language=shot.camera_language, source_visual_description=shot.visual_description, localized_visual_description_zh=localized.localized_visual_description_zh, camera_description_zh=localized.camera_description_zh, target_character_ids=[target_char[x] for x in view["character_ids"] if x in target_char], target_scene_ids=[target_scene[x] for x in view["scene_ids"] if x in target_scene], target_prop_ids=[target_prop[x] for x in view["prop_ids"] if x in target_prop], dialogue=refs, sound_effects=shot.sound_effects, ambience=shot.ambience))

    content = ReplicaLocalizedStoryboardContent(source_snapshot_artifact_id=snapshot_artifact.id, target_language=project.target_language, target_region=project.target_region, world_design_zh=world_plan.world_design_zh, continuity_rules_zh=world_plan.continuity_rules_zh, characters=characters, scenes=scenes, props=props, dialogue=dialogue_lines, shots=shots)
    skill = get_professional_skill(SKILL_ID)
    provider_jobs = [PipelineProviderJobProvenance(provider_job_id=item.id, provider=item.provider, model=item.model, payload_fingerprint=item.payload_fingerprint) for item in jobs]
    provenance = LocalizedStoryboardProvenance(source_snapshot_artifact_id=snapshot_artifact.id, source_snapshot_revision=snapshot_artifact.revision, source_snapshot_fingerprint=snapshot_artifact.input_fingerprint, target_language=project.target_language, target_region=project.target_region, generation_sequence=sequence, professional_skill_version=skill.version, provider_job=provider_jobs[0], provider_jobs=provider_jobs, generated_by_task_id=task.id)
    context.checkpoint({**checkpoint, "phase": "ASSEMBLE", "provider_job_ids": [item.provider_job_id for item in provider_jobs], "generation_sequence": sequence, "shot_count": len(shots)}, progress_percent=95)
    return content, provenance


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != TASK_TYPE or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
        return None
    now = utc_now()
    result = db.execute(update(Task).where(Task.id == task_id, Task.task_type == TASK_TYPE, Task.status == TaskStatus.QUEUED, Task.attempt < task.max_attempts).values(status=TaskStatus.RUNNING, attempt=task.attempt + 1, worker_id=worker_id, heartbeat_at=now, started_at=func.coalesce(Task.started_at, now), finished_at=None, updated_at=now))
    if result.rowcount != 1:
        db.rollback(); return None
    db.commit(); return db.get(Task, task_id)


def run_localized_storyboard_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"localized-storyboard-{uuid4()}"
    with session_factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None: return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=snapshot.id, worker_id=worker_id)
    try:
        content, provenance = _execute(context, snapshot)
    except TaskCancelled:
        return
    except AppError as exc:
        with session_factory() as db:
            mark_task_failed(db, snapshot.id, safe_error=f"本土化分镜失败（{exc.code}）：{exc.message}", worker_id=worker_id)
        return
    except Exception as exc:
        with session_factory() as db:
            mark_task_failed(db, snapshot.id, safe_error=f"本土化分镜失败（{type(exc).__name__}）", worker_id=worker_id)
        return
    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
        if finished.status == TaskStatus.CANCELLED: return
        existing = db.scalar(select(ReplicaLocalizedStoryboardCandidate).where(ReplicaLocalizedStoryboardCandidate.generated_by_task_id == snapshot.id))
        if existing is None:
            db.add(ReplicaLocalizedStoryboardCandidate(project_id=snapshot.project_id, source_snapshot_artifact_id=content.source_snapshot_artifact_id, generated_by_task_id=snapshot.id, generation_sequence=provenance.generation_sequence, input_fingerprint=snapshot.input_fingerprint, schema_version=LOCALIZED_STORYBOARD_SCHEMA_VERSION, content_json=content.model_dump(mode="json"), provenance_json=provenance.model_dump(mode="json"), review_status=CandidateStatus.NEEDS_REVIEW.value))
            db.commit()


def _candidate_read(row: ReplicaLocalizedStoryboardCandidate) -> LocalizedStoryboardCandidateRead:
    return LocalizedStoryboardCandidateRead(id=row.id, project_id=row.project_id, generation_sequence=row.generation_sequence, input_fingerprint=row.input_fingerprint, review_status=CandidateStatus(row.review_status), review_reason=row.review_reason, reviewed_at=row.reviewed_at, created_at=row.created_at, content=ReplicaLocalizedStoryboardContent.model_validate(row.content_json), provenance=LocalizedStoryboardProvenance.model_validate(row.provenance_json))


def list_localized_storyboard_candidates(db: Session, project_id: str) -> list[LocalizedStoryboardCandidateRead]:
    get_project(db, project_id)
    return [_candidate_read(row) for row in db.scalars(select(ReplicaLocalizedStoryboardCandidate).where(ReplicaLocalizedStoryboardCandidate.project_id == project_id).order_by(ReplicaLocalizedStoryboardCandidate.created_at.desc())).all()]


def get_localized_storyboard(db: Session, project_id: str) -> LocalizedStoryboardRead:
    get_project(db, project_id)
    current = _current_artifact(db, project_id, ArtifactType.TARGET_STORYBOARD)
    latest = current or _latest_artifact(db, project_id, ArtifactType.TARGET_STORYBOARD)
    if latest is None: return LocalizedStoryboardRead(project_id=project_id, status=ResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaLocalizedStoryboardRevision).where(ReplicaLocalizedStoryboardRevision.artifact_id == latest.id))
    if row is None:
        # A historical P15 storyboard is not a v2 localized storyboard.
        return LocalizedStoryboardRead(project_id=project_id, status=ResultStatus.NOT_BUILT)
    return LocalizedStoryboardRead(project_id=project_id, status=ResultStatus.CURRENT if current is not None else ResultStatus.STALE, artifact_id=latest.id, revision=latest.revision, input_fingerprint=latest.input_fingerprint, content=ReplicaLocalizedStoryboardContent.model_validate(row.content_json), provenance=row.provenance_json)


def update_localized_storyboard_shot(
    db: Session,
    *,
    project_id: str,
    command: LocalizedStoryboardShotEditCommand,
) -> LocalizedStoryboardCandidateRead:
    get_project(db, project_id)
    source = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    if source is None or source.id != command.expected_source_snapshot_artifact_id:
        raise AppError("LOCALIZED_STORYBOARD_EDIT_STALE", "正式原片分镜已经更新，请重新本土化", status_code=409)

    candidate: ReplicaLocalizedStoryboardCandidate | None = None
    if command.candidate_id:
        candidate = db.get(ReplicaLocalizedStoryboardCandidate, command.candidate_id)
        if candidate is None or candidate.project_id != project_id:
            raise AppError("LOCALIZED_STORYBOARD_CANDIDATE_NOT_FOUND", "本土化分镜候选不存在", status_code=404)
        if candidate.review_status != CandidateStatus.NEEDS_REVIEW.value:
            raise AppError("LOCALIZED_STORYBOARD_CANDIDATE_NOT_EDITABLE", "候选当前不可修改", status_code=409)
        if candidate.source_snapshot_artifact_id != source.id:
            raise AppError("LOCALIZED_STORYBOARD_EDIT_STALE", "候选依赖的原片分镜已经变化", status_code=409)
        if not command.expected_candidate_fingerprint or command.expected_candidate_fingerprint != candidate.input_fingerprint:
            raise AppError("LOCALIZED_STORYBOARD_EDIT_CONFLICT", "这份待确认分镜已在其他窗口更新，请刷新后再编辑", status_code=409)
        content = ReplicaLocalizedStoryboardContent.model_validate(candidate.content_json)
    else:
        current = _current_artifact(db, project_id, ArtifactType.TARGET_STORYBOARD)
        if current is None or current.id != command.expected_current_artifact_id:
            raise AppError("LOCALIZED_STORYBOARD_EDIT_STALE", "当前本土化分镜已经变化，请刷新后重试", status_code=409)
        revision = db.scalar(select(ReplicaLocalizedStoryboardRevision).where(ReplicaLocalizedStoryboardRevision.artifact_id == current.id))
        if revision is None:
            raise AppError("LOCALIZED_STORYBOARD_NOT_EDITABLE", "当前结果不是可编辑的本土化分镜", status_code=409)
        content = ReplicaLocalizedStoryboardContent.model_validate(revision.content_json)
        latest_sequence = db.scalar(select(func.max(ReplicaLocalizedStoryboardCandidate.generation_sequence)).where(ReplicaLocalizedStoryboardCandidate.project_id == project_id)) or 0
        provenance = dict(revision.provenance_json)
        provenance.update({"generation_sequence": latest_sequence + 1, "edited_from_artifact_id": current.id, "edited_by": "USER_EXPLICIT_ACTION"})
        candidate = ReplicaLocalizedStoryboardCandidate(
            project_id=project_id,
            source_snapshot_artifact_id=source.id,
            generated_by_task_id=None,
            generation_sequence=latest_sequence + 1,
            input_fingerprint=_sha({"source": source.id, "base": current.id, "sequence": latest_sequence + 1}),
            schema_version=LOCALIZED_STORYBOARD_SCHEMA_VERSION,
            content_json=content.model_dump(mode="json"),
            provenance_json=provenance,
            review_status=CandidateStatus.NEEDS_REVIEW.value,
        )
        db.add(candidate)
        db.flush()

    shot = next((item for item in content.shots if item.storyboard_shot_id == command.storyboard_shot_id), None)
    if shot is None:
        raise AppError("LOCALIZED_STORYBOARD_SHOT_NOT_FOUND", "要修改的本土化镜头不存在", status_code=404)
    expected_utterance_ids = [item.utterance_id for item in shot.dialogue]
    edited_utterance_ids = [item.utterance_id for item in command.dialogue]
    if len(edited_utterance_ids) != len(set(edited_utterance_ids)) or set(edited_utterance_ids) != set(expected_utterance_ids):
        raise AppError("LOCALIZED_STORYBOARD_DIALOGUE_SET_INVALID", "只能修改本镜头已有对白，不能增删或替换原片对白", status_code=422)

    shot.localized_visual_description_zh = command.localized_visual_description_zh
    shot.camera_description_zh = command.camera_description_zh
    edits = {item.utterance_id: item for item in command.dialogue}
    for item in content.dialogue:
        edit = edits.get(item.utterance_id)
        if edit is not None:
            item.target_dialogue = edit.target_dialogue
            item.target_dialogue_zh = edit.target_dialogue_zh
    for storyboard_shot in content.shots:
        for dialogue in storyboard_shot.dialogue:
            edit = edits.get(dialogue.utterance_id)
            if edit is not None:
                dialogue.target_dialogue = edit.target_dialogue
                dialogue.target_dialogue_zh = edit.target_dialogue_zh

    validated = ReplicaLocalizedStoryboardContent.model_validate(content.model_dump(mode="json"))
    for updated_shot in validated.shots:
        _assert_chinese("本土化镜头描述", updated_shot.localized_visual_description_zh)
        _assert_chinese("镜头语言中文说明", updated_shot.camera_description_zh)
    for updated_dialogue in validated.dialogue:
        _assert_chinese("目标对白中文翻译", updated_dialogue.target_dialogue_zh, minimum_cjk=1)
    _validate_content_dialogue_timing(validated)
    candidate.content_json = validated.model_dump(mode="json")
    provenance = dict(candidate.provenance_json)
    provenance["last_edited_at"] = utc_now().isoformat()
    provenance["last_edited_storyboard_shot_id"] = shot.storyboard_shot_id
    candidate.provenance_json = provenance
    candidate.input_fingerprint = _sha({"source": source.id, "content": candidate.content_json})
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return _candidate_read(candidate)


def _rebase_current_assets_for_visual_equivalent_storyboard(
    db: Session,
    *,
    project_id: str,
    previous_storyboard_id: str,
    storyboard: ArtifactNode,
) -> ArtifactNode | None:
    current_assets = _current_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    if current_assets is None:
        return None
    row = db.scalar(select(ReplicaAssetImageRevision).where(ReplicaAssetImageRevision.artifact_id == current_assets.id))
    if row is None or row.target_storyboard_artifact_id != previous_storyboard_id:
        return None
    content = ReplicaAssetImagesContent.model_validate(row.content_json).model_copy(
        update={"target_storyboard_artifact_id": storyboard.id}
    )
    latest = _latest_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    _mark_stale_with_downstream(db, [current_assets])
    artifact = ArtifactNode(
        project_id=project_id,
        artifact_type=ArtifactType.TARGET_ASSETS.value,
        namespace=ArtifactNamespace.TARGET,
        label="目标资产图",
        revision=(latest.revision if latest else 0) + 1,
        input_fingerprint=_sha({"visual_rebase_from": current_assets.id, "storyboard": storyboard.id, "content": content.model_dump(mode="json")}),
        skill_id=current_assets.skill_id,
        skill_version=current_assets.skill_version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={**dict(current_assets.metadata_json or {}), "target_storyboard_artifact_id": storyboard.id, "reused_media_from_artifact_id": current_assets.id},
    )
    db.add(artifact)
    db.flush()
    provenance = dict(row.provenance_json or {})
    provenance.update({
        "target_storyboard_artifact_id": storyboard.id,
        "reused_media_from_artifact_id": current_assets.id,
        "reuse_reason": "VISUAL_PROJECTION_UNCHANGED",
        "provider_job_ids": [],
    })
    db.add(ReplicaAssetImageRevision(
        project_id=project_id,
        artifact_id=artifact.id,
        target_storyboard_artifact_id=storyboard.id,
        candidate_id=row.candidate_id,
        generated_by_task_id=None,
        schema_version=row.schema_version,
        content_json=content.model_dump(mode="json"),
        provenance_json=provenance,
    ))
    db.add(ArtifactEdge(project_id=project_id, source_node_id=storyboard.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
    db.add(ArtifactEdge(project_id=project_id, source_node_id=artifact.id, target_node_id=current_assets.id, relation_type=ArtifactRelationType.SUPERSEDES))
    return artifact


def accept_localized_storyboard_candidate(db: Session, *, project_id: str, candidate_id: str, command: PipelineReviewCommand) -> LocalizedStoryboardRead:
    project = get_project(db, project_id)
    candidate = db.get(ReplicaLocalizedStoryboardCandidate, candidate_id)
    if candidate is None or candidate.project_id != project_id: raise AppError("LOCALIZED_STORYBOARD_CANDIDATE_NOT_FOUND", "本土化分镜候选不存在", status_code=404)
    if candidate.review_status != CandidateStatus.NEEDS_REVIEW.value: raise AppError("LOCALIZED_STORYBOARD_CANDIDATE_NOT_REVIEWABLE", "候选当前不可审核", status_code=409)
    if candidate.source_snapshot_artifact_id != command.expected_upstream_artifact_id or candidate.generation_sequence != command.expected_generation_sequence: raise AppError("LOCALIZED_STORYBOARD_REVIEW_STALE", "本土化分镜审核输入已变化", status_code=409)
    source = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    if source is None or source.id != candidate.source_snapshot_artifact_id: raise AppError("LOCALIZED_STORYBOARD_REVIEW_STALE", "正式原片分镜已经更新，请重新本土化", status_code=409)
    content = ReplicaLocalizedStoryboardContent.model_validate(candidate.content_json)
    _validate_content_dialogue_timing(content)
    previous = _current_artifact(db, project_id, ArtifactType.TARGET_STORYBOARD)
    latest = _latest_artifact(db, project_id, ArtifactType.TARGET_STORYBOARD)
    previous_content = None
    if previous:
        previous_row = db.scalar(select(ReplicaLocalizedStoryboardRevision).where(ReplicaLocalizedStoryboardRevision.artifact_id == previous.id))
        if previous_row is not None:
            previous_content = ReplicaLocalizedStoryboardContent.model_validate(previous_row.content_json)
        previous.validity = ArtifactValidity.STALE
        previous.is_current = False
        db.add(previous)
    skill = get_professional_skill(SKILL_ID)
    visual_fingerprint = _visual_projection_fingerprint(content)
    dialogue_fingerprint = _dialogue_projection_fingerprint(content)
    artifact = ArtifactNode(project_id=project_id, artifact_type=ArtifactType.TARGET_STORYBOARD.value, namespace=ArtifactNamespace.PRODUCTION, label="本土化分镜表", revision=(latest.revision if latest else 0) + 1, input_fingerprint=_sha({"candidate": candidate.input_fingerprint, "content": content.model_dump(mode="json")}), skill_id=skill.id, skill_version=skill.version, validity=ArtifactValidity.CURRENT, is_current=True, metadata_json={"schema_version": LOCALIZED_STORYBOARD_SCHEMA_VERSION, "source_snapshot_artifact_id": source.id, "shot_count": len(content.shots), "dialogue_count": len(content.dialogue), "visual_projection_fingerprint": visual_fingerprint, "dialogue_projection_fingerprint": dialogue_fingerprint})
    reviewed_at = utc_now()
    provenance = dict(candidate.provenance_json)
    provenance.update({"candidate_id": candidate.id, "reviewed_by": "USER_EXPLICIT_ACTION", "reviewed_at": reviewed_at.isoformat(), "review_reason": command.reason, "supersedes_artifact_id": latest.id if latest else None})
    db.add(artifact); db.flush()
    db.add(ReplicaLocalizedStoryboardRevision(project_id=project_id, artifact_id=artifact.id, source_snapshot_artifact_id=source.id, candidate_id=candidate.id, generated_by_task_id=candidate.generated_by_task_id, schema_version=LOCALIZED_STORYBOARD_SCHEMA_VERSION, content_json=content.model_dump(mode="json"), provenance_json=provenance))
    db.add(ArtifactEdge(project_id=project_id, source_node_id=source.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
    if latest: db.add(ArtifactEdge(project_id=project_id, source_node_id=artifact.id, target_node_id=latest.id, relation_type=ArtifactRelationType.SUPERSEDES))
    visual_unchanged = previous is not None and previous_content is not None and _visual_projection_fingerprint(previous_content) == visual_fingerprint
    if visual_unchanged:
        _rebase_current_assets_for_visual_equivalent_storyboard(db, project_id=project_id, previous_storyboard_id=previous.id, storyboard=artifact)
        downstream = [db.get(ArtifactNode, edge.target_node_id) for edge in db.scalars(select(ArtifactEdge).where(ArtifactEdge.project_id == project_id, ArtifactEdge.source_node_id == previous.id)).all()]
        _mark_stale_with_downstream(db, [item for item in downstream if item is not None and item.artifact_type != ArtifactType.TARGET_ASSETS.value])
    elif previous is not None:
        downstream = [db.get(ArtifactNode, edge.target_node_id) for edge in db.scalars(select(ArtifactEdge).where(ArtifactEdge.project_id == project_id, ArtifactEdge.source_node_id == previous.id)).all()]
        _mark_stale_with_downstream(db, [item for item in downstream if item is not None])
    for other in db.scalars(select(ReplicaLocalizedStoryboardCandidate).where(ReplicaLocalizedStoryboardCandidate.project_id == project_id, ReplicaLocalizedStoryboardCandidate.review_status == CandidateStatus.NEEDS_REVIEW.value, ReplicaLocalizedStoryboardCandidate.id != candidate.id)).all():
        other.review_status = CandidateStatus.SUPERSEDED.value; other.review_reason = "A newer localized storyboard was accepted."; other.reviewed_at = reviewed_at; db.add(other)
    candidate.review_status = CandidateStatus.ACCEPTED.value; candidate.review_reason = command.reason; candidate.reviewed_at = reviewed_at; db.add(candidate)
    _invalidate_project_plan(db, project); db.commit(); db.refresh(artifact)
    return LocalizedStoryboardRead(project_id=project_id, status=ResultStatus.CURRENT, artifact_id=artifact.id, revision=artifact.revision, input_fingerprint=artifact.input_fingerprint, content=content, provenance=provenance)


def reject_localized_storyboard_candidate(db: Session, *, project_id: str, candidate_id: str, command: PipelineReviewCommand) -> LocalizedStoryboardCandidateRead:
    get_project(db, project_id)
    candidate = db.get(ReplicaLocalizedStoryboardCandidate, candidate_id)
    if candidate is None or candidate.project_id != project_id: raise AppError("LOCALIZED_STORYBOARD_CANDIDATE_NOT_FOUND", "本土化分镜候选不存在", status_code=404)
    if candidate.review_status != CandidateStatus.NEEDS_REVIEW.value: raise AppError("LOCALIZED_STORYBOARD_CANDIDATE_NOT_REVIEWABLE", "候选当前不可审核", status_code=409)
    if candidate.source_snapshot_artifact_id != command.expected_upstream_artifact_id or candidate.generation_sequence != command.expected_generation_sequence: raise AppError("LOCALIZED_STORYBOARD_REVIEW_STALE", "本土化分镜审核输入已变化", status_code=409)
    candidate.review_status = CandidateStatus.REJECTED.value; candidate.review_reason = command.reason; candidate.reviewed_at = utc_now(); db.add(candidate); db.commit(); db.refresh(candidate)
    return _candidate_read(candidate)
