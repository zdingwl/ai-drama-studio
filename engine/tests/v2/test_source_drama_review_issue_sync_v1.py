from __future__ import annotations

from copy import deepcopy

from engine.app import source_drama_review_issue_sync_v1 as sync


def _snapshot() -> dict:
    person_key = "EP_1:RUN_1:S1:P1"
    scene_key = "EP_1:RUN_1:S1"
    shot_key = "EP_1:REV_1:H1"
    dialogue_key = f"{shot_key}:D1"
    dialogue_group_id = "RUN_1:DG:SOURCE_1"
    return {
        "schema_version": "source-drama-project-snapshot-v1",
        "status": "READY",
        "project_id": "PROJECT_1",
        "project_name": "测试短剧",
        "source_language": "zh-CN",
        "source_fingerprint": "a" * 64,
        "episode_count": 1,
        "scene_count": 1,
        "shot_count": 1,
        "resolved_character_count": 1,
        "source_dialogue_count": 1,
        "source_dialogue_projection_count": 1,
        "warnings": [],
        "characters": [
            {"id": "CHAR_1", "name": "林晚", "cover_url": None},
        ],
        "episodes": [
            {
                "schema_version": "source-drama-snapshot-v1",
                "status": "READY",
                "project_id": "PROJECT_1",
                "episode_id": "EP_1",
                "episode_title": "第一集",
                "episode_order": 1,
                "source_language": "zh-CN",
                "source_breakdown_run_id": "RUN_1",
                "source_shot_revision_id": "REV_1",
                "source_asset_revision_id": "ASSETREV_1",
                "source_fingerprint": "b" * 64,
                "scene_count": 1,
                "shot_count": 1,
                "resolved_character_count": 1,
                "unresolved_person_count": 0,
                "source_dialogue_count": 1,
                "source_dialogue_projection_count": 1,
                "source_on_screen_text_count": 0,
                "warnings": [],
                "source_dialogue_utterances": [
                    {
                        "dialogue_group_id": dialogue_group_id,
                        "start_us": 1_000_000,
                        "end_us": 2_000_000,
                        "source_text": "你怎么会在这里？",
                        "source_language": "zh-CN",
                        "speakers": [],
                        "projection_count": 1,
                        "projections": [
                            {
                                "dialogue_key": dialogue_key,
                                "shot_key": shot_key,
                                "scene_key": scene_key,
                                "projection_index": 1,
                                "start_us": 1_000_000,
                                "end_us": 2_000_000,
                                "source_text": "你怎么会在这里？",
                            }
                        ],
                    }
                ],
                "scenes": [
                    {
                        "scene_key": scene_key,
                        "ordinal": 1,
                        "start_us": 0,
                        "end_us": 4_000_000,
                        "duration_us": 4_000_000,
                        "title": "客厅",
                        "story_summary": None,
                        "scene_info": {
                            "location": "客厅",
                            "interior_exterior": None,
                            "time_of_day": None,
                            "environment": None,
                        },
                        "final_scene": None,
                        "people": [
                            {
                                "person_key": person_key,
                                "scene_person_ref": "P1",
                                "display_name": "林晚",
                                "appearance": None,
                                "character": {"id": "CHAR_1", "name": "林晚", "cover_url": None},
                            }
                        ],
                        "shots": [
                            {
                                "shot_key": shot_key,
                                "ordinal": 1,
                                "source_shot_id": "SHOT_1",
                                "source_revision_item_id": "ITEM_1",
                                "start_us": 0,
                                "end_us": 4_000_000,
                                "duration_us": 4_000_000,
                                "thumbnail_url": None,
                                "reference_url": "/reference/1",
                                "visual_description": None,
                                "people": [person_key],
                                "performance": [],
                                "source_dialogue": [
                                    {
                                        "dialogue_key": dialogue_key,
                                        "dialogue_group_id": dialogue_group_id,
                                        "projection_index": 1,
                                        "start_us": 1_000_000,
                                        "end_us": 2_000_000,
                                        "source_text": "你怎么会在这里？",
                                        "speakers": [],
                                    }
                                ],
                                "observed_props": [],
                                "final_props": [],
                                "cinematography": {
                                    "shot_type": None,
                                    "composition": None,
                                    "camera_motion": None,
                                },
                                "source_on_screen_text": [],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _add_second_unresolved_person(payload: dict) -> str:
    scene = payload["episodes"][0]["scenes"][0]
    second_key = "EP_1:RUN_1:S1:P2"
    scene["people"].append({
        "person_key": second_key,
        "scene_person_ref": "P2",
        "display_name": "顾言",
        "appearance": None,
        "character": None,
    })
    scene["shots"][0]["people"].append(second_key)
    payload["episodes"][0]["unresolved_person_count"] = 1
    payload["episodes"][0]["status"] = "READY_WITH_WARNINGS"
    payload["episodes"][0]["warnings"] = ["1 个 Scene-local 人物尚未安全解析到 Final Character"]
    payload["status"] = "READY_WITH_WARNINGS"
    payload["warnings"] = ["第01集：1 个 Scene-local 人物尚未安全解析到 Final Character"]
    return second_key


def test_missing_speaker_with_single_scene_person_is_auto_resolved(monkeypatch) -> None:
    created: list[dict] = []
    resolved: list[tuple[str, str, set[str]]] = []
    monkeypatch.setattr(sync, "upsert_review_issue", lambda **kwargs: created.append(kwargs) or kwargs)
    monkeypatch.setattr(
        sync,
        "_auto_resolve_missing",
        lambda project_id, prefix, active_keys: resolved.append((project_id, prefix, set(active_keys))),
    )

    count = sync.sync_source_drama_speaker_issues("PROJECT_1", _snapshot())

    assert count == 0
    assert created == []
    assert resolved == [("PROJECT_1", sync.SPEAKER_PREFIX, set())]


def test_single_speaker_does_not_create_review_issue(monkeypatch) -> None:
    payload = _snapshot()
    person_key = payload["episodes"][0]["scenes"][0]["people"][0]["person_key"]
    payload["episodes"][0]["scenes"][0]["shots"][0]["source_dialogue"][0]["speakers"] = [person_key]
    created: list[dict] = []
    monkeypatch.setattr(sync, "upsert_review_issue", lambda **kwargs: created.append(kwargs) or kwargs)
    monkeypatch.setattr(sync, "_auto_resolve_missing", lambda *_args, **_kwargs: None)

    assert sync.sync_source_drama_speaker_issues("PROJECT_1", payload) == 0
    assert created == []


def test_missing_speaker_with_multiple_people_requires_review(monkeypatch) -> None:
    payload = deepcopy(_snapshot())
    _add_second_unresolved_person(payload)
    created: list[dict] = []
    monkeypatch.setattr(sync, "upsert_review_issue", lambda **kwargs: created.append(kwargs) or kwargs)
    monkeypatch.setattr(sync, "_auto_resolve_missing", lambda *_args, **_kwargs: None)

    assert sync.sync_source_drama_speaker_issues("PROJECT_1", payload) == 1
    assert created[0]["issue_type"] == "SPEAKER"
    assert "自动结合" in created[0]["reason"]


def test_multiple_speakers_requires_review(monkeypatch) -> None:
    payload = deepcopy(_snapshot())
    scene = payload["episodes"][0]["scenes"][0]
    second_key = _add_second_unresolved_person(payload)
    scene["shots"][0]["source_dialogue"][0]["speakers"] = [scene["people"][0]["person_key"], second_key]

    created: list[dict] = []
    monkeypatch.setattr(sync, "upsert_review_issue", lambda **kwargs: created.append(kwargs) or kwargs)
    monkeypatch.setattr(sync, "_auto_resolve_missing", lambda *_args, **_kwargs: None)

    assert sync.sync_source_drama_speaker_issues("PROJECT_1", payload) == 1
    assert "多个不同人物" in created[0]["reason"]
