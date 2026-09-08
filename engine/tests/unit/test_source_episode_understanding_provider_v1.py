from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import source_episode_understanding_provider_v1 as episode


class FakeGeminiTransport:
    def __init__(self) -> None:
        self.video_path: Path | None = None
        self.prompt = ""
        self.schema = None

    def understand_video(self, *, video_path: Path, prompt: str, response_schema):
        self.video_path = video_path
        self.prompt = prompt
        self.schema = response_schema
        return {
            "episode_summary": "女主发现合同真相并与男主发生冲突。",
            "source_world": {
                "era": "当代",
                "region": "中国城市",
                "social_context": "都市职场",
                "visual_world": "现代都市",
            },
            "story_beats": [
                {"beat_key": "BEAT_001", "summary": "发现合同", "start_time": "00:00", "end_time": "00:20"}
            ],
            "characters": [
                {
                    "character_key": "CHAR_CAND_001",
                    "display_name": "女主",
                    "aliases": [],
                    "identity_summary": "故事核心人物",
                    "appearance_summary": "年轻女性",
                    "role_in_story": "主角",
                    "first_seen_time": "00:00",
                }
            ],
            "relationships": [],
            "scenes": [
                {
                    "scene_key": "SCENE_CAND_001",
                    "name": "办公室",
                    "location_summary": "现代办公室",
                    "visual_summary": "办公桌与落地窗",
                    "story_function": "冲突发生地",
                    "time_ranges": ["00:00-00:20"],
                }
            ],
            "props": [
                {
                    "prop_key": "PROP_CAND_001",
                    "name": "合同",
                    "visual_summary": "纸质合同",
                    "story_function": "触发冲突",
                    "owner_or_user_character_keys": ["CHAR_CAND_001"],
                    "time_ranges": ["00:05-00:12"],
                }
            ],
            "script_scenes": [
                {
                    "scene_key": "SCENE_CAND_001",
                    "heading": "办公室 / 日 / 内",
                    "start_time": "00:00",
                    "end_time": "00:20",
                    "action_summary": "女主发现合同并质问。",
                    "character_keys": ["CHAR_CAND_001"],
                    "dialogue_evidence_ids": ["asr-1"],
                    "story_beat_keys": ["BEAT_001"],
                }
            ],
            "key_events": [
                {
                    "event_key": "EVENT_001",
                    "summary": "女主发现合同",
                    "time_range": "00:05-00:12",
                    "character_keys": ["CHAR_CAND_001"],
                    "scene_key": "SCENE_CAND_001",
                    "prop_keys": ["PROP_CAND_001"],
                }
            ],
            "unresolved": [],
        }, {"remote_file_name": "files/test-video", "usage_metadata": {"promptTokenCount": 123}}


def _context(tmp_path: Path):
    video = tmp_path / "episode.mp4"
    video.write_bytes(b"fake-video")
    return SimpleNamespace(
        run_id="RUN_1",
        project_id="PROJECT_1",
        episode_id="EPISODE_1",
        source_language="zh-CN",
        source_shot_revision_id="REV_1",
        source_video_path=str(video),
        source_sha256="a" * 64,
        audio_path=None,
        shots=(
            p2.P2ShotInput(
                revision_item_id="ITEM_1",
                original_shot_id="SHOT_1",
                ordinal=1,
                start_us=0,
                end_us=2_000_000,
                duration_us=2_000_000,
                reference_clip_path=str(video),
                thumbnail_path=None,
                keyframes=(),
            ),
        ),
    )


def _asr_artifact(tmp_path: Path) -> p2.P2EvidenceArtifact:
    path = tmp_path / "asr.json"
    path.write_text(json.dumps({
        "evidence": [{
            "source_type": "ASR_SEGMENT",
            "source_id": "asr-1",
            "source_start_us": 100_000,
            "source_end_us": 900_000,
            "text": "这份合同到底怎么回事？",
        }]
    }, ensure_ascii=False), encoding="utf-8")
    return p2.P2EvidenceArtifact(
        component="ASR",
        fingerprint="f" * 64,
        path=str(path),
        uri=path.resolve().as_uri(),
        evidence_count=1,
    )


def test_gemini_episode_provider_uses_full_video_and_source_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(tmp_path / "studio"))
    transport = FakeGeminiTransport()
    provider = episode.Gemini31ProEpisodeUnderstandingProvider(transport=transport)

    result = provider.analyze(_context(tmp_path), [_asr_artifact(tmp_path)])

    assert result.status == "READY"
    assert result.model == "gemini-3.1-pro-preview"
    assert result.data["characters"][0]["character_key"] == "CHAR_CAND_001"
    assert transport.video_path == tmp_path / "episode.mp4"
    assert "整集理解" in transport.prompt
    assert "这份合同到底怎么回事？" in transport.prompt
    assert "ShotAnchor 1" in transport.prompt
    assert result.metadata["canonical_dialogue_policy"] == episode.CANONICAL_DIALOGUE_POLICY
    assert result.metadata["input_fingerprint"]


def test_gemini_episode_provider_does_not_silently_run_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(tmp_path / "studio"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    provider = episode.Gemini31ProEpisodeUnderstandingProvider()

    result = provider.analyze(_context(tmp_path), [_asr_artifact(tmp_path)])

    assert result.status == "NOT_CONFIGURED"
    assert any("API key" in warning for warning in result.warnings)


def test_episode_schema_never_asks_gemini_to_author_canonical_dialogue():
    schema_text = json.dumps(episode._response_schema(), ensure_ascii=False).casefold()
    assert "dialogue_evidence_ids" in schema_text
    assert "dialogue_text" not in schema_text
    assert "canonical_dialogue" not in schema_text
