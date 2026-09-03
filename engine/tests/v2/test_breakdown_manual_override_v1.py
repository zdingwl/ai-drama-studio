from __future__ import annotations

from copy import deepcopy

from engine.app.breakdown_manual_override_v1 import (
    apply_manual_overrides_v1,
    persist_shot_manual_edit_v1,
)


def _draft(revision_id: str = "REV_1", *, is_current: bool = True) -> dict[str, object]:
    return {
        "run": {
            "id": "RUN_1" if is_current else "RUN_HISTORY",
            "project_id": "PROJECT_1",
            "episode_id": "EPISODE_1",
            "source_shot_revision_id": revision_id,
            "status": "READY",
            "is_current": is_current,
        }
    }


def _timeline(revision_id: str = "REV_1") -> dict[str, object]:
    return {
        "schema_version": "scene-timeline-v1",
        "source_breakdown_run_id": "RUN_1",
        "source_shot_revision_id": revision_id,
        "episode_id": "EPISODE_1",
        "status": "READY",
        "is_current": True,
        "scene_count": 1,
        "shot_count": 1,
        "warnings": [],
        "scenes": [
            {
                "ordinal": 1,
                "start_us": 0,
                "end_us": 3_000_000,
                "duration_us": 3_000_000,
                "title": "场景 01",
                "scene_info": {
                    "location": "走廊",
                    "interior_exterior": "室内",
                    "time_of_day": "白天",
                    "environment": "住宅走廊",
                },
                "people": [{"ref": "P1", "display_name": "人物1", "appearance": None}],
                "story_summary": "人物在走廊交谈。",
                "shots": [
                    {
                        "ordinal": 1,
                        "start_us": 0,
                        "end_us": 3_000_000,
                        "duration_us": 3_000_000,
                        "thumbnail_url": None,
                        "reference_url": None,
                        "summary": "人物说话。",
                        "narrative_function": "对白反应镜头",
                        "visual_description": "人物面部特写。",
                        "people": ["P1"],
                        "performance": [{"text": "说话", "people": ["P1"]}],
                        "dialogue": [
                            {
                                "start_us": 500_000,
                                "end_us": 2_500_000,
                                "text": "原始对白",
                                "speakers": ["P1"],
                            }
                        ],
                        "props": [],
                        "cinematography": {
                            "shot_type": "特写",
                            "composition": "居中",
                            "camera_motion": "固定",
                        },
                        "on_screen_text": [],
                    }
                ],
            }
        ],
    }


def test_manual_override_projects_without_mutating_ai_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(tmp_path))
    draft = _draft()
    raw = _timeline()
    untouched = deepcopy(raw)

    persist_shot_manual_edit_v1(
        draft,
        raw,
        shot_ordinal=1,
        edits={
            "summary": "人工修正后的内容概要",
            "performance_text": "人物惊讶地看向画外并说话",
            "shot_type": "近景",
            "composition": "人物偏右构图",
            "scene": {"environment": "明亮的住宅走廊", "time_of_day": "白天"},
            "dialogues": [{"index": 0, "text": "人工校正对白"}],
        },
    )

    projected = apply_manual_overrides_v1(draft, raw)
    shot = projected["scenes"][0]["shots"][0]
    assert shot["summary"] == "人工修正后的内容概要"
    assert shot["performance"] == [{"text": "人物惊讶地看向画外并说话", "people": ["P1"]}]
    assert shot["cinematography"]["shot_type"] == "近景"
    assert shot["cinematography"]["composition"] == "人物偏右构图"
    assert shot["dialogue"][0]["text"] == "人工校正对白"
    assert projected["scenes"][0]["scene_info"]["environment"] == "明亮的住宅走廊"
    assert raw == untouched


def test_second_dialogue_edit_keeps_immutable_source_anchor(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(tmp_path))
    draft = _draft()
    raw = _timeline()

    persist_shot_manual_edit_v1(
        draft,
        raw,
        shot_ordinal=1,
        edits={"dialogues": [{"index": 0, "text": "第一次人工对白"}]},
    )
    persist_shot_manual_edit_v1(
        draft,
        raw,
        shot_ordinal=1,
        edits={"dialogues": [{"index": 0, "text": "第二次人工对白"}]},
    )

    projected = apply_manual_overrides_v1(draft, raw)
    assert projected["scenes"][0]["shots"][0]["dialogue"][0]["text"] == "第二次人工对白"


def test_new_shot_revision_does_not_receive_old_manual_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(tmp_path))
    old_draft = _draft("REV_1")
    old_timeline = _timeline("REV_1")
    persist_shot_manual_edit_v1(
        old_draft,
        old_timeline,
        shot_ordinal=1,
        edits={"summary": "只属于旧 Revision 的人工内容"},
    )

    new_draft = _draft("REV_2")
    new_timeline = _timeline("REV_2")
    projected = apply_manual_overrides_v1(new_draft, new_timeline)
    assert projected["scenes"][0]["shots"][0]["summary"] == "人物说话。"


def test_historical_run_with_same_revision_never_receives_current_manual_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(tmp_path))
    current_draft = _draft("REV_1", is_current=True)
    raw = _timeline("REV_1")
    persist_shot_manual_edit_v1(
        current_draft,
        raw,
        shot_ordinal=1,
        edits={"summary": "当前人工修正"},
    )

    historical_draft = _draft("REV_1", is_current=False)
    historical = apply_manual_overrides_v1(historical_draft, raw)
    assert historical["scenes"][0]["shots"][0]["summary"] == "人物说话。"
