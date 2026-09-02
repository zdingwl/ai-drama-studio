from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import remake_timeline_v1, review_issue_v1, studio_v2


def _use_temp_db(monkeypatch, tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)
    monkeypatch.setattr(remake_timeline_v1, "get_session", lambda: factory())
    monkeypatch.setattr(review_issue_v1, "get_session", lambda: factory())
    return factory


def _shot(key: str, ordinal: int, start: float, duration: float, people: list[str]) -> dict:
    start_us = int(start * 1_000_000)
    duration_us = int(duration * 1_000_000)
    return {
        "shot_key": key,
        "ordinal": ordinal,
        "source_shot_id": None,
        "start_us": start_us,
        "end_us": start_us + duration_us,
        "duration_us": duration_us,
        "reference_url": f"/ref/{key}.mp4",
        "people": people,
    }


def _source(project_id: str, episode_id: str, shots: list[dict]) -> dict:
    return {
        "project_id": project_id,
        "source_fingerprint": "a" * 64,
        "episodes": [{
            "episode_id": episode_id,
            "scenes": [{
                "scene_key": f"{episode_id}:SCENE1",
                "people": [
                    {"person_key": "P1", "character": {"id": "CHAR_1", "name": "A"}},
                    {"person_key": "P2", "character": {"id": "CHAR_2", "name": "B"}},
                ],
                "shots": shots,
            }],
        }],
    }


def _canonical_source(
    project_id: str,
    episode_id: str,
    shots: list[dict],
    *,
    group_id: str,
    source_start: float,
    source_end: float,
    projection_specs: list[tuple[str, float, float, str]],
) -> dict:
    source = _source(project_id, episode_id, shots)
    episode = source["episodes"][0]
    scene_key = episode["scenes"][0]["scene_key"]
    projections = []
    for index, (shot_key, start, end, text) in enumerate(projection_specs, start=1):
        projections.append({
            "dialogue_key": f"{shot_key}:D1",
            "shot_key": shot_key,
            "scene_key": scene_key,
            "projection_index": index,
            "start_us": int(start * 1_000_000),
            "end_us": int(end * 1_000_000),
            "source_text": text,
        })
    episode["source_dialogue_utterances"] = [{
        "dialogue_group_id": group_id,
        "start_us": int(source_start * 1_000_000),
        "end_us": int(source_end * 1_000_000),
        "source_text": "你怎么会在这里？",
        "source_language": "zh-CN",
        "speakers": ["P1"],
        "projection_count": len(projections),
        "projections": projections,
    }]
    return source


def _dialogue(
    *,
    row_id: str,
    episode_id: str,
    shot_key: str,
    source_key: str,
    source_start: float,
    source_end: float,
    duration: float | None,
    source_character_id: str = "CHAR_1",
) -> dict:
    ready = duration is not None
    return {
        "id": row_id,
        "episode_id": episode_id,
        "shot_key": shot_key,
        "source_dialogue_key": source_key,
        "source_dialogue_signature": "b" * 64,
        "source_start_us": int(source_start * 1_000_000),
        "source_end_us": int(source_end * 1_000_000),
        "source_character_id": source_character_id,
        "target_character_id": "TARGET_1",
        "final_text": "Target line",
        "status": "READY" if ready else "REVIEW",
        "audio_status": "READY" if ready else "NOT_CONFIGURED",
        "audio_input_signature": "c" * 64 if ready else None,
        "speech_duration_us": int(duration * 1_000_000) if duration is not None else None,
    }


def _seed(
    monkeypatch,
    tmp_path: Path,
    shots: list[dict],
    dialogues: list[dict],
    *,
    source_override: dict | None = None,
):
    factory = _use_temp_db(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="Timing Test",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )
    episode_id = "EP_1"
    with factory() as session:
        session.add(studio_v2.Episode(
            id=episode_id,
            project_id=project["id"],
            title="EP1",
            original_filename="ep1.mp4",
            source_path=str(tmp_path / "ep1.mp4"),
            source_sha256="0" * 64,
            sort_order=1,
            status="IMPORTED",
        ))
        session.commit()
    source = source_override or _source(project["id"], episode_id, shots)
    source["project_id"] = project["id"]
    for dialogue in dialogues:
        dialogue["episode_id"] = episode_id
    monkeypatch.setattr(remake_timeline_v1, "load_project_source_drama_snapshot_v1", lambda _project_id: source)
    monkeypatch.setattr(remake_timeline_v1, "validate_target_dialogue_dependencies_v1", lambda _project_id: None)
    monkeypatch.setattr(remake_timeline_v1, "get_target_dialogue_v1", lambda _project_id: {"dialogues": dialogues})
    return project["id"], episode_id, source


