from __future__ import annotations

from pathlib import Path

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import content_analysis_v2, studio_v2


def use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}", connect_args={"check_same_thread": False})
    studio_v2.Base.metadata.create_all(engine)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")


def seed_one_shot_project(monkeypatch, tmp_path: Path) -> tuple[str, str, str]:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(name="F05 测试", source_language="zh-CN", target_language="en-US", target_region="US")
    with studio_v2.get_session() as session:
        episode = studio_v2.Episode(
            id="EPISODE_1", project_id=project["id"], title="第一集", original_filename="e1.mp4",
            source_path=str(tmp_path / "e1.mp4"), source_sha256="a" * 64, sort_order=1,
        )
        session.add(episode)
        session.flush()
        session.add(studio_v2.Preprocess(
            id="PREPROCESS_1", episode_id=episode.id, status="READY",
            proxy_path=str(tmp_path / "proxy.mp4"), audio_path=str(tmp_path / "audio.wav"), media_info_json="{}",
        ))
        session.add(studio_v2.Shot(
            id="SHOT_1", episode_id=episode.id, ordinal=1, start_us=0, end_us=2_000_000,
            duration_us=2_000_000, reference_clip_path=str(tmp_path / "shot.mp4"), thumbnail_path=None,
            keyframes_json="[]", status="READY",
        ))
        session.commit()
    return project["id"], "EPISODE_1", "SHOT_1"


def test_f05_schema_keeps_ai_evidence_separate_from_final_entities() -> None:
    table_names = set(studio_v2.Base.metadata.tables)
    assert {
        "v2_content_analysis_runs",
        "v2_character_candidates",
        "v2_character_tracks",
        "v2_scene_candidates",
        "v2_shot_scene_evidence",
        "v2_prop_candidates",
        "v2_shot_prop_evidence",
        # 历史/后续 F06 兼容表继续保留，但新的 F05 Asset Run 不写入。
        "v2_speaker_segments",
        "v2_analysis_dialogues",
    } <= table_names
    assert "v2_characters" in table_names
    assert "v2_dialogues" in table_names


def test_asset_run_persists_scene_and_switches_current_without_running_dialogue(monkeypatch, tmp_path: Path) -> None:
    project_id, _episode_id, shot_id = seed_one_shot_project(monkeypatch, tmp_path)

    monkeypatch.setattr(content_analysis_v2, "analyze_characters", lambda shots: [])
    monkeypatch.setattr(content_analysis_v2, "_cluster_scenes", lambda run_id, project_id, shots: [
        content_analysis_v2.SceneDraft(id="SCENE_CANDIDATE_1", shot_ids=[shot_id], cover_path=None)
    ])

    # F05 新流程不允许意外触发 ASR / Speaker；如果调用就让测试直接失败。
    monkeypatch.setattr(content_analysis_v2, "_run_asr", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("F05 不应运行 ASR")))
    monkeypatch.setattr(content_analysis_v2, "_run_diarization", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("F05 不应运行 Speaker")))

    result = content_analysis_v2.run_content_analysis(project_id)
    assert result["is_current"] is True
    assert result["profile_version"] == "f05-assets-v2.3"
    assert result["counts"]["scene_candidates"] == 1
    assert result["counts"]["dialogues"] == 0
    assert result["dialogues"] == []
    assert result["component_status"]["props"] == "NOT_CONFIGURED"
    assert "asr" not in result["component_status"]
    assert "speaker" not in result["component_status"]

    current = content_analysis_v2.get_current_analysis(project_id)
    assert current is not None
    assert current["id"] == result["id"]

    with studio_v2.get_session() as session:
        shot = session.get(studio_v2.Shot, shot_id)
        assert shot is not None
        assert "场景候选" in (shot.short_description or "")
        assert "源对白" not in (shot.short_description or "")


def test_scene_clustering_never_crosses_episode_boundary(monkeypatch) -> None:
    descriptors = {
        "SHOT_A": np.asarray([1.0, 0.0], dtype=np.float32),
        "SHOT_B": np.asarray([1.0, 0.0], dtype=np.float32),
    }
    monkeypatch.setattr(content_analysis_v2, "_scene_descriptor", lambda path: descriptors[path])

    scenes = content_analysis_v2._cluster_scenes(
        "RUN",
        "PROJECT",
        [
            {
                "id": "SHOT_A", "episode_id": "EP_1", "episode_order": 1, "ordinal": 1,
                "thumbnail_path": "SHOT_A",
            },
            {
                "id": "SHOT_B", "episode_id": "EP_2", "episode_order": 2, "ordinal": 1,
                "thumbnail_path": "SHOT_B",
            },
        ],
    )

    assert len(scenes) == 2
    assert scenes[0].shot_ids == ["SHOT_A"]
    assert scenes[1].shot_ids == ["SHOT_B"]


def test_speaker_mapping_helper_remains_conservative_for_future_f06() -> None:
    candidate = content_analysis_v2.CandidateDraft(id="CHAR_A")
    candidate.tracks = [
        content_analysis_v2.TrackDraft(shot_id="SHOT_1", episode_id="EP_1", episode_order=1, shot_ordinal=1),
        content_analysis_v2.TrackDraft(shot_id="SHOT_2", episode_id="EP_1", episode_order=1, shot_ordinal=2),
    ]
    dialogues = [
        {"shot_id": "SHOT_1", "speaker_label": "SPEAKER_00", "speaker_candidate_id": None, "speaker_mapping_confidence": None},
        {"shot_id": "SHOT_2", "speaker_label": "SPEAKER_00", "speaker_candidate_id": None, "speaker_mapping_confidence": None},
    ]
    content_analysis_v2._map_speaker_to_character(dialogues, [candidate])
    assert all(item["speaker_candidate_id"] == "CHAR_A" for item in dialogues)
    assert all((item["speaker_mapping_confidence"] or 0) >= 0.60 for item in dialogues)
