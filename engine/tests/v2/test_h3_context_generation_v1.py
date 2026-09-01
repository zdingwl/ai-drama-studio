from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import generation_attempt_v1, review_issue_v1, studio_v2
from engine.app.h3_context_contract_v1 import H3CompiledContextV1
from engine.app.h3_reference_assets_v1 import target_character_reference_signature_v1
from engine.app.video_generation_provider_v1 import (
    VideoGenerationJobStatusV1,
    VideoGenerationRequestV1,
    VideoGenerationSubmissionV1,
)


def use_temp_database(monkeypatch, tmp_path: Path) -> str:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")
    project = studio_v2.create_project(
        name="R8",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )
    return project["id"]


def ready_request() -> dict:
    return VideoGenerationRequestV1.model_validate({
        "provider": "MINIMAX_H3_LOCAL",
        "mode": "REF2VA",
        "prompt": "subject_definitions: test",
        "conditions": [
            {"type": "video", "uri": "file:///tmp/ref.mp4", "role": "source_directing_reference"},
        ],
        "duration_seconds": 5,
    }).model_dump(mode="json")


def test_h3_context_ready_requires_request_matching_materialized_conditions(tmp_path: Path) -> None:
    ref = tmp_path / "ref.mp4"
    ref.write_bytes(b"video")
    payload = {
        "schema_version": "h3-context-v1",
        "project_id": "PROJECT_X",
        "episode_id": "EPISODE_X",
        "segment_id": "GENSEG_X",
        "segment_input_fingerprint": "a" * 64,
        "context_fingerprint": "b" * 64,
        "status": "READY",
        "reason": "ready",
        "provider": "MINIMAX_H3_LOCAL",
        "mode": "REF2VA",
        "prompt": "subject_definitions: test",
        "conditions": [{
            "type": "video",
            "role": "source_directing_reference",
            "label": "<Video 1>",
            "uri": ref.resolve().as_uri(),
            "local_path": str(ref.resolve()),
            "sha256": "c" * 64,
            "source": "source-reference-video",
        }],
        "request": {
            **ready_request(),
            "conditions": [{
                "type": "video",
                "uri": ref.resolve().as_uri(),
                "role": "source_directing_reference",
            }],
        },
        "workspace_dir": str(tmp_path),
        "created_at": "2026-09-01T00:00:00+00:00",
    }
    assert H3CompiledContextV1.model_validate(payload).status == "READY"
    broken = {**payload, "request": None}
    with pytest.raises(ValueError):
        H3CompiledContextV1.model_validate(broken)


def test_target_character_reference_signature_changes_with_identity_definition() -> None:
    base = {
        "id": "TARGETCHAR_1",
        "project_id": "PROJECT_1",
        "target_language": "en-US",
        "target_region": "US",
        "target_name": "Emma Miller",
        "appearance_profile": "young American woman, long dark hair",
        "generation_prompt": "stable fictional heroine identity",
    }
    first = target_character_reference_signature_v1(base)
    second = target_character_reference_signature_v1({**base, "target_name": "Claire Miller"})
    third = target_character_reference_signature_v1({**base, "appearance_profile": "young American woman, short auburn hair"})
    assert len(first) == 64
    assert first != second
    assert first != third


def test_domain_review_issue_cannot_be_closed_without_domain_edit(monkeypatch, tmp_path: Path) -> None:
    project_id = use_temp_database(monkeypatch, tmp_path)
    issue = review_issue_v1.upsert_review_issue(
        project_id=project_id,
        source_key="auto:dialogue-timing:test",
        issue_type="DIALOGUE_TIMING",
        reason="目标对白显著超时",
        severity="BLOCKING",
    )
    with pytest.raises(ValueError):
        review_issue_v1.set_review_issue_status(issue["id"], status="RESOLVED")
    with pytest.raises(ValueError):
        review_issue_v1.set_review_issue_status(issue["id"], status="IGNORED")
    assert review_issue_v1.list_review_issues(project_id)[0]["status"] == "OPEN"


