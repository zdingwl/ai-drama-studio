from types import SimpleNamespace

import pytest

from engine.app import breakdown_p2_pipeline_v1 as pipeline


class FakeProvider:
    def __init__(self, component: str) -> None:
        self.component = component
        self.episode_intelligence = None

    def set_episode_intelligence_artifact(self, path: str, fingerprint: str) -> None:
        self.episode_intelligence = (path, fingerprint)


def execution(component: str, status: str = "READY") -> pipeline.ProviderExecution:
    return pipeline.ProviderExecution(
        component=component,
        status=status,
        provider=f"fake-{component.lower()}",
        model="fake-model",
        artifact=SimpleNamespace(component=component, path=f"/{component.lower()}.json"),
        elapsed_seconds=0.01,
        warnings=(),
    )


def episode_execution(status: str = "READY") -> pipeline.EpisodeIntelligenceExecution:
    artifact = None
    if status == "READY":
        artifact = SimpleNamespace(
            path="/episode-intelligence.json",
            fingerprint="e" * 64,
            input_fingerprint="i" * 64,
        )
    return pipeline.EpisodeIntelligenceExecution(
        status=status,
        provider="fake-gemini",
        model="gemini-3.1-pro-preview",
        artifact=artifact,
        elapsed_seconds=0.02,
        warnings=(),
    )


def prepare(monkeypatch):
    monkeypatch.setattr(
        pipeline.p2,
        "load_p2_run_context",
        lambda run_id: SimpleNamespace(
            run_id=run_id,
            project_id="PROJECT_1",
            episode_id="EPISODE_1",
            source_shot_revision_id="REV_1",
        ),
    )
    monkeypatch.setattr(pipeline, "_pipeline_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pipeline,
        "_execute_episode_intelligence",
        lambda run_id, provider, artifacts: episode_execution(),
    )
    from engine.app import source_presence_audit_v1 as audit

    monkeypatch.setattr(audit, "inspect_artifact", lambda context, artifact: [])
    monkeypatch.setattr(audit, "publish", lambda *args: None)


def test_pipeline_runs_asr_ocr_whole_episode_then_vlm_and_fusion(monkeypatch) -> None:
    prepare(monkeypatch)
    calls = []
    progress = []
    vlm = FakeProvider("VLM")

    def fake_execute(run_id, provider):
        calls.append(provider.component)
        return execution(provider.component)

    def fake_episode(run_id, provider, artifacts):
        calls.append("EPISODE_INTELLIGENCE")
        assert [item.component for item in artifacts] == ["ASR", "OCR"]
        return episode_execution()

    monkeypatch.setattr(pipeline, "_execute_provider", fake_execute)
    monkeypatch.setattr(pipeline, "_execute_episode_intelligence", fake_episode)
    monkeypatch.setattr(
        pipeline.fusion,
        "fuse_breakdown_run",
        lambda run_id: calls.append("FUSION") or SimpleNamespace(id=run_id, status="READY"),
    )

    result = pipeline.run_breakdown_p2_run(
        "RUN_1",
        providers=(vlm, FakeProvider("OCR"), FakeProvider("ASR")),
        progress=lambda percent, stage, message: progress.append((percent, stage)),
    )

    assert result.status == "READY"
    assert calls == ["ASR", "OCR", "EPISODE_INTELLIGENCE", "VLM", "FUSION"]
    assert vlm.episode_intelligence == ("/episode-intelligence.json", "e" * 64)
    assert progress[0] == (0.0, "breakdown_prepare")
    assert (35.0, "breakdown_episode_intelligence") in progress
    assert (60.0, "breakdown_vlm") in progress
    assert progress[-1] == (100.0, "breakdown_ready")


@pytest.mark.parametrize("component,status", [("ASR", "NO_EVIDENCE"), ("OCR", "NOT_AVAILABLE")])
def test_asr_ocr_degraded_statuses_still_reach_episode_intelligence(monkeypatch, component: str, status: str) -> None:
    prepare(monkeypatch)
    calls = []

    def fake_execute(run_id, provider):
        calls.append(provider.component)
        return execution(provider.component, status if provider.component == component else "READY")

    def fake_episode(run_id, provider, artifacts):
        calls.append("EPISODE_INTELLIGENCE")
        return episode_execution()

    monkeypatch.setattr(pipeline, "_execute_provider", fake_execute)
    monkeypatch.setattr(pipeline, "_execute_episode_intelligence", fake_episode)
    monkeypatch.setattr(
        pipeline.fusion,
        "fuse_breakdown_run",
        lambda run_id: calls.append("FUSION") or SimpleNamespace(id=run_id, status="READY_WITH_WARNINGS"),
    )

    result = pipeline.run_breakdown_p2_run(
        "RUN_2",
        providers=(FakeProvider("ASR"), FakeProvider("OCR"), FakeProvider("VLM")),
    )

    assert result.status == "READY_WITH_WARNINGS"
    assert calls == ["ASR", "OCR", "EPISODE_INTELLIGENCE", "VLM", "FUSION"]


