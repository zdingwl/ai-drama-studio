"""Script-only typed pipeline. Never calls Replica P11/P12 or video production services."""

import hashlib
import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.script_localization.models import ScriptLocalizationRevision
from app.script_localization.providers import ScriptLocalizationProvider
from app.script_localization.schemas import (
    AnalysisSemantic, LocalizedScriptSemantic, PlanSemantic, ResultStatus,
    ScriptLocalizationStateRead, StageRead, TargetScriptEditCommand,
)
from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill
from app.sources.models import SourceAsset, SourceDocument
from app.sources.storage import resolve_source_asset_path
from app.workflow.models import Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import TaskCancelled, create_task_from_command, mark_task_failed, mark_task_succeeded, resume_task, retry_task
from app.workflow.worker import TaskExecutionContext

TASK_TYPE = "SCRIPT_LOCALIZATION_STAGE"
ANALYSIS_SKILL = "script-analysis"
LOCALIZATION_SKILL = "script-localization"
# The first production slice is deliberately bounded. Never silently truncate a script.
MAX_SCRIPT_CHARS = 24000


@dataclass(frozen=True)
class InputBundle:
    project: object
    source: ArtifactNode
    text: str
    artifacts: list[ArtifactNode]
    analysis: dict | None = None
    plan: dict | None = None


def _hash(value: object) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def require_project(db: Session, project_id: str):
    project = get_project(db, project_id)
    if project.project_type != ProjectType.SCRIPT_LOCALIZATION:
        raise AppError("SCRIPT_LOCALIZATION_NOT_ALLOWED", "当前操作仅适用于剧本本土化", status_code=422)
    return project


def _current(db: Session, project_id: str, kind: ArtifactType) -> ArtifactNode | None:
    rows = list(db.scalars(select(ArtifactNode).where(
        ArtifactNode.project_id == project_id,
        ArtifactNode.artifact_type == kind.value,
        ArtifactNode.validity == ArtifactValidity.CURRENT,
        ArtifactNode.is_current.is_(True),
    )).all())
    if len(rows) > 1:
        raise AppError("SCRIPT_LOCALIZATION_CURRENT_AMBIGUOUS", f"{kind.value} 存在多个当前版本", status_code=409)
    return rows[0] if rows else None


def _require(db: Session, project_id: str, kind: ArtifactType) -> ArtifactNode:
    result = _current(db, project_id, kind)
    if result is None:
        raise AppError("SCRIPT_LOCALIZATION_INPUT_REQUIRED", f"请先完成 {kind.value}；旧版本不可作为正式输入", status_code=409)
    return result


def _content(db: Session, artifact: ArtifactNode) -> dict:
    row = db.scalar(select(ScriptLocalizationRevision).where(
        ScriptLocalizationRevision.artifact_id == artifact.id,
        ScriptLocalizationRevision.project_id == artifact.project_id,
    ))
    if row is None:
        raise AppError("SCRIPT_LOCALIZATION_REVISION_MISSING", "剧本分析结果缺少独立版本记录，请检查数据库迁移", status_code=500)
    return row.content_json


def _source(db: Session, project_id: str) -> tuple[ArtifactNode, str]:
    source = _require(db, project_id, ArtifactType.SOURCE_TEXT)
    document = db.scalar(select(SourceDocument).where(
        SourceDocument.project_id == project_id,
        SourceDocument.is_current.is_(True),
    ))
    if document is None or source.metadata_json.get("document_id") != document.id:
        raise AppError("SCRIPT_LOCALIZATION_SOURCE_STALE", "原剧本版本已经变化，请重新读取", status_code=409)
    asset = db.get(SourceAsset, document.source_asset_id)
    if asset is None or asset.project_id != project_id:
        raise AppError("SCRIPT_LOCALIZATION_SOURCE_MISSING", "原剧本素材不存在", status_code=409)
    path = resolve_source_asset_path(asset.relative_path)
    if not path.is_file():
        raise AppError("SCRIPT_LOCALIZATION_SOURCE_MISSING", "原剧本文件不存在", status_code=409)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise AppError("SCRIPT_LOCALIZATION_SOURCE_ENCODING", "原剧本编码异常", status_code=422) from exc
    if not text.strip():
        raise AppError("SCRIPT_LOCALIZATION_SOURCE_EMPTY", "原剧本不能为空", status_code=422)
    if len(text) > MAX_SCRIPT_CHARS:
        raise AppError("SCRIPT_LOCALIZATION_SOURCE_TOO_LONG", "当前剧本分析仅支持 24000 字符以内；长剧本分块分析尚未验收，不能截断处理", status_code=422)
    return source, text