def test_keep_when_real_speech_finishes_inside_source_shot(monkeypatch, tmp_path: Path) -> None:
    shots = [_shot("H1", 1, 0.0, 3.0, ["P1"])]
    dialogues = [_dialogue(row_id="D1", episode_id="", shot_key="H1", source_key="S1", source_start=0.5, source_end=2.8, duration=2.35)]
    project_id, _, _ = _seed(monkeypatch, tmp_path, shots, dialogues)

    result = remake_timeline_v1.generate_remake_timeline_v1(project_id)
    plan = result["episodes"][0]["shot_plans"][0]

    assert plan["strategy"] == "KEEP"
    assert plan["planned_duration_us"] == 3_000_000
    # Speech ends at 2.85s. Lack of a full 180ms optional tail must not extend the Shot.
    assert plan["dialogue_plans"][0]["planned_end_offset_us"] == 2_850_000


def test_trim_shorter_target_line_only_when_source_dialogue_was_near_tail(monkeypatch, tmp_path: Path) -> None:
    shots = [_shot("H1", 1, 0.0, 4.0, ["P1"])]
    dialogues = [_dialogue(row_id="D1", episode_id="", shot_key="H1", source_key="S1", source_start=1.0, source_end=3.8, duration=1.7)]
    project_id, _, _ = _seed(monkeypatch, tmp_path, shots, dialogues)

    result = remake_timeline_v1.generate_remake_timeline_v1(project_id)
    plan = result["episodes"][0]["shot_plans"][0]

    assert plan["strategy"] == "TRIM"
    assert plan["planned_duration_us"] == 2_880_000
    assert plan["duration_delta_us"] == -1_120_000


def test_long_line_prefers_next_silent_reaction_shot(monkeypatch, tmp_path: Path) -> None:
    shots = [
        _shot("H1", 1, 0.0, 2.0, ["P1"]),
        _shot("H2", 2, 2.0, 1.5, ["P2"]),
    ]
    dialogues = [_dialogue(row_id="D1", episode_id="", shot_key="H1", source_key="S1", source_start=0.5, source_end=1.8, duration=2.2)]
    project_id, _, _ = _seed(monkeypatch, tmp_path, shots, dialogues)

    result = remake_timeline_v1.generate_remake_timeline_v1(project_id)
    first = result["episodes"][0]["shot_plans"][0]
    second = result["episodes"][0]["shot_plans"][1]

    assert first["strategy"] == "CARRY_OVER_REACTION"
    assert first["planned_duration_us"] == 2_000_000
    assert first["dialogue_plans"][0]["carry_over_shot_key"] == "H2"
    assert first["dialogue_plans"][0]["overrun_us"] == 700_000
    assert second["planned_start_us"] == 2_000_000


def test_long_line_extends_when_next_shot_is_not_a_reaction_candidate(monkeypatch, tmp_path: Path) -> None:
    shots = [
        _shot("H1", 1, 0.0, 2.0, ["P1"]),
        _shot("H2", 2, 2.0, 1.5, ["P1"]),
    ]
    dialogues = [_dialogue(row_id="D1", episode_id="", shot_key="H1", source_key="S1", source_start=0.5, source_end=1.8, duration=2.2)]
    project_id, _, _ = _seed(monkeypatch, tmp_path, shots, dialogues)

    result = remake_timeline_v1.generate_remake_timeline_v1(project_id)
    first = result["episodes"][0]["shot_plans"][0]
    second = result["episodes"][0]["shot_plans"][1]

    assert first["strategy"] == "EXTEND"
    assert first["planned_duration_us"] == 2_880_000
    assert second["planned_start_us"] == 2_880_000


def test_cross_shot_utterance_uses_one_audio_plan_without_extending_first_projection(monkeypatch, tmp_path: Path) -> None:
    shots = [
        _shot("H1", 1, 0.0, 2.0, ["P1"]),
        _shot("H2", 2, 2.0, 2.0, ["P2"]),
    ]
    group_id = "EP_1:RUN_2:DG:UTTERANCE_1"
    dialogues = [_dialogue(
        row_id="D1",
        episode_id="",
        shot_key="H1",
        source_key=group_id,
        source_start=1.5,
        source_end=2.5,
        duration=1.8,
    )]
    source = _canonical_source(
        "PLACEHOLDER",
        "EP_1",
        shots,
        group_id=group_id,
        source_start=1.5,
        source_end=2.5,
        projection_specs=[
            ("H1", 1.5, 2.0, "你怎么"),
            ("H2", 2.0, 2.5, "会在这里？"),
        ],
    )
    project_id, _, source = _seed(monkeypatch, tmp_path, shots, dialogues, source_override=source)
    source["project_id"] = project_id

    result = remake_timeline_v1.generate_remake_timeline_v1(project_id)
    first, second = result["episodes"][0]["shot_plans"]

    assert result["status"] == "READY"
    assert first["planned_duration_us"] == 2_000_000
    assert second["planned_duration_us"] == 2_000_000
    assert len(first["dialogue_plans"]) == 1
    assert second["dialogue_plans"] == []
    dialogue_plan = first["dialogue_plans"][0]
    assert dialogue_plan["source_dialogue_key"] == group_id
    assert dialogue_plan["planned_start_us"] == 1_500_000
    assert dialogue_plan["planned_end_us"] == 3_300_000
    # The one TTS event naturally crosses H1 -> H2; it is not duplicated on H2.
    assert first["planned_end_us"] == 2_000_000
    assert second["planned_start_us"] == 2_000_000
    assert second["planned_end_us"] == 4_000_000
    assert review_issue_v1.list_review_issues(project_id) == []


