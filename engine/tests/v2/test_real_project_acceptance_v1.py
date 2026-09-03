from __future__ import annotations

import sys

import scripts.run_real_project_acceptance_v1 as acceptance_runner
from scripts.run_real_project_acceptance_v1 import (
    AcceptanceError,
    acceptance_result,
    runtime_blockers,
    run_pipeline,
    summarize_state,
)


def _state(*, issues=None, segments=2, selected=2, post_succeeded=2, outputs_succeeded=1):
    return {
        "project": {"id": "PROJECT_1", "name": "Acceptance", "episodes": [{"id": "EP_1"}]},
        "review_issues": list(issues or []),
        "source_drama_snapshot": {
            "source_dialogue_count": 2,
            "source_dialogue_projection_count": 3,
        },
        "target_dialogue": {
            "dialogue_count": 2,
            "audio_ready_count": 2,
        },
        "flow_state": {
            "stages": [{
                "stage_key": "target_dialogue",
                "validity": "CURRENT",
                "metrics": {"dialogue_count": 2},
            }],
        },
        "generation_segments": {
            "segment_count": segments,
            "review_count": 0,
            "waiting_audio_count": 0,
        },
        "h3_quality": {
            "selected_count": selected,
            "review_count": 0,
            "waiting_model_count": 0,
        },
        "postproduction": {
            "segment_count": segments,
            "succeeded_count": post_succeeded,
            "review_count": 0,
            "waiting_count": 0,
            "episodes": [{
                "segments": [
                    {"audio_mix_mode": "SOURCE_BACKGROUND_SAFE"}
                    for _ in range(post_succeeded)
                ]
            }],
        },
        "outputs": {
            "episode_count": 1,
            "succeeded_count": outputs_succeeded,
            "waiting_count": 0,
        },
    }


def test_acceptance_requires_full_selected_postproduction_and_episode_output_coverage() -> None:
    assert acceptance_result(summarize_state(_state())) == "READY_FOR_MANUAL_ACCEPTANCE"
    assert acceptance_result(summarize_state(_state(selected=1))) == "NOT_READY"
    assert acceptance_result(summarize_state(_state(post_succeeded=1))) == "NOT_READY"
    assert acceptance_result(summarize_state(_state(outputs_succeeded=0))) == "NOT_READY"


def test_acceptance_requires_one_current_target_dialogue_per_complete_source_utterance() -> None:
    state = _state()
    summary = summarize_state(state)
    assert summary["source_dialogue_count"] == 2
    assert summary["source_dialogue_projection_count"] == 3
    assert summary["target_dialogue_count"] == 2
    assert summary["flow_target_dialogue_count"] == 2
    assert summary["dialogue_contract_current"] is True
    assert summary["flow_target_dialogue_count_current"] is True

    state["target_dialogue"]["dialogue_count"] = 3
    state["target_dialogue"]["audio_ready_count"] = 3
    summary = summarize_state(state)
    assert summary["dialogue_contract_current"] is False
    assert acceptance_result(summary) == "NOT_READY"


def test_acceptance_reads_formal_flowstate_stage_key_and_keeps_legacy_key_compatibility() -> None:
    state = _state()
    assert summarize_state(state)["flow_target_dialogue_count_current"] is True

    stage = state["flow_state"]["stages"][0]
    stage["key"] = stage.pop("stage_key")
    summary = summarize_state(state)
    assert summary["flow_target_dialogue_count"] == 2
    assert summary["flow_target_dialogue_count_current"] is True


def test_acceptance_rejects_flowstate_target_dialogue_history_leak() -> None:
    state = _state()
    state["flow_state"]["stages"][0]["metrics"]["dialogue_count"] = 3
    summary = summarize_state(state)
    assert summary["target_dialogue_count"] == 2
    assert summary["flow_target_dialogue_count"] == 3
    assert summary["dialogue_contract_current"] is True
    assert summary["flow_target_dialogue_count_current"] is False
    assert acceptance_result(summary) == "NOT_READY"


def test_acceptance_rejects_target_dialogue_audio_that_is_not_fully_current() -> None:
    state = _state()
    state["target_dialogue"]["audio_ready_count"] = 1
    summary = summarize_state(state)
    assert summary["target_dialogue_audio_current"] is False
    assert acceptance_result(summary) == "NOT_READY"


def test_real_review_issue_has_priority_over_other_ready_counts() -> None:
    summary = summarize_state(_state(issues=[{"issue_type": "H3_QC"}]))
    assert summary["review_types"] == ["H3_QC"]
    assert acceptance_result(summary) == "NEEDS_REVIEW"


def test_runtime_blockers_require_the_complete_local_acceptance_stack() -> None:
    ready = {
        key: {"ready": True}
        for key in (
            "backend",
            "h3_fl2va",
            "h3_ref2va",
            "qwen3_vl",
            "qwen3_tts",
            "latentsync",
            "audio_separator",
        )
    }
    assert runtime_blockers(ready) == []
    ready["audio_separator"] = {"ready": False}
    assert runtime_blockers(ready) == ["audio_separator"]