def _inputs(db: Session, project_id: str, stage: str) -> InputBundle:
    project = require_project(db, project_id)
    source, text = _source(db, project_id)
    if stage not in {"analyze", "plan", "generate"}:
        raise AppError("SCRIPT_LOCALIZATION_STAGE_INVALID", "未知剧本处理阶段", status_code=422)
    artifacts = [source]
    analysis = None
    plan = None
    if stage in {"plan", "generate"}:
        snapshot = _require(db, project_id, ArtifactType.SOURCE_TEXT_SNAPSHOT)
        story = _require(db, project_id, ArtifactType.STORY_SKELETON)
        rhythm = _require(db, project_id, ArtifactType.RHYTHM_SKELETON)
        artifacts += [snapshot, story, rhythm]
        analysis = _content(db, snapshot)
        if analysis.get("source_artifact_id") != source.id:
            raise AppError("SCRIPT_LOCALIZATION_SOURCE_STALE", "剧本分析结果与当前原剧本不一致", status_code=409)
    if stage == "generate":
        plan_artifact = _require(db, project_id, ArtifactType.ADAPTATION_PLAN)
        artifacts.append(plan_artifact)
        plan = _content(db, plan_artifact)
        if plan.get("source_snapshot_artifact_id") != artifacts[1].id:
            raise AppError("SCRIPT_LOCALIZATION_PLAN_STALE", "本土化方案引用了旧剧本分析", status_code=409)
        if plan.get("target_language") != project.target_language or plan.get("target_region") != project.target_region:
            raise AppError("SCRIPT_LOCALIZATION_TARGET_CHANGED", "目标语言或地区已更新，请重新生成本土化方案", status_code=409)
        if plan.get("semantic", {}).get("unresolved_decisions"):
            raise AppError("SCRIPT_LOCALIZATION_HUMAN_DECISION_REQUIRED", "当前本土化方案包含待人工决策的核心文化冲突，禁止自动生成正式剧本", status_code=409)
    return InputBundle(project=project, source=source, text=text, artifacts=artifacts, analysis=analysis, plan=plan)


def _skill(stage: str):
    return get_professional_skill(ANALYSIS_SKILL if stage == "analyze" else LOCALIZATION_SKILL)


def _fingerprint(bundle: InputBundle, stage: str, profile: dict) -> str:
    skill = _skill(stage)
    return _hash({
        "task": TASK_TYPE, "stage": stage,
        "source_ids": [(a.id, a.revision, a.input_fingerprint) for a in bundle.artifacts],
        "project_id": bundle.project.id, "workflow_revision": bundle.project.workflow_revision,
        "language": bundle.project.target_language, "region": bundle.project.target_region,
        "skill": [skill.id, skill.version], "provider": profile,
    })


