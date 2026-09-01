from __future__ import annotations

from pathlib import Path
import wave

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import review_issue_v1, studio_v2, target_dialogue_v1, target_localization_v1
from engine.app.target_dialogue_pipeline_v1 import run_target_dialogue_pipeline_v1


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
    monkeypatch.setattr(target_dialogue_v1, "get_session", lambda: factory())
    monkeypatch.setattr(target_dialogue_v1, "project_dir", lambda _project_id: tmp_path / "workspace" / _project_id)
    monkeypatch.setattr(review_issue_v1, "get_session", lambda: factory())
    return factory


def _snapshot(project_id: str, episode_id: str, *, speakers: list[str] | None = None) -> dict:
    person_key = f"{episode_id}:RUN_1:S1:P1"
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
        "characters": [{"id": "CHAR_1", "name": "林晚", "cover_url": None}],
        "episodes": [{
            "episode_id": episode_id,
            "episode_order": 1,
            "scenes": [{
                "scene_key": f"{episode_id}:RUN_1:S1",
                "title": "客厅质问",
                "story_summary": "林晚在客厅质问来访者。",
                "people": [{
                    "person_key": person_key,
                    "appearance": "二十多岁女性，干练",
                    "character": {"id": "CHAR_1", "name": "林晚", "cover_url": None},
                }],
                "shots": [{
                    "shot_key": f"{episode_id}:REV_1:H1",
                    "visual_description": "林晚抬头看向门口，神情惊讶。",
                    "source_dialogue": [{
                        "dialogue_key": f"{episode_id}:REV_1:H1:D1",
                        "start_us": 1_000_000,
                        "end_us": 2_200_000,
                        "source_text": "你怎么会在这里？",
                        "speakers": [person_key] if speakers is None else speakers,
                    }],
                }],
            }],
        }],
    }


def _target_localization(project_id: str) -> dict:
    return {
        "schema_version": "target-localization-v1",
        "project_id": project_id,
        "source_fingerprint": "a" * 64,
        "target_language": "en-US",
        "target_region": "US",
        "scene_policy": "KEEP",
        "status": "READY",
        "target_character_count": 1,
        "scene_mapping_count": 0,
        "review_count": 0,
        "target_characters": [{
            "id": "TARGETCHAR_1",
            "project_id": project_id,
            "source_character_id": "CHAR_1",
            "source_character_name": "林晚",
            "source_character_signature": "b" * 64,
            "source_fingerprint": "a" * 64,
            "target_language": "en-US",
            "target_region": "US",
            "target_name": "Emma Miller",
            "appearance_profile": "American woman in her mid-20s, professional, long brown hair",
            "generation_prompt": "consistent American woman, mid-20s, professional, long brown hair",
            "confidence": 0.95,
            "status": "READY",
            "decision_source": "AI",
            "reference_assets": [],
            "created_at": "2026-09-01T00:00:00+00:00",
            "updated_at": "2026-09-01T00:00:00+00:00",
        }],
        "scene_mappings": [],
    }


def _seed(monkeypatch, tmp_path: Path, *, speakers: list[str] | None = None):
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
    snapshot = _snapshot(project["id"], episode_id, speakers=speakers)
    monkeypatch.setattr(target_dialogue_v1, "load_project_source_drama_snapshot_v1", lambda _project_id: snapshot)
    monkeypatch.setattr(target_dialogue_v1, "get_target_localization_v1", lambda _project_id: _target_localization(project["id"]))
    return project["id"], episode_id


def _translation(confidence: float = 0.95) -> dict:
    return {"dialogues": [{
        "source_dialogue_key": "EP_1:REV_1:H1:D1",
        "translated_text": "Why are you here?",
        "localized_text": "Why are you here?",
        "final_text": "Why are you here?",
        "confidence": confidence,
    }]}


def _write_wav(path: Path, *, seconds: float, rate: int = 16_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(round(seconds * rate))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames)