def test_cross_shot_target_overrun_extends_last_projection_not_first(monkeypatch, tmp_path: Path) -> None:
    shots = [
        _shot("H1", 1, 0.0, 2.0, ["P1"]),
        _shot("H2", 2, 2.0, 2.0, ["P1"]),
    ]
    group_id = "EP_1:RUN_2:DG:UTTERANCE_2"
    dialogues = [_dialogue(
        row_id="D1",
        episode_id="",
        shot_key="H1",
        source_key=group_id,
        source_start=1.5,
        source_end=2.5,
        duration=3.0,
    )]
    source = _canonical_source(
        "PLACEHOLDER",
        "EP_1",
        shots,
        group_id=group_id,
        source_start=1.5,
        source_end=2.5,
        projection_specs=[
            ("H1", 1.5, 2.0, "你怎么"),
            ("H2", 2.0, 2.5, "会在这里？"),
        ],
    )
    project_id, _, source = _seed(monkeypatch, tmp_path, shots, dialogues, source_override=source)
    source["project_id"] = project_id

    result = remake_timeline_v1.generate_remake_timeline_v1(project_id)
    first, second = result["episodes"][0]["shot_plans"]

    assert result["status"] == "READY"
    assert first["strategy"] == "KEEP"
    assert first["planned_duration_us"] == 2_000_000
    assert len(first["dialogue_plans"]) == 1
    # 1.5s + 3.0s target speech = 4.5s. Source visual projection span lasts through H2 end=4.0s,
    # so only H2 receives 0.5s speech overrun + 0.18s natural tail.
    assert second["strategy"] == "EXTEND"
    assert second["planned_duration_us"] == 2_680_000
    assert second["planned_start_us"] == 2_000_000
    assert second["planned_end_us"] == 4_680_000
    dialogue_plan = first["dialogue_plans"][0]
    assert dialogue_plan["strategy"] == "EXTEND"
    assert dialogue_plan["overrun_us"] == 500_000
    assert dialogue_plan["planned_end_us"] == 4_500_000


def test_extreme_extension_creates_timing_review_and_manual_edit_reflows(monkeypatch, tmp_path: Path) -> None:
    shots = [
        _shot("H1", 1, 0.0, 2.0, ["P1"]),
        _shot("H2", 2, 2.0, 1.0, ["P1"]),
    ]
    dialogues = [_dialogue(row_id="D1", episode_id="", shot_key="H1", source_key="S1", source_start=0.2, source_end=1.8, duration=6.0)]
    project_id, _, _ = _seed(monkeypatch, tmp_path, shots, dialogues)

    result = remake_timeline_v1.generate_remake_timeline_v1(project_id)
    episode = result["episodes"][0]
    first = episode["shot_plans"][0]

    assert result["status"] == "REVIEW"
    assert first["strategy"] == "HUMAN_REVIEW"
    issues = review_issue_v1.list_review_issues(project_id)
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "DIALOGUE_TIMING"

    updated = remake_timeline_v1.update_remake_shot_timing_v1(
        episode["id"],
        first["shot_plan_id"],
        strategy="EXTEND",
        planned_duration_us=6_380_000,
        reason="接受延长，后续交给 H3 生成动作延续",
    )

    assert updated["status"] == "READY"
    assert updated["shot_plans"][0]["decision_source"] == "MANUAL"
    assert updated["shot_plans"][1]["planned_start_us"] == 6_380_000
    assert review_issue_v1.list_review_issues(project_id) == []


def test_missing_tts_is_waiting_audio_not_human_review(monkeypatch, tmp_path: Path) -> None:
    shots = [_shot("H1", 1, 0.0, 3.0, ["P1"])]
    dialogues = [_dialogue(row_id="D1", episode_id="", shot_key="H1", source_key="S1", source_start=0.5, source_end=2.0, duration=None)]
    project_id, _, _ = _seed(monkeypatch, tmp_path, shots, dialogues)

    result = remake_timeline_v1.generate_remake_timeline_v1(project_id)
    plan = result["episodes"][0]["shot_plans"][0]

    assert result["status"] == "WAITING_AUDIO"
    assert plan["status"] == "WAITING_AUDIO"
    assert plan["dialogue_plans"][0]["speech_duration_us"] is None
    assert review_issue_v1.list_review_issues(project_id) == []