def start_stage(db: Session, project_id: str, stage: str, idempotency_key: str) -> Task:
    bundle = _inputs(db, project_id, stage)
    provider = ScriptLocalizationProvider(get_settings(), bundle.project.source_understanding_provider)
    profile = provider.profile()
    task = create_task_from_command(db, project_id=project_id, idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=TASK_TYPE,
            task_name={"analyze": "分析原剧本", "plan": "制定本土化方案", "generate": "生成本土化剧本"}[stage],
            input_fingerprint=_fingerprint(bundle, stage, profile),
            input_artifact_ids=[artifact.id for artifact in bundle.artifacts],
            initial_checkpoint_json={"stage": stage},
            max_attempts=3,
        ),
    )
    key = idempotency_key.strip()
    if task.status == TaskStatus.FAILED and task.attempt < task.max_attempts and task.idempotency_key != key:
        return retry_task(db, project_id, task.id)
    if task.status == TaskStatus.INTERRUPTED and task.attempt < task.max_attempts and task.idempotency_key != key:
        return resume_task(db, project_id, task.id)
    return task


def _stage(db: Session, project_id: str, kind: ArtifactType) -> StageRead:
    current = _current(db, project_id, kind)
    latest = current or db.scalar(select(ArtifactNode).where(
        ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == kind.value,
    ).order_by(ArtifactNode.revision.desc()).limit(1))
    if latest is None:
        return StageRead(status=ResultStatus.NOT_BUILT)
    return StageRead(
        status=ResultStatus.CURRENT if current is not None else ResultStatus.STALE,
        artifact_id=latest.id, revision=latest.revision,
        content=_content(db, latest),
    )


def get_state(db: Session, project_id: str) -> ScriptLocalizationStateRead:
    require_project(db, project_id)
    return ScriptLocalizationStateRead(
        project_id=project_id,
        analysis=_stage(db, project_id, ArtifactType.SOURCE_TEXT_SNAPSHOT),
        plan=_stage(db, project_id, ArtifactType.ADAPTATION_PLAN),
        target_script=_stage(db, project_id, ArtifactType.TARGET_SCRIPT),
        final_output=_stage(db, project_id, ArtifactType.FINAL_OUTPUT),
    )


def _publish_one(db: Session, *, project_id: str, kind: ArtifactType,
                 namespace: ArtifactNamespace, label: str, content: dict,
                 sources: list[ArtifactNode], skill_id: str, skill_version: str,
                 task_id: str | None, provider_job_id: str | None = None) -> ArtifactNode:
    previous = _current(db, project_id, kind)
    if previous is not None:
        _mark_stale_with_downstream(db, [previous])
    revision = int(db.scalar(select(func.max(ArtifactNode.revision)).where(
        ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == kind.value,
    )) or 0) + 1
    node = ArtifactNode(
        project_id=project_id, artifact_type=kind.value, namespace=namespace, label=label,
        revision=revision, input_fingerprint=_hash({"content": content, "sources": [a.id for a in sources]}),
        skill_id=skill_id, skill_version=skill_version,
        validity=ArtifactValidity.CURRENT, is_current=True,
        metadata_json={"schema_version": "1.0", "source_ids": [a.id for a in sources]},
    )
    db.add(node)
    db.flush()
    db.add(ScriptLocalizationRevision(
        project_id=project_id, artifact_id=node.id,
        content_json=content,
        provenance_json={"input_artifact_ids": [a.id for a in sources], "task_id": task_id,
                         "provider_job_id": provider_job_id, "skill_id": skill_id,
                         "skill_version": skill_version},
    ))
    for parent in sources:
        db.add(ArtifactEdge(project_id=project_id, source_node_id=parent.id,
                            target_node_id=node.id, relation_type=ArtifactRelationType.DERIVED_FROM))
    if previous is not None:
        db.add(ArtifactEdge(project_id=project_id, source_node_id=node.id,
                            target_node_id=previous.id, relation_type=ArtifactRelationType.SUPERSEDES))
    return node


