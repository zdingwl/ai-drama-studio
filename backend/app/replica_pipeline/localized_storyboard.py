import hashlib
import json
import re
from dataclasses import dataclass
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
from app.replica_pipeline.models import ReplicaLocalizedStoryboardCandidate, ReplicaLocalizedStoryboardRevision
from app.replica_pipeline.schemas import (
    CandidateStatus,
    LOCALIZED_STORYBOARD_SCHEMA_VERSION,
    LocalizedShotDialogueRef,
    LocalizedStoryboardCandidateRead,
    LocalizedStoryboardDialogue,
    LocalizedStoryboardProvenance,
    LocalizedStoryboardRead,
    LocalizedStoryboardSemantic,
    LocalizedStoryboardShot,
    LocalizedTargetCharacter,
    LocalizedTargetProp,
    LocalizedTargetScene,
    PipelineProviderJobProvenance,
    PipelineReviewCommand,
    ReplicaLocalizedStoryboardContent,
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


def _assert_chinese(label: str, value: str) -> None:
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", value))
    if cjk < 4:
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


@dataclass(frozen=True)
class LocalizationProviderResult:
    semantic: LocalizedStoryboardSemantic
    remote_job_id: str | None = None


class LocalizationProvider(Protocol):
    provider_name: str
    model_name: str

    def profile(self) -> dict: ...
    def localize(self, payload: LocalizationProviderInput) -> LocalizationProviderResult: ...


def _provider_prompt(payload: LocalizationProviderInput) -> str:
    skill = get_professional_skill(SKILL_ID)
    rules = "\n".join(f"{idx}. {rule}" for idx, rule in enumerate(skill.provider_rules, 1))
    schema = LocalizedStoryboardSemantic.model_json_schema()
    return f"""你正在执行 AI Drama Studio Professional Skill：{skill.name}（{skill.id}@{skill.version}）。

任务不是写一份独立 Target Bible，也不是只翻译对白；你必须直接把正式原片分镜表改写成目标地区成立的本土化分镜。

目标：
- target_language: {payload.target_language}
- target_region: {payload.target_region}
- scene_strategy: {payload.scene_strategy}
- visual_style: {payload.visual_style}

硬规则：
- characters/scenes/props/dialogue/shots 必须严格逐项覆盖输入给出的稳定 ID，不得漏项、重复、合并、拆分或创造 ID。
- localized_visual_description_zh / camera_description_zh / entity description / target_dialogue_zh 必须使用简体中文，供中国用户理解和审核。
- target_dialogue 必须是 {payload.target_language} 的本土自然对白；target_dialogue_zh 是它的中文意思，不是第二句要说出的对白。
- 不改变 shot 顺序、shot anchor、start/end/duration 或结构化 camera facts。
- 可以本土化人物姓名、社会身份、地点、文化物件和自然表达，但不得改写故事事件顺序。
- 不生成资产图片、H3 prompt、音频、视频或 Artifact/target entity ID。
- 只输出一个符合 JSON Schema 的 object，不输出 Markdown 或解释。

Professional Skill rules:
{rules}

正式 Source storyboard view：
{json.dumps(payload.source_view, ensure_ascii=False, separators=(",", ":"))}

输出 JSON Schema：
{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}
"""


def _validate_semantic(payload: LocalizationProviderInput, semantic: LocalizedStoryboardSemantic) -> LocalizedStoryboardSemantic:
    coverage = (
        (payload.expected_character_ids, [item.source_character_id for item in semantic.characters], "character"),
        (payload.expected_scene_ids, [item.source_scene_id for item in semantic.scenes], "scene"),
        (payload.expected_prop_ids, [item.source_prop_id for item in semantic.props], "prop"),
        (payload.expected_dialogue_ids, [item.utterance_id for item in semantic.dialogue], "dialogue"),
        (payload.expected_shot_ids, [item.shot_anchor_id for item in semantic.shots], "shot"),
    )
    for expected, actual, label in coverage:
        if len(actual) != len(set(actual)) or set(actual) != set(expected):
            raise AppError(
                "LOCALIZED_STORYBOARD_PROVIDER_COVERAGE_INVALID",
                f"本土化分镜 Provider 的 {label} 覆盖不完整",
                status_code=502,
                details={"expected": len(expected), "actual": len(actual)},
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
        _assert_chinese("目标对白中文翻译", item.target_dialogue_zh)
    for item in semantic.shots:
        _assert_chinese("本土化镜头描述", item.localized_visual_description_zh)
        _assert_chinese("镜头语言中文说明", item.camera_description_zh)
    return semantic


class _DoubaoProvider:
    provider_name = "volcengine-ark"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.p7_doubao_model
        if settings.p7_doubao_api_key is None or not settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError("LOCALIZED_STORYBOARD_PROVIDER_NOT_CONFIGURED", "火山引擎本土化分镜 Provider 尚未配置", status_code=409)

    def profile(self) -> dict:
        return {"provider": self.provider_name, "model": self.model_name, "mode": "CLOUD_API_TEXT", "skill": SKILL_ID}

    def localize(self, payload: LocalizationProviderInput) -> LocalizationProviderResult:
        assert self.settings.p7_doubao_api_key is not None
        client = Ark(
            api_key=self.settings.p7_doubao_api_key.get_secret_value(),
            base_url=self.settings.p7_doubao_base_url,
            timeout=self.settings.p7_doubao_request_timeout_seconds,
            max_retries=2,
        )
        response = client.responses.create(
            model=self.model_name,
            input=[{"role": "user", "content": [{"type": "input_text", "text": _provider_prompt(payload)}]}],
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
            semantic=_validate_semantic(payload, semantic),
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

    def localize(self, payload: LocalizationProviderInput) -> LocalizationProviderResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key is not None and self.api_key.get_secret_value().strip():
            headers["Authorization"] = f"Bearer {self.api_key.get_secret_value()}"
        with httpx.Client(timeout=httpx.Timeout(self.settings.p7_qwen_local_request_timeout_seconds)) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": self.model_name, "messages": [{"role": "user", "content": _provider_prompt(payload)}], "temperature": 0.2, "max_tokens": MAX_OUTPUT_TOKENS},
            )
            response.raise_for_status()
            body = response.json()
        choices = body.get("choices") or []
        text = ((choices[0].get("message") or {}).get("content") if choices else None)
        if not isinstance(text, str) or not text.strip():
            raise AppError("LOCALIZED_STORYBOARD_PROVIDER_EMPTY", "本土化分镜 Provider 未返回可用文本", status_code=502)
        semantic = LocalizedStoryboardSemantic.model_validate_json(_json_object(text))
        return LocalizationProviderResult(semantic=_validate_semantic(payload, semantic), remote_job_id=str(body.get("id") or "") or None)


def _provider(settings: Settings, selection: SourceUnderstandingProvider) -> LocalizationProvider:
    if selection == SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API:
        return _DoubaoProvider(settings)
    if selection == SourceUnderstandingProvider.QWEN3_8_27B_LOCAL:
        return _LocalQwenProvider(settings, model_name=settings.p7_qwen38_local_model, base_url=settings.p7_qwen38_local_base_url, api_key=settings.p7_qwen38_local_api_key)
    if selection in {SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL, SourceUnderstandingProvider.QWEN3_VL_LOCAL}:
        return _LocalQwenProvider(settings, model_name=settings.p7_qwen3_vl_8b_local_model, base_url=settings.p7_qwen3_vl_8b_local_base_url, api_key=settings.p7_qwen3_vl_8b_local_api_key)
    raise AppError("LOCALIZED_STORYBOARD_PROVIDER_UNSUPPORTED", "当前本土化分镜 Provider 未实现", status_code=422)


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
                "dialogue": [{"utterance_id": ref.utterance_id, "delivery": ref.delivery.value} for ref in shot.dialogue],
                "sound_effects": list(shot.sound_effects),
                "ambience": list(shot.ambience),
            })

    characters = [item for item in snapshot.source_characters.entities if item.character_id in used_chars]
    scenes = [item for item in snapshot.source_scenes.entities if item.scene_id in used_scenes]
    props = [item for item in snapshot.source_props.entities if item.prop_id in used_props]
    dialogue = [line for episode in sorted(snapshot.episodes, key=lambda item: item.episode_order) for line in episode.canonical_dialogue]
    return {
        "characters": [{"source_character_id": item.character_id, "name": item.display_name, "aliases": item.aliases, "notes": item.notes} for item in characters],
        "scenes": [{"source_scene_id": item.scene_id, "name": item.display_name, "aliases": item.aliases, "notes": item.notes} for item in scenes],
        "props": [{"source_prop_id": item.prop_id, "name": item.display_name, "aliases": item.aliases, "notes": item.notes} for item in props],
        "dialogue": [{"utterance_id": item.utterance_id, "utterance_number": item.utterance_number, "text": item.text, "language": item.language, "speaker_character_id": speaker_by_utterance.get(item.utterance_id)} for item in dialogue],
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


def create_localized_storyboard_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project = get_project(db, project_id)
    if project.project_type != ProjectType.REPLICA:
        raise AppError("LOCALIZED_STORYBOARD_PROJECT_UNSUPPORTED", "当前五步主生产链只正式支持 REPLICA", status_code=422)
    snapshot_artifact, snapshot = _load_snapshot(db, project_id)
    provider = _provider(get_settings(), project.source_understanding_provider)
    payload = _payload(project, snapshot)
    fingerprint = _sha({"snapshot": snapshot_artifact.input_fingerprint, "target_language": project.target_language, "target_region": project.target_region, "scene_strategy": str(project.scene_strategy), "visual_style": project.visual_style, "provider": provider.profile(), "skill": get_professional_skill(SKILL_ID).version})
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
        job_payload = {"source_snapshot_artifact_id": snapshot_artifact.id, "source_snapshot_fingerprint": snapshot_artifact.input_fingerprint, "target_language": project.target_language, "target_region": project.target_region, "provider_profile": profile, "generation_sequence": sequence}
        def _remote_call(_):
            provider_result = provider.localize(payload)
            return ProviderDispatchResult(value=provider_result, remote_job_id=provider_result.remote_job_id)

        job, dispatched = dispatch_provider_call(db, task_id=task.id, provider=provider.provider_name, model=provider.model_name, capability=Capability.STORYBOARD_LOCALIZATION, payload=job_payload, artifact_id=snapshot_artifact.id, remote_call=_remote_call)
        result: LocalizationProviderResult = dispatched.value
        context.checkpoint({"provider_job_id": job.id, "generation_sequence": sequence}, progress_percent=70)

    semantic = result.semantic
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
        refs: list[LocalizedShotDialogueRef] = []
        for source_ref in shot.dialogue:
            line = dialogue_by_id[source_ref.utterance_id]
            refs.append(LocalizedShotDialogueRef(utterance_id=line.utterance_id, utterance_number=line.utterance_number, delivery=source_ref.delivery, target_character_id=line.target_character_id, target_dialogue=line.target_dialogue, target_dialogue_zh=line.target_dialogue_zh, overlap_start_us=source_ref.overlap_start_us, overlap_end_us=source_ref.overlap_end_us))
        media = episode_media.get(episode.episode_id)
        if media is None:
            raise AppError("LOCALIZED_STORYBOARD_EPISODE_MEDIA_MISSING", "Source Snapshot 缺少 Episode 媒体尺寸", status_code=500)
        shots.append(LocalizedStoryboardShot(storyboard_shot_id=f"localized:{episode.episode_id}:{shot.shot_anchor_id}", episode_id=episode.episode_id, episode_order=episode.episode_order, source_shot_anchor_id=shot.shot_anchor_id, shot_number=shot.shot_number, start_us=shot.start_us, end_us=shot.end_us, duration_us=shot.duration_us, output_ratio=_nearest_h3_ratio(media.width, media.height), camera_language=shot.camera_language, source_visual_description=shot.visual_description, localized_visual_description_zh=localized.localized_visual_description_zh, camera_description_zh=localized.camera_description_zh, target_character_ids=[target_char[x] for x in view["character_ids"] if x in target_char], target_scene_ids=[target_scene[x] for x in view["scene_ids"] if x in target_scene], target_prop_ids=[target_prop[x] for x in view["prop_ids"] if x in target_prop], dialogue=refs, sound_effects=shot.sound_effects, ambience=shot.ambience))

    content = ReplicaLocalizedStoryboardContent(source_snapshot_artifact_id=snapshot_artifact.id, target_language=project.target_language, target_region=project.target_region, characters=characters, scenes=scenes, props=props, dialogue=dialogue_lines, shots=shots)
    skill = get_professional_skill(SKILL_ID)
    provenance = LocalizedStoryboardProvenance(source_snapshot_artifact_id=snapshot_artifact.id, source_snapshot_revision=snapshot_artifact.revision, source_snapshot_fingerprint=snapshot_artifact.input_fingerprint, target_language=project.target_language, target_region=project.target_region, generation_sequence=sequence, professional_skill_version=skill.version, provider_job=PipelineProviderJobProvenance(provider_job_id=job.id, provider=job.provider, model=job.model, payload_fingerprint=job.payload_fingerprint), generated_by_task_id=task.id)
    context.checkpoint({"provider_job_id": job.id, "generation_sequence": sequence, "shot_count": len(shots)}, progress_percent=95)
    return content, provenance


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != TASK_TYPE or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
        return None
    now = utc_now()
    result = db.execute(update(Task).where(Task.id == task_id, Task.task_type == TASK_TYPE, Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts).values(status=TaskStatus.RUNNING, attempt=task.attempt + 1, worker_id=worker_id, heartbeat_at=now, started_at=func.coalesce(Task.started_at, now), finished_at=None, updated_at=now))
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
    return LocalizedStoryboardCandidateRead(id=row.id, project_id=row.project_id, generation_sequence=row.generation_sequence, review_status=CandidateStatus(row.review_status), review_reason=row.review_reason, reviewed_at=row.reviewed_at, created_at=row.created_at, content=ReplicaLocalizedStoryboardContent.model_validate(row.content_json), provenance=LocalizedStoryboardProvenance.model_validate(row.provenance_json))


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


def accept_localized_storyboard_candidate(db: Session, *, project_id: str, candidate_id: str, command: PipelineReviewCommand) -> LocalizedStoryboardRead:
    project = get_project(db, project_id)
    candidate = db.get(ReplicaLocalizedStoryboardCandidate, candidate_id)
    if candidate is None or candidate.project_id != project_id: raise AppError("LOCALIZED_STORYBOARD_CANDIDATE_NOT_FOUND", "本土化分镜候选不存在", status_code=404)
    if candidate.review_status != CandidateStatus.NEEDS_REVIEW.value: raise AppError("LOCALIZED_STORYBOARD_CANDIDATE_NOT_REVIEWABLE", "候选当前不可审核", status_code=409)
    if candidate.source_snapshot_artifact_id != command.expected_upstream_artifact_id or candidate.generation_sequence != command.expected_generation_sequence: raise AppError("LOCALIZED_STORYBOARD_REVIEW_STALE", "本土化分镜审核输入已变化", status_code=409)
    source = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    if source is None or source.id != candidate.source_snapshot_artifact_id: raise AppError("LOCALIZED_STORYBOARD_REVIEW_STALE", "正式原片分镜已经更新，请重新本土化", status_code=409)
    content = ReplicaLocalizedStoryboardContent.model_validate(candidate.content_json)
    previous = _current_artifact(db, project_id, ArtifactType.TARGET_STORYBOARD)
    latest = _latest_artifact(db, project_id, ArtifactType.TARGET_STORYBOARD)
    if previous: _mark_stale_with_downstream(db, [previous])
    skill = get_professional_skill(SKILL_ID)
    artifact = ArtifactNode(project_id=project_id, artifact_type=ArtifactType.TARGET_STORYBOARD.value, namespace=ArtifactNamespace.PRODUCTION, label="本土化分镜表", revision=(latest.revision if latest else 0) + 1, input_fingerprint=_sha({"candidate": candidate.input_fingerprint, "content": content.model_dump(mode="json")}), skill_id=skill.id, skill_version=skill.version, validity=ArtifactValidity.CURRENT, is_current=True, metadata_json={"schema_version": LOCALIZED_STORYBOARD_SCHEMA_VERSION, "source_snapshot_artifact_id": source.id, "shot_count": len(content.shots), "dialogue_count": len(content.dialogue)})
    reviewed_at = utc_now()
    provenance = dict(candidate.provenance_json)
    provenance.update({"candidate_id": candidate.id, "reviewed_by": "USER_EXPLICIT_ACTION", "reviewed_at": reviewed_at.isoformat(), "review_reason": command.reason, "supersedes_artifact_id": latest.id if latest else None})
    db.add(artifact); db.flush()
    db.add(ReplicaLocalizedStoryboardRevision(project_id=project_id, artifact_id=artifact.id, source_snapshot_artifact_id=source.id, candidate_id=candidate.id, generated_by_task_id=candidate.generated_by_task_id, schema_version=LOCALIZED_STORYBOARD_SCHEMA_VERSION, content_json=content.model_dump(mode="json"), provenance_json=provenance))
    db.add(ArtifactEdge(project_id=project_id, source_node_id=source.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
    if latest: db.add(ArtifactEdge(project_id=project_id, source_node_id=artifact.id, target_node_id=latest.id, relation_type=ArtifactRelationType.SUPERSEDES))
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
