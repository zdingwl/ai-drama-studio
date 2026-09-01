from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import review_issue_v1, studio_v2, target_localization_v1


def _use_temp_db(monkeypatch, tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")
    monkeypatch.setattr(target_localization_v1, "get_session", lambda: factory())
    monkeypatch.setattr(review_issue_v1, "get_session", lambda: factory())
    return factory


def _snapshot(project_id: str, episode_id: str) -> dict:
    return {
        "schema_version": "source-drama-project-snapshot-v1",
        "status": "READY",
        "project_id": project_id,
        "project_name": "测试短剧",
        "source_language": "zh-CN",
        "source_fingerprint": "a" * 64,
        "episode_count": 1,
        "scene_count": 1,
        "shot_count": 1,
        "resolved_character_count": 1,
        "source_dialogue_count": 1,
        "warnings": [],
        "characters": [{"id": "CHAR_1", "name": "林晚", "cover_url": "/source-char.jpg"}],
        "episodes": [{
            "episode_id": episode_id,
            "episode_order": 1,
            "scenes": [{
                "scene_key": f"{episode_id}:RUN_1:S1",
                "title": "客厅",
                "story_summary": "林晚在客厅质问来访者。",
                "scene_info": {"location": "客厅", "environment": "现代住宅客厅"},
                "final_scene": {"id": "SCENE_1", "name": "林家客厅", "cover_url": None},
                "people": [{
                    "person_key": "PKEY_1",
                    "appearance": "二十多岁女性，长发，干练",
                    "character": {"id": "CHAR_1", "name": "林晚", "cover_url": "/source-char.jpg"},
                }],
                "shots": [{
                    "source_on_screen_text": [{"source_text": "第一集"}],
                }],
            }],
        }],
    }


def _seed(monkeypatch, tmp_path: Path):
    factory = _use_temp_db(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="测试短剧",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )
    episode_id = "EP_1"
    with factory() as session:
        session.add(studio_v2.Episode(
            id=episode_id,
            project_id=project["id"],
            title="第一集",
            original_filename="ep1.mp4",
            source_path=str(tmp_path / "ep1.mp4"),
            source_sha256="0" * 64,
            sort_order=1,
            status="IMPORTED",
        ))
        session.commit()
    snapshot = _snapshot(project["id"], episode_id)
    monkeypatch.setattr(target_localization_v1, "load_project_source_drama_snapshot_v1", lambda _project_id: snapshot)
    return project["id"], episode_id


def test_keep_scene_policy_does_not_require_model(monkeypatch, tmp_path: Path) -> None:
    project_id, _episode_id = _seed(monkeypatch, tmp_path)
    monkeypatch.setattr(target_localization_v1, "get_project_remake_policy", lambda _project_id: {"scene_policy": "KEEP"})
    monkeypatch.setattr(target_localization_v1, "semantic_model_status", lambda: {"ready": False})

    bundle = target_localization_v1.generate_target_localization_v1(project_id)

    assert bundle["scene_mappings"][0]["decision"] == "KEEP"
    assert bundle["scene_mappings"][0]["status"] == "READY"
    assert bundle["target_characters"][0]["status"] == "REVIEW"
    assert bundle["review_count"] == 1
    issues = review_issue_v1.list_review_issues(project_id)
    assert [item["issue_type"] for item in issues] == ["TARGET_CHARACTER"]


def test_model_can_auto_localize_character_and_scene(monkeypatch, tmp_path: Path) -> None:
    project_id, _episode_id = _seed(monkeypatch, tmp_path)
    monkeypatch.setattr(target_localization_v1, "get_project_remake_policy", lambda _project_id: {"scene_policy": "AUTO"})
    monkeypatch.setattr(target_localization_v1, "semantic_model_status", lambda: {"ready": True})

    def fake_request(prompt: str):
        if "目标演员角色" in prompt:
            return {"characters": [{
                "source_character_id": "CHAR_1",
                "target_name": "Emma Miller",
                "appearance_profile": "25岁左右的美国女性，干练职业气质，棕色长发",
                "generation_prompt": "consistent American woman, mid-20s, professional, long brown hair",
                "confidence": 0.93,
            }]}
        return {"scenes": [{
            "scene_key": "EP_1:RUN_1:S1",
            "decision": "LOCALIZE",
            "target_label": "American apartment living room",
            "target_description": "Contemporary middle-class American apartment living room, same spatial function and blocking capacity.",
            "reason": "源画面文字具有明显地区特征",
            "confidence": 0.88,
        }]}

    monkeypatch.setattr(target_localization_v1, "_request_text_model", fake_request)
    bundle = target_localization_v1.generate_target_localization_v1(project_id)

    assert bundle["status"] == "READY"
    assert bundle["review_count"] == 0
    assert bundle["target_characters"][0]["target_name"] == "Emma Miller"
    assert bundle["scene_mappings"][0]["decision"] == "LOCALIZE"
    assert review_issue_v1.list_review_issues(project_id) == []


def test_manual_character_edit_closes_review_issue(monkeypatch, tmp_path: Path) -> None:
    project_id, _episode_id = _seed(monkeypatch, tmp_path)
    monkeypatch.setattr(target_localization_v1, "get_project_remake_policy", lambda _project_id: {"scene_policy": "KEEP"})
    monkeypatch.setattr(target_localization_v1, "semantic_model_status", lambda: {"ready": False})
    bundle = target_localization_v1.generate_target_localization_v1(project_id)
    target_id = bundle["target_characters"][0]["id"]

    updated = target_localization_v1.update_target_character_v1(
        target_id,
        target_name="Emma Miller",
        appearance_profile="美国女性，二十多岁，职业气质，棕色长发",
        generation_prompt="consistent American woman, mid-20s, professional, long brown hair",
    )

    assert updated["status"] == "READY"
    assert updated["decision_source"] == "MANUAL"
    assert review_issue_v1.list_review_issues(project_id) == []
