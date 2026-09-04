from __future__ import annotations

from sqlalchemy import select

from engine.app import target_character_auto_design_v1 as auto
from engine.app import target_localization_v1
from engine.tests.v2.test_target_localization_v1 import _seed


def _prepare(monkeypatch, tmp_path):
    project_id, _episode_id, factory, snapshot = _seed(monkeypatch, tmp_path)
    monkeypatch.setattr(auto, "get_session", lambda: factory())
    monkeypatch.setattr(auto, "inventory", lambda _project_id: {"revision": "REV_1"})
    monkeypatch.setattr(auto, "load_project_source_drama_snapshot_v1", lambda _project_id: snapshot)
    monkeypatch.setattr(
        auto,
        "local_qwen_text_runtime_status",
        lambda: {"ready": True, "provider": "qwen3-vl-local-subprocess"},
    )
    return project_id, factory, snapshot


def _proposal(name: str = "Emma Miller", confidence: float = 0.93):
    return {
        "characters": [{
            "source_character_id": "CHAR_1",
            "target_name": name,
            "appearance_profile": "25岁左右的美国女性，职业气质，棕色长发",
            "generation_prompt": "consistent American woman, mid-20s, professional, long brown hair",
            "confidence": confidence,
        }]
    }


def test_auto_design_only_writes_target_characters_not_scene_mappings(monkeypatch, tmp_path) -> None:
    project_id, factory, _snapshot = _prepare(monkeypatch, tmp_path)
    captured: list[str] = []

    def fake_many(prompts: list[str]):
        captured.extend(prompts)
        return [_proposal()]

    monkeypatch.setattr(auto, "_request_text_model_many", fake_many)
    result = auto.generate_target_characters_only_v1(project_id, expected_revision="REV_1")

    assert result["status"] == "READY"
    assert result["target_character_count"] == 1
    assert result["review_count"] == 0
    assert len(captured) == 1
    assert "目标演员角色" in captured[0]
    assert "场景本土化" not in captured[0]

    with factory() as session:
        target = session.scalar(select(target_localization_v1.TargetCharacter))
        assert target is not None
        assert target.target_name == "Emma Miller"
        assert target.decision_source == "AI"
        assert session.scalars(select(target_localization_v1.SceneLocalizationMapping)).all() == []


def test_auto_design_preserves_manual_character_confirmation(monkeypatch, tmp_path) -> None:
    project_id, factory, _snapshot = _prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(auto, "_request_text_model_many", lambda _prompts: [_proposal()])
    auto.generate_target_characters_only_v1(project_id, expected_revision="REV_1")

    with factory() as session:
        target = session.scalar(select(target_localization_v1.TargetCharacter))
        target_id = target.id

    target_localization_v1.update_target_character_v1(
        target_id,
        target_name="Emma Carter",
        appearance_profile="美国女性，二十多岁，职业气质，深棕色长发",
        generation_prompt="consistent fictional American actor, professional, long dark brown hair",
    )

    monkeypatch.setattr(auto, "_request_text_model_many", lambda _prompts: [_proposal(name="Different AI Name")])
    auto.generate_target_characters_only_v1(project_id, expected_revision="REV_1")

    with factory() as session:
        target = session.get(target_localization_v1.TargetCharacter, target_id)
        assert target.target_name == "Emma Carter"
        assert target.decision_source == "MANUAL"
        assert target.status == "READY"


def test_auto_design_rejects_source_revision_change_before_write(monkeypatch, tmp_path) -> None:
    project_id, factory, _snapshot = _prepare(monkeypatch, tmp_path)
    calls = iter([{"revision": "REV_1"}, {"revision": "REV_2"}])
    monkeypatch.setattr(auto, "inventory", lambda _project_id: next(calls))
    monkeypatch.setattr(auto, "_request_text_model_many", lambda _prompts: [_proposal()])

    try:
        auto.generate_target_characters_only_v1(project_id, expected_revision="REV_1")
        assert False, "expected source revision conflict"
    except ValueError as exc:
        assert "发生变化" in str(exc)

    with factory() as session:
        assert session.scalars(select(target_localization_v1.TargetCharacter)).all() == []


def test_auto_redesign_clears_selected_reference_assets(monkeypatch, tmp_path) -> None:
    project_id, factory, _snapshot = _prepare(monkeypatch, tmp_path)
    monkeypatch.setattr(auto, "_request_text_model_many", lambda _prompts: [_proposal()])
    auto.generate_target_characters_only_v1(project_id, expected_revision="REV_1")

    with factory() as session:
        target = session.scalar(select(target_localization_v1.TargetCharacter))
        target.reference_assets_json = '["old-front.jpg", "old-side.jpg"]'
        session.commit()

    monkeypatch.setattr(auto, "_request_text_model_many", lambda _prompts: [_proposal(name="Olivia Miller")])
    auto.generate_target_characters_only_v1(project_id, expected_revision="REV_1")

    with factory() as session:
        target = session.scalar(select(target_localization_v1.TargetCharacter))
        assert target.target_name == "Olivia Miller"
        assert target.reference_assets_json == "[]"