def test_episode_intelligence_not_ready_blocks_vlm(monkeypatch) -> None:
    prepare(monkeypatch)
    calls = []
    failed = []

    def fake_execute(run_id, provider):
        calls.append(provider.component)
        return execution(provider.component)

    monkeypatch.setattr(pipeline, "_execute_provider", fake_execute)
    monkeypatch.setattr(
        pipeline,
        "_execute_episode_intelligence",
        lambda run_id, provider, artifacts: episode_execution("NOT_CONFIGURED"),
    )
    monkeypatch.setattr(
        pipeline,
        "_safe_fail_processing",
        lambda run_id, exc, executions, episode: failed.append((run_id, type(exc).__name__)),
    )
    monkeypatch.setattr(pipeline.fusion, "fuse_breakdown_run", lambda run_id: pytest.fail("fusion must not run"))

    with pytest.raises(pipeline.BreakdownP2PipelineError, match="Gemini 整片理解未配置"):
        pipeline.run_breakdown_p2_run(
            "RUN_GEMINI_MISSING",
            providers=(FakeProvider("ASR"), FakeProvider("OCR"), FakeProvider("VLM")),
        )

    assert calls == ["ASR", "OCR"]
    assert failed == [("RUN_GEMINI_MISSING", "BreakdownP2PipelineError")]


def test_vlm_not_ready_fails_closed_before_fusion(monkeypatch) -> None:
    prepare(monkeypatch)
    calls = []
    failed = []

    def fake_execute(run_id, provider):
        calls.append(provider.component)
        status = "NOT_AVAILABLE" if provider.component == "VLM" else "READY"
        return execution(provider.component, status)

    monkeypatch.setattr(pipeline, "_execute_provider", fake_execute)
    monkeypatch.setattr(
        pipeline,
        "_safe_fail_processing",
        lambda run_id, exc, executions, episode: failed.append((run_id, type(exc).__name__)),
    )
    monkeypatch.setattr(pipeline.fusion, "fuse_breakdown_run", lambda run_id: pytest.fail("fusion must not run"))

    with pytest.raises(pipeline.BreakdownP2PipelineError, match="VLM Provider status=NOT_AVAILABLE"):
        pipeline.run_breakdown_p2_run(
            "RUN_3",
            providers=(FakeProvider("ASR"), FakeProvider("OCR"), FakeProvider("VLM")),
        )

    assert calls == ["ASR", "OCR", "VLM"]
    assert failed == [("RUN_3", "BreakdownP2PipelineError")]


def test_provider_exception_closes_processing_run(monkeypatch) -> None:
    prepare(monkeypatch)
    failed = []

    def fake_execute(run_id, provider):
        if provider.component == "OCR":
            raise RuntimeError("ocr exploded")
        return execution(provider.component)

    monkeypatch.setattr(pipeline, "_execute_provider", fake_execute)
    monkeypatch.setattr(
        pipeline,
        "_safe_fail_processing",
        lambda run_id, exc, executions, episode: failed.append((run_id, str(exc), len(executions))),
    )

    with pytest.raises(RuntimeError, match="ocr exploded"):
        pipeline.run_breakdown_p2_run(
            "RUN_4",
            providers=(FakeProvider("ASR"), FakeProvider("OCR"), FakeProvider("VLM")),
        )

    assert failed == [("RUN_4", "ocr exploded", 1)]


def test_episode_entry_creates_frozen_run_with_whole_episode_first_profile(monkeypatch) -> None:
    created = {}
    run = SimpleNamespace(id="RUN_NEW")

    def fake_create(episode_id, **kwargs):
        created["episode_id"] = episode_id
        created.update(kwargs)
        return run

    monkeypatch.setattr(pipeline.breakdown_service_v1, "create_breakdown_run", fake_create)
    monkeypatch.setattr(
        pipeline,
        "run_breakdown_p2_run",
        lambda run_id, **kwargs: SimpleNamespace(id=run_id, status="READY"),
    )

    result = pipeline.run_episode_breakdown_p2(
        "EP_1",
        providers=(FakeProvider("ASR"), FakeProvider("OCR"), FakeProvider("VLM")),
    )

    assert result.id == "RUN_NEW"
    assert created["episode_id"] == "EP_1"
    assert created["pipeline_profile"] == pipeline.P2_PIPELINE_PROFILE
    assert created["component_status"]["P2_PIPELINE"]["provider_order"] == [
        "ASR",
        "OCR",
        "EPISODE_INTELLIGENCE",
        "VLM",
    ]
