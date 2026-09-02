from __future__ import annotations

from scripts.run_real_project_acceptance_v1 import (
    acceptance_result,
    runtime_blockers,
    run_pipeline,
    summarize_state,
)


def _state(*, issues=None, segments=2, selected=2, post_succeeded=2, outputs_succeeded=1):
    return {
        "project": {"id": "PROJECT_1", "name": "Acceptance", "episodes": [{"id": "EP_1"}]},
        "review_issues": list(issues or []),
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


class _FakeClient:
    def __init__(self) -> None:
        self.posts: list[str] = []
        self.review_calls = 0

    def post(self, path: str, payload=None):
        self.posts.append(path)
        return {"id": f"TASK_{len(self.posts)}"}

    def get(self, path: str):
        if path.startswith("/api/tasks/"):
            return {"id": path.rsplit("/", 1)[-1], "status": "READY", "message": "done"}
        if path == "/api/projects/PROJECT_1/review-issues?status=OPEN":
            self.review_calls += 1
            # First call is the post-prepare gate. A real issue must stop H3 immediately.
            return [{"issue_type": "DIALOGUE_TIMING", "severity": "BLOCKING"}]
        if path == "/api/projects/PROJECT_1":
            return {"id": "PROJECT_1", "name": "Acceptance", "episodes": [{"id": "EP_1"}]}
        if path == "/api/projects/PROJECT_1/generation-segments":
            return {"segment_count": 2, "review_count": 0, "waiting_audio_count": 0}
        if path == "/api/projects/PROJECT_1/h3-quality":
            return {"selected_count": 0, "review_count": 0, "waiting_model_count": 0}
        if path == "/api/projects/PROJECT_1/postproduction":
            return {"segment_count": 2, "succeeded_count": 0, "review_count": 0, "waiting_count": 2, "episodes": []}
        if path == "/api/projects/PROJECT_1/outputs":
            return {"episode_count": 1, "succeeded_count": 0, "waiting_count": 1}
        raise AssertionError(path)


def test_run_pipeline_stops_at_review_center_instead_of_launching_h3() -> None:
    client = _FakeClient()
    result, state = run_pipeline(client, "PROJECT_1", poll_seconds=0.001, timeout_seconds=1.0)
    assert result == "NEEDS_REVIEW"
    assert client.posts == ["/api/projects/PROJECT_1/tasks/auto-remake-prepare"]
    assert summarize_state(state)["open_review_count"] == 1