class FakeSuccessProvider:
    key = "MINIMAX_H3_LOCAL"

    def __init__(self) -> None:
        self.submit_count = 0

    def status(self) -> dict:
        return {"ready": True}

    def submit(self, request):
        self.submit_count += 1
        return VideoGenerationSubmissionV1(
            provider="MINIMAX_H3_LOCAL",
            mode=request.mode,
            external_job_id="job_1",
            provider_status="queued",
        )

    def get_status(self, *, mode: str, external_job_id: str):
        return VideoGenerationJobStatusV1(
            provider="MINIMAX_H3_LOCAL",
            mode=mode,
            external_job_id=external_job_id,
            provider_status="completed",
            terminal=True,
            succeeded=True,
            failed=False,
        )

    def download(self, *, mode: str, external_job_id: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-h3-output")
        return destination


class FakeSubmitFailureProvider(FakeSuccessProvider):
    def submit(self, request):
        raise RuntimeError("runtime unavailable before submit")


def fake_segment(project_id: str) -> dict:
    return {
        "id": "GENSEG_1",
        "project_id": project_id,
        "episode_id": "EPISODE_FAKE",
        "status": "READY",
        "reason": "ready",
        "input_fingerprint": "1" * 64,
    }


def fake_context(project_id: str) -> dict:
    return {
        "schema_version": "h3-context-v1",
        "project_id": project_id,
        "episode_id": "EPISODE_FAKE",
        "segment_id": "GENSEG_1",
        "segment_input_fingerprint": "1" * 64,
        "context_fingerprint": "2" * 64,
        "status": "READY",
        "reason": "ready",
        "provider": "MINIMAX_H3_LOCAL",
        "mode": "REF2VA",
        "prompt": "subject_definitions: test",
        "conditions": [],
        "request": ready_request(),
        "workspace_dir": "/tmp/context",
        "created_at": "2026-09-01T00:00:00+00:00",
    }


def test_generation_attempt_submit_poll_download_and_reuse(monkeypatch, tmp_path: Path) -> None:
    project_id = use_temp_database(monkeypatch, tmp_path)
    monkeypatch.setattr(generation_attempt_v1, "_current_segment", lambda project_id_arg, segment_id: fake_segment(project_id_arg))
    monkeypatch.setattr(generation_attempt_v1, "compile_h3_context_v1", lambda project_id_arg, segment_id: fake_context(project_id_arg))
    provider = FakeSuccessProvider()

    first = generation_attempt_v1.execute_generation_segment_v1(
        project_id,
        "GENSEG_1",
        provider=provider,
        poll_interval_seconds=0.01,
        timeout_seconds=30,
    )
    assert first["status"] == "SUCCEEDED"
    assert Path(first["output_path"]).read_bytes() == b"fake-h3-output"
    assert provider.submit_count == 1

    second = generation_attempt_v1.execute_generation_segment_v1(
        project_id,
        "GENSEG_1",
        provider=provider,
        poll_interval_seconds=0.01,
        timeout_seconds=30,
    )
    assert second["id"] == first["id"]
    assert provider.submit_count == 1


def test_generation_attempt_records_pre_submit_failure_without_external_job(monkeypatch, tmp_path: Path) -> None:
    project_id = use_temp_database(monkeypatch, tmp_path)
    monkeypatch.setattr(generation_attempt_v1, "_current_segment", lambda project_id_arg, segment_id: fake_segment(project_id_arg))
    monkeypatch.setattr(generation_attempt_v1, "compile_h3_context_v1", lambda project_id_arg, segment_id: fake_context(project_id_arg))

    with pytest.raises(generation_attempt_v1.GenerationAttemptError):
        generation_attempt_v1.execute_generation_segment_v1(
            project_id,
            "GENSEG_1",
            provider=FakeSubmitFailureProvider(),
            timeout_seconds=30,
        )

    with studio_v2.get_session() as session:
        rows = list(session.query(generation_attempt_v1.GenerationAttempt).all())
    assert len(rows) == 1
    assert rows[0].status == "FAILED"
    assert rows[0].external_job_id is None
