"""Breakdown-first Phase P1.2/P1.3/P1.6 的 Breakdown Run 生命周期服务。

职责：
- 为 Episode 当前 ShotRevision 创建 PROCESSING BreakdownRun；
- 在发布 READY 前锁住 source_shot_revision_id，拒绝过期 Revision 冒充 Current；
- P1.3 强制执行真实 Draft validator，禁止由调用方用布尔值绕过；
- 原子切换同 Episode 的 Current Breakdown Run；
- 失败 Run 不替换旧 Current；
- P1.6 提供可加入 ShotRevision 同一事务的 STALE 标记能力。

边界：
- 不运行 ASR/OCR/VLM，不写 Final Character/Scene/Prop 或任何 Shot Binding；
- P1.6 只负责 ShotRevision → BreakdownRun STALE 联动，不做 P1.7 文档收口。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from engine.app import breakdown_validator_v1, shot_revision_v2, studio_v2
from engine.app.breakdown_models_v1 import BREAKDOWN_DRAFT_SCHEMA_VERSION, BreakdownRun
from engine.app.shot_revision_v2 import ShotRevision

READY_STATUSES = {"READY", "READY_WITH_WARNINGS"}
ACTIVE_SOURCE_STATUSES = {"PROCESSING", "READY", "READY_WITH_WARNINGS"}


class BreakdownRunLifecycleError(RuntimeError):
    """Breakdown Run 生命周期违反 Contract。"""


class BreakdownValidationGateError(BreakdownRunLifecycleError):
    """P1.3 validator gate 未通过，因此 Run 已按 FAILED 收口。"""


class BreakdownRunStaleError(BreakdownRunLifecycleError):
    """Run 绑定的 ShotRevision 已不是 Current，禁止发布。"""


def _json_text(value: Any, *, default: Any) -> str:
    payload = default if value is None else value
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _issue_payload(issues: Any) -> list[dict[str, Any]]:
    return [
        {
            "code": item.code,
            "message": item.message,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
        }
        for item in issues
    ]


def _merge_warning_payload(validation_warnings: Any, pipeline_warnings: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if validation_warnings:
        payload["validator"] = _issue_payload(validation_warnings)
    if pipeline_warnings:
        payload["pipeline"] = pipeline_warnings
    return payload


def create_breakdown_run(
    episode_id: str,
    *,
    pipeline_profile: str | None = None,
    component_status: Any = None,
    provider_metadata: Any = None,
) -> BreakdownRun:
    """基于 Episode 当前 ShotRevision 创建一个新的 PROCESSING Run。

    对旧项目会复用 ``ensure_current_revision`` 的 BASELINE 兼容逻辑；如果 Episode
    还没有 Shot，则拒绝创建空 Run。创建新 PROCESSING Run 不会抢占已有 Current READY Run。
    """

    revision_snapshot = shot_revision_v2.ensure_current_revision(episode_id)
    if revision_snapshot is None:
        raise BreakdownRunLifecycleError("当前剧集没有 ShotRevision/Shot，无法创建 Breakdown Run")
    source_revision_id = str(revision_snapshot["id"])

    with studio_v2.get_session() as session:
        episode = session.get(studio_v2.Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        revision = session.get(ShotRevision, source_revision_id)
        if revision is None or revision.episode_id != episode_id or not revision.is_current:
            raise BreakdownRunLifecycleError("创建 Breakdown Run 时 Current ShotRevision 已变化，请重新启动")

        run = BreakdownRun(
            id=studio_v2.new_id("BREAKDOWNRUN"),
            project_id=episode.project_id,
            episode_id=episode.id,
            source_shot_revision_id=revision.id,
            status="PROCESSING",
            is_current=False,
            schema_version=BREAKDOWN_DRAFT_SCHEMA_VERSION,
            pipeline_profile=pipeline_profile,
            component_status_json=_json_text(component_status, default={}),
            provider_metadata_json=_json_text(provider_metadata, default={}),
            counts_json="{}",
            warning_json="{}",
            error_message=None,
            started_at=studio_v2.utcnow(),
            completed_at=None,
        )
        session.add(run)
        session.commit()
        return run


def publish_breakdown_run(
    run_id: str,
    *,
    warnings: Any = None,
    component_status: Any = None,
    provider_metadata: Any = None,
) -> BreakdownRun:
    """验证并把 PROCESSING Run 发布为 Episode Current READY Run。

    P1.3 起发布方不能再传入 ``validation_passed=True``。本函数在同一数据库事务中
    调用真实 Breakdown Draft validator；任一硬校验失败都会把本 Run 收口为 FAILED，
    并保持旧 Current 不变。Validator 计算的真实实体数量会写入 ``counts_json``。

    Validator 通过后还会再次检查 source ShotRevision 仍然是 Episode Current，避免
    分析过程中 Shot 被 split/merge/restore/auto rerun 后旧 Run 竞态发布成最新结果。
    """

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")
        if run.status != "PROCESSING":
            raise BreakdownRunLifecycleError(f"只有 PROCESSING Run 可以发布，当前状态为 {run.status}")

        validation = breakdown_validator_v1.validate_breakdown_run_in_session(session, run)
        run.counts_json = _json_text(validation.counts, default={})
        warning_payload = _merge_warning_payload(validation.warnings, warnings)
        run.warning_json = _json_text(warning_payload, default={})

        if not validation.passed:
            run.status = "FAILED"
            run.is_current = False
            run.error_message = validation.error_message() or "Breakdown Draft validator 未通过"
            if component_status is not None:
                run.component_status_json = _json_text(component_status, default={})
            if provider_metadata is not None:
                run.provider_metadata_json = _json_text(provider_metadata, default={})
            run.completed_at = studio_v2.utcnow()
            session.commit()
            raise BreakdownValidationGateError(run.error_message)

        current_revision = session.scalar(
            select(ShotRevision).where(
                ShotRevision.episode_id == run.episode_id,
                ShotRevision.is_current.is_(True),
            )
        )
        if current_revision is None or current_revision.id != run.source_shot_revision_id:
            run.status = "STALE"
            run.is_current = False
            run.error_message = "source ShotRevision 已不是 Episode Current，禁止发布旧 Breakdown Run"
            run.completed_at = studio_v2.utcnow()
            session.commit()
            raise BreakdownRunStaleError(run.error_message)

        prior_currents = session.scalars(
            select(BreakdownRun).where(
                BreakdownRun.episode_id == run.episode_id,
                BreakdownRun.is_current.is_(True),
            )
        ).all()
        for prior in prior_currents:
            if prior.id == run.id:
                continue
            prior.is_current = False
            if prior.source_shot_revision_id != run.source_shot_revision_id and prior.status in READY_STATUSES:
                prior.status = "STALE"

        if component_status is not None:
            run.component_status_json = _json_text(component_status, default={})
        if provider_metadata is not None:
            run.provider_metadata_json = _json_text(provider_metadata, default={})
        run.error_message = None
        run.status = "READY_WITH_WARNINGS" if warning_payload else "READY"
        run.is_current = True
        run.completed_at = studio_v2.utcnow()
        session.commit()
        return run


def fail_breakdown_run(
    run_id: str,
    error_message: str,
    *,
    component_status: Any = None,
) -> BreakdownRun:
    """把 PROCESSING Run 显式收口为 FAILED；绝不替换旧 Current。"""

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")
        if run.status != "PROCESSING":
            raise BreakdownRunLifecycleError(f"只有 PROCESSING Run 可以失败收口，当前状态为 {run.status}")
        run.status = "FAILED"
        run.is_current = False
        run.error_message = error_message
        if component_status is not None:
            run.component_status_json = _json_text(component_status, default={})
        run.completed_at = studio_v2.utcnow()
        session.commit()
        return run


def mark_episode_breakdown_runs_stale_in_session(
    session: Any,
    episode_id: str,
    *,
    current_shot_revision_id: str,
) -> list[str]:
    """在调用方事务内把旧 ShotRevision 的活动 Breakdown Run 标记为 STALE。

    P1.6 的 ShotRevision 切换必须与 STALE 标记共用一个数据库事务：如果 Shot 修改或
    Revision 写入最终回滚，BreakdownRun 的状态也一起回滚，不能出现“Shot 没切成功但
    Breakdown 已 STALE”的半提交状态。函数只 flush/修改 ORM，不自行 commit。
    """

    episode = session.get(studio_v2.Episode, episode_id)
    if episode is None:
        raise LookupError("剧集不存在")
    current_revision = session.get(ShotRevision, current_shot_revision_id)
    if current_revision is None or current_revision.episode_id != episode_id or not current_revision.is_current:
        raise BreakdownRunLifecycleError("Episode 当前没有可用的 Current ShotRevision")

    runs = session.scalars(
        select(BreakdownRun).where(
            BreakdownRun.episode_id == episode_id,
            BreakdownRun.source_shot_revision_id != current_revision.id,
            BreakdownRun.status.in_(ACTIVE_SOURCE_STATUSES),
        )
    ).all()
    changed: list[str] = []
    now = studio_v2.utcnow()
    for run in runs:
        run.status = "STALE"
        run.is_current = False
        if run.completed_at is None:
            run.completed_at = now
        changed.append(run.id)
    return changed


def mark_episode_breakdown_runs_stale(
    episode_id: str,
    *,
    current_shot_revision_id: str | None = None,
) -> list[str]:
    """把不再解释 Episode Current ShotRevision 的活动 Run 标记为 STALE。

    保留给显式维护/修复调用；P1.6 正常 ShotRevision 提交流程使用
    ``mark_episode_breakdown_runs_stale_in_session``，与 Revision 切换保持原子性。
    历史 Draft 行不会删除。FAILED/已 STALE Run 保持原状态；同一 Current Revision 上的
    非 Current READY 历史 Run也保持可读 READY 状态。
    """

    with studio_v2.get_session() as session:
        episode = session.get(studio_v2.Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")

        if current_shot_revision_id is None:
            current_revision = session.scalar(
                select(ShotRevision).where(
                    ShotRevision.episode_id == episode_id,
                    ShotRevision.is_current.is_(True),
                )
            )
        else:
            current_revision = session.get(ShotRevision, current_shot_revision_id)
            if current_revision is not None and (
                current_revision.episode_id != episode_id or not current_revision.is_current
            ):
                current_revision = None

        if current_revision is None:
            raise BreakdownRunLifecycleError("Episode 当前没有可用的 Current ShotRevision")

        changed = mark_episode_breakdown_runs_stale_in_session(
            session,
            episode_id,
            current_shot_revision_id=current_revision.id,
        )
        session.commit()
        return changed
