from __future__ import annotations

import pytest

from engine.app import target_localization_runtime_guard_v1 as guard


def _snapshot(*, characters: bool = True, scenes: bool = True) -> dict:
    return {
        "characters": [{"id": "CHAR_1", "name": "林晚"}] if characters else [],
        "episodes": [{"scenes": [{"scene_key": "S1"}] if scenes else []}],
    }


def test_required_model_unavailable_fails_as_runtime_state(monkeypatch) -> None:
    cleaned: list[str] = []
    monkeypatch.setattr(guard, "load_project_source_drama_snapshot_v1", lambda _project_id: _snapshot())
    monkeypatch.setattr(guard, "get_project_remake_policy", lambda _project_id: {"scene_policy": "AUTO"})
    monkeypatch.setattr(
        guard,
        "local_qwen_text_runtime_status",
        lambda: {"ready": False, "missing": ["checkpoint"]},
    )
    monkeypatch.setattr(
        guard,
        "cleanup_automatic_localization_placeholders_v1",
        lambda project_id: cleaned.append(project_id) or 0,
    )

    with pytest.raises(guard.TargetLocalizationRuntimeUnavailable, match="不需要额外启动 8001"):
        guard.require_target_localization_runtime_v1("PROJECT_1")

    assert cleaned == ["PROJECT_1"]


def test_breakdown_local_qwen_runtime_is_accepted_without_http_service(monkeypatch) -> None:
    monkeypatch.setattr(guard, "load_project_source_drama_snapshot_v1", lambda _project_id: _snapshot())
    monkeypatch.setattr(guard, "get_project_remake_policy", lambda _project_id: {"scene_policy": "AUTO"})
    monkeypatch.setattr(
        guard,
        "local_qwen_text_runtime_status",
        lambda: {
            "ready": True,
            "provider": "qwen3-vl-local-subprocess",
            "http_configured": False,
            "local_ready": True,
        },
    )

    status = guard.require_target_localization_runtime_v1("PROJECT_1")

    assert status["ready"] is True
    assert status["provider"] == "qwen3-vl-local-subprocess"
    assert status["http_configured"] is False


def test_model_is_not_required_for_empty_keep_project(monkeypatch) -> None:
    monkeypatch.setattr(
        guard,
        "load_project_source_drama_snapshot_v1",
        lambda _project_id: _snapshot(characters=False, scenes=True),
    )
    monkeypatch.setattr(guard, "get_project_remake_policy", lambda _project_id: {"scene_policy": "KEEP"})
    monkeypatch.setattr(
        guard,
        "local_qwen_text_runtime_status",
        lambda: {"ready": False, "provider": None, "local_ready": False},
    )

    status = guard.require_target_localization_runtime_v1("PROJECT_1")

    assert status["ready"] is False


def test_blank_target_character_is_runtime_failure_not_human_review(monkeypatch) -> None:
    cleaned: list[str] = []
    monkeypatch.setattr(
        guard,
        "cleanup_automatic_localization_placeholders_v1",
        lambda project_id: cleaned.append(project_id) or 1,
    )
    bundle = {
        "target_characters": [{
            "id": "TARGET_1",
            "status": "REVIEW",
            "decision_source": "AI",
            "target_name": "待确认目标角色",
            "appearance_profile": "等待本地模型或人工确认目标人物设定",
            "generation_prompt": "等待目标人物设定完成后生成稳定人物参考",
        }],
        "scene_mappings": [],
    }

    with pytest.raises(guard.TargetLocalizationRuntimeUnavailable):
        guard.validate_target_localization_generation_v1("PROJECT_1", bundle)

    assert cleaned == ["PROJECT_1"]


def test_low_confidence_real_character_proposal_is_not_placeholder(monkeypatch) -> None:
    class _Scalars:
        def all(self):
            return []

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def scalars(self, _query):
            return _Scalars()

    monkeypatch.setattr(guard, "get_session", lambda: _Session())
    bundle = {
        "target_characters": [{
            "id": "TARGET_1",
            "status": "REVIEW",
            "decision_source": "AI",
            "target_name": "Emma Miller",
            "appearance_profile": "美国本地年轻职业女性，棕色长发，沉稳",
            "generation_prompt": "consistent American woman, professional, long brown hair",
        }],
        "scene_mappings": [],
    }

    assert guard.validate_target_localization_generation_v1("PROJECT_1", bundle) == bundle