def test_main_run_mode_defers_downstream_runtime_blockers_to_the_production_stage(monkeypatch) -> None:
    client = object()
    runtimes = {
        "backend": {"ready": True},
        "h3_fl2va": {"ready": False},
        "h3_ref2va": {"ready": False},
        "qwen3_vl": {"ready": True},
        "qwen3_tts": {"ready": True},
        "latentsync": {"ready": False},
        "audio_separator": {"ready": False},
    }
    state = _state(issues=[{"issue_type": "CHARACTER_IDENTITY", "severity": "BLOCKING"}])
    calls: list[str] = []

    monkeypatch.setattr(acceptance_runner, "HttpClient", lambda _base_url: client)
    monkeypatch.setattr(
        acceptance_runner,
        "collect_runtime_status",
        lambda _client, *, vlm_base_url, vlm_model: runtimes,
    )
    monkeypatch.setattr(acceptance_runner, "collect_project_state", lambda _client, _project_id: state)

    def fake_run_pipeline(_client, project_id, *, poll_seconds, timeout_seconds):
        calls.append(project_id)
        return "NEEDS_REVIEW", state

    monkeypatch.setattr(acceptance_runner, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_real_project_acceptance_v1.py", "--project-id", "PROJECT_1", "--run", "--json"],
    )

    assert acceptance_runner.main() == 2
    assert calls == ["PROJECT_1"]


class _StageClient:
    def __init__(self, stage: str, *, review: bool = False, review_after_prepare: bool = False) -> None:
        self.stage = stage
        self.review = review
        self.review_after_prepare = review_after_prepare
        self.posts: list[str] = []

    def post(self, path: str, payload=None):
        self.posts.append(path)
        if path.endswith("/tasks/auto-remake-prepare"):
            self.stage = "segments"
            if self.review_after_prepare:
                self.review = True
        elif path.endswith("/tasks/h3-generate-ready"):
            self.stage = "selected"
        elif path.endswith("/tasks/postproduction"):
            self.stage = "complete"
        else:
            raise AssertionError(path)
        return {"id": f"TASK_{len(self.posts)}"}

    def get(self, path: str):
        if path.startswith("/api/tasks/"):
            return {"id": path.rsplit("/", 1)[-1], "status": "READY", "message": "done"}
        if path == "/api/projects/PROJECT_1/review-issues?status=OPEN":
            return [{"issue_type": "DIALOGUE_TIMING", "severity": "BLOCKING"}] if self.review else []
        if path == "/api/projects/PROJECT_1":
            return {"id": "PROJECT_1", "name": "Acceptance", "episodes": [{"id": "EP_1"}]}
        if path == "/api/projects/PROJECT_1/source-drama-snapshot":
            if self.stage == "unprepared":
                raise AcceptanceError("SourceDramaSnapshot unavailable")
            return {"source_dialogue_count": 2, "source_dialogue_projection_count": 3}
        if path == "/api/projects/PROJECT_1/target-dialogue":
            if self.stage == "unprepared":
                raise AcceptanceError("TargetDialogue unavailable")
            return {"dialogue_count": 2, "audio_ready_count": 2}
        if path == "/api/projects/PROJECT_1/flow-state":
            count = 0 if self.stage == "unprepared" else 2
            return {
                "stages": [{
                    "stage_key": "target_dialogue",
                    "validity": "CURRENT",
                    "metrics": {"dialogue_count": count},
                }],
            }
        if path == "/api/projects/PROJECT_1/generation-segments":
            if self.stage == "unprepared":
                raise AcceptanceError("GenerationSegment unavailable")
            return {"segment_count": 2, "review_count": 0, "waiting_audio_count": 0}
        if path == "/api/projects/PROJECT_1/h3-quality":
            selected = 2 if self.stage in {"selected", "complete"} else 0
            return {"selected_count": selected, "review_count": 0, "waiting_model_count": 0}
        if path == "/api/projects/PROJECT_1/postproduction":
            succeeded = 2 if self.stage == "complete" else 0
            return {
                "segment_count": 2,
                "succeeded_count": succeeded,
                "review_count": 0,
                "waiting_count": 0 if succeeded else 2,
                "episodes": [{"segments": [{"audio_mix_mode": "SOURCE_BACKGROUND_SAFE"}] * succeeded}],
            }
        if path == "/api/projects/PROJECT_1/outputs":
            succeeded = 1 if self.stage == "complete" else 0
            return {"episode_count": 1, "succeeded_count": succeeded, "waiting_count": 0 if succeeded else 1}
        raise AssertionError(path)


def _run(client: _StageClient):
    return run_pipeline(client, "PROJECT_1", poll_seconds=0.001, timeout_seconds=1.0)


def test_run_pipeline_stops_immediately_when_review_center_is_already_open() -> None:
    client = _StageClient("segments", review=True)
    result, state = _run(client)
    assert result == "NEEDS_REVIEW"
    assert client.posts == []
    assert summarize_state(state)["open_review_count"] == 1


def test_run_pipeline_stops_after_prepare_when_prepare_creates_review_issue() -> None:
    client = _StageClient("unprepared", review_after_prepare=True)
    result, state = _run(client)
    assert result == "NEEDS_REVIEW"
    assert client.posts == ["/api/projects/PROJECT_1/tasks/auto-remake-prepare"]
    assert summarize_state(state)["open_review_count"] == 1


def test_run_pipeline_resumes_at_h3_when_generation_segments_are_already_current() -> None:
    client = _StageClient("segments")
    result, _state_after = _run(client)
    assert result == "READY_FOR_MANUAL_ACCEPTANCE"
    assert client.posts == [
        "/api/projects/PROJECT_1/tasks/h3-generate-ready",
        "/api/projects/PROJECT_1/tasks/postproduction",
    ]


def test_run_pipeline_resumes_at_postproduction_when_selected_outputs_already_exist() -> None:
    client = _StageClient("selected")
    result, _state_after = _run(client)
    assert result == "READY_FOR_MANUAL_ACCEPTANCE"
    assert client.posts == ["/api/projects/PROJECT_1/tasks/postproduction"]


def test_run_pipeline_does_nothing_when_project_is_already_ready_for_manual_acceptance() -> None:
    client = _StageClient("complete")
    result, _state_after = _run(client)
    assert result == "READY_FOR_MANUAL_ACCEPTANCE"
    assert client.posts == []
