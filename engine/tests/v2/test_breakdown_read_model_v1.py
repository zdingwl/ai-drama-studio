from __future__ import annotations

from copy import deepcopy

from engine.app.breakdown_read_model_v1 import (
    IDENTITY_PARTIAL_WARNING,
    IDENTITY_PENDING_WARNING,
    IDENTITY_STALE_WARNING,
    compose_breakdown_read_model_v1,
)


def _timeline() -> dict[str, object]:
    return {
        "schema_version": "scene-timeline-v1",
        "source_breakdown_run_id": "RUN1",
        "source_shot_revision_id": "SHOTREV1",
        "episode_id": "EP1",
        "status": "READY",
        "is_current": True,
        "scene_count": 1,
        "shot_count": 1,
        "warnings": [],
        "scenes": [
            {
                "ordinal": 1,
                "start_us": 0,
                "end_us": 1_000_000,
                "duration_us": 1_000_000,
                "title": "客厅",
                "scene_info": {
                    "location": "客厅",
                    "interior_exterior": "室内",
                    "time_of_day": "白天",
                    "environment": "窗边有自然光",
                },
                "people": [
                    {"ref": "P1", "display_name": "人物1", "appearance": "黑色外套"},
                    {"ref": "P2", "display_name": "人物2", "appearance": "白色衬衫"},
                ],
                "story_summary": "两人在客厅短暂交谈。",
                "shots": [
                    {
                        "ordinal": 1,
                        "start_us": 0,
                        "end_us": 1_000_000,
                        "duration_us": 1_000_000,
                        "thumbnail_url": "/api/shot-revision-items/ITEM1/thumbnail",
                        "reference_url": "/api/shot-revision-items/ITEM1/reference",
                        "visual_description": "P1 站在窗边，P2 面向 P1。",
                        "people": ["P1", "P2"],
                        "performance": [
                            {"text": "P1 转身看向 P2", "people": ["P1"]},
                        ],
                        "dialogue": [
                            {
                                "start_us": 100_000,
                                "end_us": 320_000,
                                "text": "这句对白必须保持原样。",
                                "speakers": [],
                            }
                        ],
                        "props": [
                            {"label": "花瓶", "interaction": "拿起花瓶"},
                        ],
                        "cinematography": {
                            "shot_type": "中景",
                            "composition": "双人构图",
                            "camera_motion": None,
                        },
                        "on_screen_text": [
                            {
                                "start_us": 400_000,
                                "end_us": 500_000,
                                "text": "OCR 原文 100% 保留",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _resolution() -> dict[str, object]:
    return {
        "schema_version": "breakdown-character-bridge-v1",
        "profile": "breakdown-character-presence-signature-p5-v1",
        "project_id": "PROJECT1",
        "episode_id": "EP1",
        "breakdown_run_id": "RUN1",
        "shot_revision_id": "SHOTREV1",
        "asset_revision_id": "ASSETREV1",
        "scene_count": 1,
        "person_count": 2,
        "resolved_count": 1,
        "unresolved_count": 1,
        "warnings": [],
        "scenes": [
            {
                "scene_segment_id": "SEG1",
                "scene_ordinal": 1,
                "subject_aware_shot_count": 1,
                "resolved_count": 1,
                "unresolved_count": 1,
                "people": [
                    {
                        "scene_person_ref": "P1",
                        "local_subject_id": "LS1",
                        "local_subject_ordinal": 1,
                        "local_display_name": "人物1",
                        "status": "UNRESOLVED",
                        "character_id": None,
                        "character_name": None,
                        "support_shot_ids": ["SHOT1"],
                        "support_shot_ordinals": [1],
                        "resolution_basis": "NO_MATCHING_FINAL_CHARACTER_SIGNATURE",
                    },
                    {
                        "scene_person_ref": "P2",
                        "local_subject_id": "LS2",
                        "local_subject_ordinal": 2,
                        "local_display_name": "人物2",
                        "status": "RESOLVED",
                        "character_id": "CHAR1",
                        "character_name": "人物001",
                        "support_shot_ids": ["SHOT1"],
                        "support_shot_ordinals": [1],
                        "resolution_basis": "FINAL_SHOT_BINDING_SIGNATURE_V1",
                    },
                ],
            }
        ],
    }


def _snapshots() -> dict[str, dict[str, str | None]]:
    return {
        "CHAR1": {
            "id": "CHAR1",
            "name": "人物001",
            "cover_url": "/api/content-analysis/characters/CAND1/cover",
        }
    }


def _identity_people(result: dict[str, object]) -> list[dict[str, object]]:
    identity = result["identity"]
    assert isinstance(identity, dict)
    scenes = identity["scenes"]
    assert isinstance(scenes, list)
    scene = scenes[0]
    assert isinstance(scene, dict)
    people = scene["people"]
    assert isinstance(people, list)
    return people  # type: ignore[return-value]


def _assert_all_anonymous(result: dict[str, object]) -> None:
    people = _identity_people(result)
    assert [item["display_name"] for item in people] == ["人物1", "人物2"]
    assert all(item["character"] is None for item in people)
    identity = result["identity"]
    assert isinstance(identity, dict)
    assert identity["resolved_count"] == 0
    assert identity["unresolved_count"] == 2


def test_resolved_p5_person_uses_current_final_character_and_unresolved_stays_anonymous() -> None:
    timeline = _timeline()
    result = compose_breakdown_read_model_v1(
        timeline,
        _resolution(),
        character_snapshots=_snapshots(),
    )

    people = _identity_people(result)
    assert people[0] == {"ref": "P1", "display_name": "人物1", "character": None}
    assert people[1] == {
        "ref": "P2",
        "display_name": "人物001",
        "character": {
            "id": "CHAR1",
            "name": "人物001",
            "cover_url": "/api/content-analysis/characters/CAND1/cover",
        },
    }
    identity = result["identity"]
    assert isinstance(identity, dict)
    assert identity["asset_revision_id"] == "ASSETREV1"
    assert identity["resolved_count"] == 1
    assert identity["unresolved_count"] == 1
    assert identity["warnings"] == [IDENTITY_PARTIAL_WARNING]

    # P6 can only add an identity overlay. Frozen G2 facts, including verbatim ASR/OCR, must be identical.
    assert result["timeline"] == timeline
    rendered_timeline = result["timeline"]
    assert isinstance(rendered_timeline, dict)
    scene = rendered_timeline["scenes"][0]  # type: ignore[index]
    shot = scene["shots"][0]
    assert shot["dialogue"][0]["text"] == "这句对白必须保持原样。"
    assert shot["on_screen_text"][0]["text"] == "OCR 原文 100% 保留"
    assert shot["visual_description"] == "P1 站在窗边，P2 面向 P1。"
    assert shot["props"][0]["interaction"] == "拿起花瓶"


def test_missing_p5_resolution_keeps_every_person_anonymous() -> None:
    result = compose_breakdown_read_model_v1(_timeline(), None)

    _assert_all_anonymous(result)
    identity = result["identity"]
    assert isinstance(identity, dict)
    assert identity["warnings"] == [IDENTITY_PENDING_WARNING]


def test_breakdown_run_or_shot_revision_mismatch_fails_closed() -> None:
    for field, value in (("breakdown_run_id", "OLD_RUN"), ("shot_revision_id", "OLD_REV")):
        resolution = _resolution()
        resolution[field] = value
        result = compose_breakdown_read_model_v1(
            _timeline(),
            resolution,
            character_snapshots=_snapshots(),
        )
        _assert_all_anonymous(result)
        identity = result["identity"]
        assert isinstance(identity, dict)
        assert identity["warnings"] == [IDENTITY_STALE_WARNING]


def test_stale_asset_revision_gate_fails_closed() -> None:
    result = compose_breakdown_read_model_v1(
        _timeline(),
        _resolution(),
        current_asset_revision_matches=False,
        character_snapshots=_snapshots(),
    )

    _assert_all_anonymous(result)


def test_scene_person_ref_or_display_name_mismatch_fails_closed() -> None:
    mismatch_ref = _resolution()
    people = mismatch_ref["scenes"][0]["people"]  # type: ignore[index]
    people[1]["scene_person_ref"] = "P3"
    result = compose_breakdown_read_model_v1(
        _timeline(), mismatch_ref, character_snapshots=_snapshots()
    )
    _assert_all_anonymous(result)

    mismatch_name = _resolution()
    people = mismatch_name["scenes"][0]["people"]  # type: ignore[index]
    people[1]["local_display_name"] = "对白里提到的名字"
    result = compose_breakdown_read_model_v1(
        _timeline(), mismatch_name, character_snapshots=_snapshots()
    )
    _assert_all_anonymous(result)


def test_missing_or_renamed_current_character_snapshot_fails_closed() -> None:
    result = compose_breakdown_read_model_v1(
        _timeline(), _resolution(), character_snapshots={}
    )
    _assert_all_anonymous(result)

    renamed = _snapshots()
    renamed["CHAR1"] = {"id": "CHAR1", "name": "新资产名", "cover_url": None}
    result = compose_breakdown_read_model_v1(
        _timeline(), _resolution(), character_snapshots=renamed
    )
    _assert_all_anonymous(result)


def test_invalid_bridge_aggregate_counts_fail_closed() -> None:
    resolution = _resolution()
    resolution["resolved_count"] = 2
    resolution["unresolved_count"] = 0

    result = compose_breakdown_read_model_v1(
        _timeline(), resolution, character_snapshots=_snapshots()
    )
    _assert_all_anonymous(result)


def test_duplicate_scene_or_person_refs_cannot_be_collapsed_into_a_resolution() -> None:
    duplicate_scene = _resolution()
    scene_copy = deepcopy(duplicate_scene["scenes"][0])  # type: ignore[index]
    duplicate_scene["scenes"] = [duplicate_scene["scenes"][0], scene_copy]  # type: ignore[index]
    duplicate_scene["scene_count"] = 2
    duplicate_scene["person_count"] = 4
    duplicate_scene["resolved_count"] = 2
    duplicate_scene["unresolved_count"] = 2
    result = compose_breakdown_read_model_v1(
        _timeline(), duplicate_scene, character_snapshots=_snapshots()
    )
    _assert_all_anonymous(result)

    duplicate_ref = _resolution()
    people = duplicate_ref["scenes"][0]["people"]  # type: ignore[index]
    people[1]["scene_person_ref"] = "P1"
    result = compose_breakdown_read_model_v1(
        _timeline(), duplicate_ref, character_snapshots=_snapshots()
    )
    _assert_all_anonymous(result)


def test_unresolved_person_can_never_smuggle_character_fields_through_p6() -> None:
    # P5 contract itself rejects a UNRESOLVED row carrying Character identity. P6 must not bypass it.
    resolution = _resolution()
    person = resolution["scenes"][0]["people"][0]  # type: ignore[index]
    person["character_id"] = "CHAR_EVIL"
    person["character_name"] = "猜出来的人名"

    try:
        compose_breakdown_read_model_v1(
            _timeline(), resolution, character_snapshots=_snapshots()
        )
    except ValueError as exc:
        assert "UNRESOLVED" in str(exc)
    else:
        raise AssertionError("UNRESOLVED 人物携带 Character identity 时必须被 Contract 拒绝")