def _prompt(bundle: InputBundle, stage: str) -> tuple[str, type]:
    if stage == "analyze":
        return (
            "严格依照原剧本识别人物/场次/对白关系、故事、节奏与文化锚点。"
            "严禁虚构不存在的人物、对白、动机或结局，证据不足记入 unresolved_questions。"
            "保留原文顺序与场次，全文只读。\n原剧本：\n" + bundle.text,
            AnalysisSemantic,
        )
    if stage == "plan":
        return (
            "为下列已分析剧本设计目标地区本土化方案，只做方案不输出剧本。"
            "角色映射、称谓、机构、货币、文化习惯需一致；故事主线/角色功能/冲突因果/反转信息顺序均不可静默改动。"
            "需改变核心冲突才能成立的情况写进 unresolved_decisions。\n"
            f"目标语言：{bundle.project.target_language}；目标地区：{bundle.project.target_region}\n"
            f"当前 Source 分析：{json.dumps(bundle.analysis, ensure_ascii=False)}",
            PlanSemantic,
        )
    return (
        "请输出完整目标地区剧本：逐场保留原文的场次、剧情因果、人物功能、冲突与信息揭示顺序；"
        "根据全剧唯一的映射表本土化称谓、对白、制度与文化。"
        "script_text 必须包含完整可读的剧本正文，不要摘要，不要遗漏最后的场次。"
        "重要替换写入 changes；不确定的文化冲突不得静默发明解决方案。\n"
        f"目标语言：{bundle.project.target_language}；地区：{bundle.project.target_region}\n"
        f"本土化方案：{json.dumps(bundle.plan, ensure_ascii=False)}\n原剧本：\n{bundle.text}",
        LocalizedScriptSemantic,
    )


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    now = utc_now()
    result = db.execute(update(Task).where(
        Task.id == task_id, Task.task_type == TASK_TYPE,
        Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts,
    ).values(status=TaskStatus.RUNNING, attempt=Task.attempt + 1, worker_id=worker_id,
             heartbeat_at=now, started_at=func.coalesce(Task.started_at, now),
             finished_at=None, updated_at=now))
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    return db.get(Task, task_id)


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[str, dict, str]:
    stage = str(task.checkpoint_json.get("stage") or "")
    with context.session_factory() as db:
        bundle = _inputs(db, task.project_id, stage)
        provider = ScriptLocalizationProvider(get_settings(), bundle.project.source_understanding_provider)
        if task.input_artifact_ids_json != [a.id for a in bundle.artifacts] or task.input_fingerprint != _fingerprint(bundle, stage, provider.profile()):
            raise AppError("STALE_ARTIFACT_INPUT", "输入版本已经发生变化，请重新创建剧本任务", status_code=409)
        prompt, model_type = _prompt(bundle, stage)
        profile = provider.profile()
        skill = _skill(stage)
    context.checkpoint({"stage": stage, "progress": "provider"}, progress_percent=20)

    def call(_job):
        semantic, remote_id = provider.generate(skill_id=skill.id, prompt=prompt, output_model=model_type)
        return ProviderDispatchResult(value=semantic.model_dump(mode="json"), remote_job_id=remote_id, completed=True)

    with context.session_factory() as db:
        job, response = dispatch_provider_call(db,
            task_id=task.id, provider=provider.provider_name, model=provider.model_name,
            capability={"analyze": Capability.SCRIPT_ANALYSIS, "plan": Capability.LOCALIZATION,
                        "generate": Capability.TARGET_SCRIPT}[stage],
            payload={"task": TASK_TYPE, "stage": stage, "input_artifact_ids": [a.id for a in bundle.artifacts],
                     "skill": [skill.id, skill.version], "target_language": bundle.project.target_language,
                     "target_region": bundle.project.target_region, "provider_profile": profile},
            artifact_id=bundle.artifacts[-1].id, remote_call=call,
        )
    context.checkpoint({"stage": stage, "progress": "validated"}, progress_percent=90)
    return stage, response.value, job.id


