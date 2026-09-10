import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.core.errors import AppError
from app.core.time import utc_now
from app.projects.service import get_project
from app.skills.models import Capability
from app.sources.models import Episode
from app.workflow.models import ProviderJob, ProviderJobStatus, Task, TaskStatus


_SENSITIVE_PROVIDER_KEYS = {
    "apikey",
    "authorization",
    "accesstoken",
    "refreshtoken",
    "token",
    "secret",
    "password",
}


@dataclass(frozen=True)
class ProviderDispatchResult:
    value: Any = None
    remote_job_id: str | None = None
    completed: bool = True


def _normalized_key(value: str) -> str:
    return value.lower().replace("_", "").replace("-", "").replace(" ", "")


def _assert_payload_has_no_credentials(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if _normalized_key(key_text) in _SENSITIVE_PROVIDER_KEYS:
                raise AppError(
                    "SENSITIVE_PROVIDER_PAYLOAD",
                    "Provider 业务 payload 不能包含凭据或 Authorization；凭据必须仅通过运行时配置传递",
                    status_code=422,
                    details={"path": f"{path}.{key_text}"},
                )
            _assert_payload_has_no_credentials(nested, f"{path}.{key_text}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_payload_has_no_credentials(nested, f"{path}[{index}]")


def provider_payload_fingerprint(payload: dict) -> str:
    _assert_payload_has_no_credentials(payload)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_provider_scope(
    db: Session,
    *,
    project_id: str,
    episode_id: str | None,
    artifact_id: str | None,
) -> None:
    get_project(db, project_id)
    if episode_id is not None:
        episode = db.get(Episode, episode_id)
        if episode is None or episode.project_id != project_id:
            raise AppError("PROVIDER_EPISODE_SCOPE_INVALID", "ProviderJob Episode 范围无效", status_code=422)
    if artifact_id is not None:
        artifact = db.get(ArtifactNode, artifact_id)
        if artifact is None or artifact.project_id != project_id:
            raise AppError("PROVIDER_ARTIFACT_SCOPE_INVALID", "ProviderJob Artifact 范围无效", status_code=422)
        if artifact.validity != ArtifactValidity.CURRENT or not artifact.is_current:
            raise AppError("STALE_ARTIFACT_INPUT", "Provider 不能消费已过期 Artifact", status_code=409)


def create_provider_job_before_remote(
    db: Session,
    *,
    task_id: str,
    provider: str,
    model: str,
    capability: Capability,
    payload: dict,
    episode_id: str | None = None,
    artifact_id: str | None = None,
) -> ProviderJob:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    if task.status != TaskStatus.RUNNING:
        raise AppError("PROVIDER_REQUIRES_RUNNING_TASK", "Provider 调用必须属于正在运行的 Task", status_code=409)
    if task.cancel_requested:
        raise AppError("TASK_CANCEL_REQUESTED", "任务已请求取消，禁止继续发起 Provider 调用", status_code=409)
    _assert_provider_scope(
        db,
        project_id=task.project_id,
        episode_id=episode_id,
        artifact_id=artifact_id,
    )
    payload_fingerprint = provider_payload_fingerprint(payload)
    now = utc_now()
    job_id = str(uuid4())
    job = ProviderJob(
        id=job_id,
        project_id=task.project_id,
        task_id=task.id,
        episode_id=episode_id,
        artifact_id=artifact_id,
        provider=provider.strip(),
        model=model.strip(),
        capability=capability.value,
        payload_fingerprint=payload_fingerprint,
        attempt=task.attempt,
        status=ProviderJobStatus.RUNNING,
        local_job_id=f"provider-job:{job_id}",
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _safe_provider_failure(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return f"{exc.code}: {exc.message}"[:1000]
    return f"Provider 请求失败（{type(exc).__name__}）"


def dispatch_provider_call(
    db: Session,
    *,
    task_id: str,
    provider: str,
    model: str,
    capability: Capability,
    payload: dict,
    remote_call: Callable[[ProviderJob], ProviderDispatchResult],
    episode_id: str | None = None,
    artifact_id: str | None = None,
) -> tuple[ProviderJob, ProviderDispatchResult]:
    """Persist and commit ProviderJob first, then invoke the external/paid adapter."""

    job = create_provider_job_before_remote(
        db,
        task_id=task_id,
        provider=provider,
        model=model,
        capability=capability,
        payload=payload,
        episode_id=episode_id,
        artifact_id=artifact_id,
    )
    try:
        result = remote_call(job)
    except Exception as exc:
        now = utc_now()
        persisted = db.get(ProviderJob, job.id)
        if persisted is not None:
            persisted.status = ProviderJobStatus.FAILED
            persisted.safe_error = _safe_provider_failure(exc)
            persisted.finished_at = now
            persisted.updated_at = now
            db.add(persisted)
            db.commit()
            db.refresh(persisted)
            job = persisted
        # Provider adapters are allowed to raise an authored AppError when they can safely
        # distinguish a contract/response failure from transport failure. Preserve that code and
        # message after the ProviderJob has been durably marked FAILED instead of collapsing every
        # failure into PROVIDER_REQUEST_FAILED.
        if isinstance(exc, AppError):
            raise
        raise AppError(
            "PROVIDER_REQUEST_FAILED",
            f"Provider 请求失败（{type(exc).__name__}）",
            status_code=502,
        ) from exc

    now = utc_now()
    persisted = db.get(ProviderJob, job.id)
    if persisted is None:
        raise AppError("PROVIDER_JOB_NOT_FOUND", "ProviderJob 持久化记录丢失", status_code=500)
    persisted.remote_job_id = result.remote_job_id
    persisted.status = ProviderJobStatus.SUCCEEDED if result.completed else ProviderJobStatus.SUBMITTED
    persisted.finished_at = now if result.completed else None
    persisted.safe_error = None
    persisted.updated_at = now
    db.add(persisted)
    db.commit()
    db.refresh(persisted)
    return persisted, result


def mark_provider_job_succeeded(db: Session, provider_job_id: str) -> ProviderJob:
    job = db.get(ProviderJob, provider_job_id)
    if job is None:
        raise AppError("PROVIDER_JOB_NOT_FOUND", "ProviderJob 不存在", status_code=404)
    if job.status not in {ProviderJobStatus.SUBMITTED, ProviderJobStatus.RUNNING}:
        raise AppError("PROVIDER_JOB_NOT_COMPLETABLE", "当前 ProviderJob 状态不能标记成功", status_code=409)
    now = utc_now()
    job.status = ProviderJobStatus.SUCCEEDED
    job.finished_at = now
    job.safe_error = None
    job.updated_at = now
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_provider_job_failed(db: Session, provider_job_id: str, *, safe_error: str) -> ProviderJob:
    job = db.get(ProviderJob, provider_job_id)
    if job is None:
        raise AppError("PROVIDER_JOB_NOT_FOUND", "ProviderJob 不存在", status_code=404)
    if job.status not in {ProviderJobStatus.SUBMITTED, ProviderJobStatus.RUNNING}:
        raise AppError("PROVIDER_JOB_NOT_FAILABLE", "当前 ProviderJob 状态不能标记失败", status_code=409)
    now = utc_now()
    job.status = ProviderJobStatus.FAILED
    job.safe_error = (safe_error.strip() or "Provider 请求失败")[:1000]
    job.finished_at = now
    job.updated_at = now
    db.add(job)
    db.commit()
    db.refresh(job)
    return job