def test_target_dialogue_text_localizes_automatically(monkeypatch, tmp_path: Path) -> None:
    project_id, _episode_id = _seed(monkeypatch, tmp_path)
    monkeypatch.setattr(target_dialogue_v1, "request_local_qwen_json", lambda _prompt: _translation())

    bundle = target_dialogue_v1.generate_target_dialogue_text_v1(project_id)

    assert bundle["status"] == "TEXT_READY_AUDIO_PENDING"
    assert bundle["review_count"] == 0
    assert bundle["dialogues"][0]["final_text"] == "Why are you here?"
    assert bundle["dialogues"][0]["target_character_id"] == "TARGETCHAR_1"
    assert bundle["voice_profiles"][0]["status"] == "PLANNED"
    assert review_issue_v1.list_review_issues(project_id) == []


def test_low_confidence_dialogue_enters_review_and_manual_edit_closes_it(monkeypatch, tmp_path: Path) -> None:
    project_id, _episode_id = _seed(monkeypatch, tmp_path)
    monkeypatch.setattr(target_dialogue_v1, "request_local_qwen_json", lambda _prompt: _translation(0.45))

    bundle = target_dialogue_v1.generate_target_dialogue_text_v1(project_id)
    row = bundle["dialogues"][0]

    assert row["status"] == "REVIEW"
    issues = review_issue_v1.list_review_issues(project_id)
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "LOCALIZATION"

    updated = target_dialogue_v1.update_target_dialogue_v1(
        row["id"],
        translated_text="Why are you here?",
        localized_text="What are you doing here?",
        final_text="What are you doing here?",
    )

    assert updated["status"] == "READY"
    assert updated["decision_source"] == "MANUAL"
    assert updated["audio_status"] == "PENDING"
    assert updated["audio_path"] is None
    assert updated["speech_duration_us"] is None
    assert review_issue_v1.list_review_issues(project_id) == []


def test_unknown_speaker_does_not_duplicate_localization_review(monkeypatch, tmp_path: Path) -> None:
    project_id, _episode_id = _seed(monkeypatch, tmp_path, speakers=[])
    monkeypatch.setattr(target_dialogue_v1, "request_local_qwen_json", lambda _prompt: _translation())

    bundle = target_dialogue_v1.generate_target_dialogue_text_v1(project_id)

    assert bundle["dialogues"][0]["status"] == "REVIEW"
    assert bundle["dialogues"][0]["target_character_id"] is None
    assert review_issue_v1.list_review_issues(project_id) == []


def test_tts_not_configured_keeps_text_and_marks_audio_pending(monkeypatch, tmp_path: Path) -> None:
    project_id, _episode_id = _seed(monkeypatch, tmp_path)
    monkeypatch.setattr(target_dialogue_v1, "request_local_qwen_json", lambda _prompt: _translation())
    monkeypatch.setattr(target_dialogue_v1, "runtime_status", lambda: {"ready": False, "reachable": False})

    bundle = run_target_dialogue_pipeline_v1(project_id, synthesize_audio=True)

    assert bundle["status"] == "TEXT_READY_AUDIO_PENDING"
    assert bundle["dialogues"][0]["status"] == "READY"
    assert bundle["dialogues"][0]["audio_status"] == "NOT_CONFIGURED"
    assert bundle["dialogues"][0]["final_text"] == "Why are you here?"


def test_qwen3_tts_audio_duration_is_persisted(monkeypatch, tmp_path: Path) -> None:
    project_id, _episode_id = _seed(monkeypatch, tmp_path)
    monkeypatch.setattr(target_dialogue_v1, "request_local_qwen_json", lambda _prompt: _translation())
    monkeypatch.setattr(target_dialogue_v1, "runtime_status", lambda: {"ready": True, "reachable": True})

    def fake_design_voice_reference(*, output_path: Path, **_kwargs) -> None:
        _write_wav(output_path, seconds=0.6)

    def fake_synthesize_clone(*, output_path: Path, **_kwargs) -> None:
        _write_wav(output_path, seconds=1.25)

    monkeypatch.setattr(target_dialogue_v1, "design_voice_reference", fake_design_voice_reference)
    monkeypatch.setattr(target_dialogue_v1, "synthesize_clone", fake_synthesize_clone)

    bundle = run_target_dialogue_pipeline_v1(project_id, synthesize_audio=True)
    row = bundle["dialogues"][0]

    assert bundle["status"] == "READY"
    assert bundle["audio_ready_count"] == 1
    assert bundle["voice_profiles"][0]["status"] == "REFERENCE_READY"
    assert row["audio_status"] == "READY"
    assert row["speech_duration_us"] == 1_250_000
    assert Path(row["audio_path"]).is_file()