def _publish(db: Session, task_id: str, stage: str, value: dict, job_id: str) -> None:
    task = db.get(Task, task_id)
    if task is None or task.status != TaskStatus.SUCCEEDED:
        raise AppError("SCRIPT_LOCALIZATION_TASK_NOT_SUCCEEDED", "剧本任务尚未成功", status_code=409)
    bundle = _inputs(db, task.project_id, stage)
    provider = ScriptLocalizationProvider(get_settings(), bundle.project.source_understanding_provider)
    if task.input_artifact_ids_json != [a.id for a in bundle.artifacts] or task.input_fingerprint != _fingerprint(bundle, stage, provider.profile()):
        raise AppError("STALE_ARTIFACT_INPUT", "模型调用期间原剧本或本土化方案已变化，禁止发布旧结果", status_code=409)
    skill = _skill(stage)
    if stage == "analyze":
        semantic = AnalysisSemantic.model_validate(value)
        if not semantic.story_beats:
            raise AppError("SCRIPT_LOCALIZATION_ANALYSIS_EMPTY", "未生成可靠故事骨架，拒绝发布", status_code=422)
        snap = _publish_one(db, project_id=task.project_id,
            kind=ArtifactType.SOURCE_TEXT_SNAPSHOT, namespace=ArtifactNamespace.SOURCE,
            label="原剧本结构化分析", content={"source_artifact_id": bundle.source.id,
                                          "source_sha256": bundle.source.input_fingerprint,
                                          "semantic": semantic.model_dump(mode="json")},
            sources=[bundle.source], skill_id=skill.id, skill_version=skill.version,
            task_id=task.id, provider_job_id=job_id)
        _publish_one(db, project_id=task.project_id, kind=ArtifactType.STORY_SKELETON,
            namespace=ArtifactNamespace.SOURCE, label="剧本故事骨架",
            content={"story_beats": [beat.model_dump(mode="json") for beat in semantic.story_beats]},
            sources=[snap], skill_id=skill.id, skill_version=skill.version, task_id=task.id, provider_job_id=job_id)
        _publish_one(db, project_id=task.project_id, kind=ArtifactType.RHYTHM_SKELETON,
            namespace=ArtifactNamespace.SOURCE, label="剧本节奏骨架",
            content={"rhythm_beats": [beat.model_dump(mode="json") for beat in semantic.rhythm_beats]},
            sources=[snap], skill_id=skill.id, skill_version=skill.version, task_id=task.id, provider_job_id=job_id)
    elif stage == "plan":
        semantic = PlanSemantic.model_validate(value)
        _publish_one(db, project_id=task.project_id, kind=ArtifactType.ADAPTATION_PLAN,
            namespace=ArtifactNamespace.TARGET, label="剧本本土化方案",
            content={"source_snapshot_artifact_id": bundle.artifacts[1].id,
                     "target_language": bundle.project.target_language,
                     "target_region": bundle.project.target_region,
                     "semantic": semantic.model_dump(mode="json")},
            sources=bundle.artifacts, skill_id=skill.id, skill_version=skill.version, task_id=task.id, provider_job_id=job_id)
    else:
        semantic = LocalizedScriptSemantic.model_validate(value)
        if not semantic.script_text.strip() or (len(bundle.text) > 1000 and len(semantic.script_text) < len(bundle.text) // 8):
            raise AppError("SCRIPT_LOCALIZATION_TARGET_INCOMPLETE", "目标剧本可能被截断，拒绝发布", status_code=422)
        _publish_one(db, project_id=task.project_id, kind=ArtifactType.TARGET_SCRIPT,
            namespace=ArtifactNamespace.TARGET, label="正式本土化剧本",
            content={"title": semantic.title, "text": semantic.script_text,
                     "changes": [row.model_dump(mode="json") for row in semantic.changes],
                     "consistency_notes": semantic.consistency_notes,
                     "target_language": bundle.project.target_language,
                     "target_region": bundle.project.target_region,
                     "source_text_artifact_id": bundle.source.id,
                     "adaptation_plan_artifact_id": bundle.artifacts[-1].id},
            sources=bundle.artifacts, skill_id=skill.id, skill_version=skill.version, task_id=task.id, provider_job_id=job_id)
    _invalidate_project_plan(db, bundle.project)
    db.commit()


def _mark_publish_failed(db: Session, task_id: str, message: str) -> None:
    task = db.get(Task, task_id)
    if task is not None and task.status == TaskStatus.SUCCEEDED:
        task.status = TaskStatus.FAILED
        task.progress_percent = min(task.progress_percent, 99)
        task.last_error = message[:1000]
        task.finished_at = utc_now()
        db.add(task)
        db.commit()


def run_stage_task(factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"script-localization-{uuid4()}"
    with factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        task = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=factory, task_id=task.id, worker_id=worker_id)
    try:
        stage, value, job_id = _execute(context, task)
    except TaskCancelled:
        return
    except AppError as exc:
        with factory() as db:
            mark_task_failed(db, task.id, safe_error=f"剧本任务失败（{exc.code}）：{exc.message}", worker_id=worker_id)
        return
    except Exception as exc:
        with factory() as db:
            mark_task_failed(db, task.id, safe_error=f"剧本任务异常（{type(exc).__name__}）", worker_id=worker_id)
        return
    with factory() as db:
        finished = mark_task_succeeded(db, task.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        return
    try:
        with factory() as db:
            _publish(db, task.id, stage, value, job_id)
    except AppError as exc:
        with factory() as db:
            db.rollback()
            _mark_publish_failed(db, task.id, f"剧本发布失败（{exc.code}）：{exc.message}")
    except Exception as exc:
        with factory() as db:
            db.rollback()
            _mark_publish_failed(db, task.id, f"剧本发布异常（{type(exc).__name__}）")


def save_target_edit(db: Session, project_id: str, command: TargetScriptEditCommand) -> StageRead:
    project = require_project(db, project_id)
    previous = _require(db, project_id, ArtifactType.TARGET_SCRIPT)
    if previous.id != command.expected_artifact_id:
        raise AppError("SCRIPT_LOCALIZATION_EDIT_CONFLICT", "目标剧本已更新，请刷新后重试", status_code=409)
    content = _content(db, previous)
    if not command.script_text.strip():
        raise AppError("SCRIPT_LOCALIZATION_TARGET_EMPTY", "目标剧本不能为空", status_code=422)
    if command.script_text == content.get("text"):
        return _stage(db, project_id, ArtifactType.TARGET_SCRIPT)
    updated = {**content, "text": command.script_text, "edited_by_user": True}
    skill = get_professional_skill(LOCALIZATION_SKILL)
    try:
        _publish_one(db, project_id=project_id, kind=ArtifactType.TARGET_SCRIPT,
            namespace=ArtifactNamespace.TARGET, label="人工修订的本土化剧本",
            content=updated, sources=[previous], skill_id=skill.id,
            skill_version=skill.version, task_id=None)
        _invalidate_project_plan(db, project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _stage(db, project_id, ArtifactType.TARGET_SCRIPT)


def export_current_script(db: Session, project_id: str) -> StageRead:
    project = require_project(db, project_id)
    target = _require(db, project_id, ArtifactType.TARGET_SCRIPT)
    content = _content(db, target)
    text = str(content.get("text") or "")
    if not text.strip():
        raise AppError("SCRIPT_LOCALIZATION_TARGET_EMPTY", "没有可导出的目标剧本", status_code=409)
    current = _current(db, project_id, ArtifactType.FINAL_OUTPUT)
    if current is not None and current.metadata_json.get("source_ids") == [target.id]:
        return _stage(db, project_id, ArtifactType.FINAL_OUTPUT)
    skill = get_professional_skill(LOCALIZATION_SKILL)
    try:
        _publish_one(db, project_id=project_id, kind=ArtifactType.FINAL_OUTPUT,
            namespace=ArtifactNamespace.PRODUCTION, label="正式本土化剧本导出",
            content={"text": text, "filename": f"script-localized-r{target.revision}.md",
                     "source_target_script_artifact_id": target.id},
            sources=[target], skill_id=skill.id, skill_version=skill.version, task_id=None)
        _invalidate_project_plan(db, project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _stage(db, project_id, ArtifactType.FINAL_OUTPUT)
