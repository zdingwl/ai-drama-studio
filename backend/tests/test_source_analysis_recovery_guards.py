from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.projects.enums import ProjectType
from app.source_analysis import service as source_analysis_service
from app.source_analysis.schemas import SourceAnalysisState
from app.workflow.models import TaskStatus


def _project(project_type: ProjectType) -> SimpleNamespace:
    return SimpleNamespace(project_type=project_type)


def test_source_analysis_service_rejects_translation_before_pipeline_access(monkeypatch) -> None:
    monkeypatch.setattr(
        source_analysis_service,
        "get_project",
        lambda db, project_id: _project(ProjectType.TRANSLATION),
    )

    with pytest.raises(AppError) as status_error:
        source_analysis_service.get_source_analysis_status(SimpleNamespace(), "translation-project")
    assert status_error.value.code == "SOURCE_ANALYSIS_NOT_ALLOWED"

    with pytest.raises(AppError) as create_error:
        source_analysis_service.create_source_analysis_task(
            SimpleNamespace(),
            project_id="translation-project",
            idempotency_key="translation-must-not-enter-source-bible-flow",
        )
    assert create_error.value.code == "SOURCE_ANALYSIS_NOT_ALLOWED"


def test_interrupted_pipeline_is_exposed_as_retryable_failure(monkeypatch) -> None:
    interrupted = SimpleNamespace(
        id="pipeline-1",
        status=TaskStatus.INTERRUPTED,
        progress_percent=68,
        attempt=1,
        max_attempts=3,
        checkpoint_json={"stage": "shot_breakdown", "stage_label": "正在整理逐镜动作和镜头语言"},
        last_error=None,
    )
    monkeypatch.setattr(
        source_analysis_service,
        "get_project",
        lambda db, project_id: _project(ProjectType.REPLICA),
    )
    monkeypatch.setattr(
        source_analysis_service,
        "_latest_pipeline_task",
        lambda db, project_id: interrupted,
    )
    monkeypatch.setattr(
        source_analysis_service,
        "get_source_video_snapshot",
        lambda db, project_id: SimpleNamespace(status="NOT_BUILT"),
    )

    result = source_analysis_service.get_source_analysis_status(SimpleNamespace(), "replica-project")

    assert result.state == SourceAnalysisState.FAILED
    assert result.task_id == "pipeline-1"
    assert result.progress_percent == 68
    assert result.can_retry is True
    assert result.current_stage == "正在整理逐镜动作和镜头语言"
    assert result.message == "原片解析已中断，请重新解析继续。"


def test_interrupted_pipeline_at_attempt_limit_is_not_retryable(monkeypatch) -> None:
    interrupted = SimpleNamespace(
        id="pipeline-2",
        status=TaskStatus.INTERRUPTED,
        progress_percent=84,
        attempt=3,
        max_attempts=3,
        checkpoint_json={},
        last_error="worker heartbeat expired",
    )
    monkeypatch.setattr(
        source_analysis_service,
        "get_project",
        lambda db, project_id: _project(ProjectType.REDRAW),
    )
    monkeypatch.setattr(
        source_analysis_service,
        "_latest_pipeline_task",
        lambda db, project_id: interrupted,
    )
    monkeypatch.setattr(
        source_analysis_service,
        "get_source_video_snapshot",
        lambda db, project_id: SimpleNamespace(status="STALE"),
    )

    result = source_analysis_service.get_source_analysis_status(SimpleNamespace(), "redraw-project")

    assert result.state == SourceAnalysisState.FAILED
    assert result.can_retry is False
    assert result.current_stage == "解析已中断"
    assert result.message == "worker heartbeat expired"
