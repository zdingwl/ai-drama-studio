import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.models import ArtifactNode
from app.core.config import get_settings
from app.evidence import service as base_service
from app.evidence.models import AsrEvidenceSegment
from app.evidence.providers import AsrSegmentResult, EvidenceProviders, OcrDetectionResult
from app.evidence.service_v4 import (
    P6_CANONICAL_POLICY,
    P6_PROFILE_VERSION,
    P6_TEXT_ADJUDICATION_POLICY,
    _adjudicate_dialogue_texts,
)


def _utterance(text: str = "甲阿姨"):
    return base_service.CanonicalUtterance(
        start_us=200_000,
        end_us=1_200_000,
        text=text,
        language="zh",
        segment_indexes=[0],
    )


def _visual(
    text: str,
    *,
    confidence: float = 0.99,
    start_us: int = 0,
    end_us: int = 1_500_000,
    y: int = 140,
):
    return base_service.CanonicalVisualSpan(
        start_us=start_us,
        end_us=end_us,
        text=text,
        confidence=confidence,
        bbox=[[10, y - 10], [100, y - 10], [100, y + 10], [10, y + 10]],
        observation_indexes=[0],
    )


def test_v4_adjudicates_single_high_confidence_subtitle_near_match() -> None:
    dialogue, audits = _adjudicate_dialogue_texts(
        [_utterance("甲阿姨")],
        [_visual("乙阿姨")],
        180,
    )

    assert dialogue[0].text == "乙阿姨"
    decision = audits[0]
    assert decision.asr_text == "甲阿姨"
    assert decision.canonical_text == "乙阿姨"
    assert decision.text_source == "OCR_SUBTITLE_ADJUDICATED"
    assert decision.ocr_span_numbers == [1]
    assert decision.edit_distance == 1
    assert decision.reason == "HIGH_CONFIDENCE_TEMPORAL_SUBTITLE_NEAR_MATCH"


def test_v4_does_not_rewrite_for_exact_weak_upper_or_non_overlapping_ocr() -> None:
    exact, exact_audits = _adjudicate_dialogue_texts([_utterance()], [_visual("甲阿姨")], 180)
    assert exact[0].text == "甲阿姨"
    assert exact_audits[0].text_source == "ASR"
    assert exact_audits[0].reason == "HIGH_CONFIDENCE_SUBTITLE_CORROBORATION"

    weak, weak_audits = _adjudicate_dialogue_texts(
        [_utterance()],
        [_visual("乙阿姨", confidence=0.70)],
        180,
    )
    assert weak[0].text == "甲阿姨" and weak_audits == {}

    upper, upper_audits = _adjudicate_dialogue_texts(
        [_utterance()],
        [_visual("乙阿姨", y=40)],
        180,
    )
    assert upper[0].text == "甲阿姨" and upper_audits == {}

    late, late_audits = _adjudicate_dialogue_texts(
        [_utterance()],
        [_visual("乙阿姨", start_us=1_300_000, end_us=1_700_000)],
        180,
    )
    assert late[0].text == "甲阿姨" and late_audits == {}


def test_v4_keeps_asr_when_distinct_subtitle_candidates_conflict() -> None:
    dialogue, audits = _adjudicate_dialogue_texts(
        [_utterance("甲阿姨")],
        [_visual("乙阿姨"), _visual("丙阿姨")],
        180,
    )

    assert dialogue[0].text == "甲阿姨"
    assert audits[0].text_source == "ASR"
    assert audits[0].reason == "AMBIGUOUS_OCR_SUBTITLE_CANDIDATES"
    assert audits[0].ocr_span_numbers == [1, 2]


class _FakeAsr:
    profile = {"provider": "fake-continuous-asr", "model": "test", "continuous_episode_input": True}

    def transcribe(self, source_path, *, language_hint, duration_us, on_progress=None):
        if on_progress is not None:
            on_progress(1.0)
        return [
            AsrSegmentResult(
                start_us=200_000,
                end_us=1_200_000,
                text="甲阿姨",
                language="zh",
                confidence=0.91,
                provenance={"provider": "fake", "raw_marker": "preserve-me"},
            )
        ]


class _FakeOcr:
    profile = {"provider": "fake-timeline-ocr", "engine": "test"}

    def recognize(self, image):
        return [
            OcrDetectionResult(
                text="乙阿姨",
                confidence=0.99,
                bbox=[[10, 120], [100, 120], [100, 160], [10, 160]],
            )
        ]


def _video(path: Path) -> bytes:
    subprocess.run(
        [
            get_settings().ffmpeg_binary,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:d=2:r=12",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2:sample_rate=16000",
            "-shortest",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )
    return path.read_bytes()


def test_v4_api_persists_corrected_canonical_but_preserves_raw_asr_audit(
    client: TestClient,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    providers = EvidenceProviders(asr=_FakeAsr(), ocr=_FakeOcr())
    monkeypatch.setattr("app.evidence.service.build_evidence_providers", lambda settings: providers)

    project_response = client.post(
        "/api/v3/projects",
        json={
            "name": "P6-v4-adjudication",
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]
    upload = client.post(
        f"/api/v3/projects/{project_id}/sources/videos",
        files=[("files", ("episode.mp4", _video(tmp_path / "episode.mp4"), "video/mp4"))],
    )
    assert upload.status_code == 201
    episode_id = upload.json()[0]["id"]

    task = client.post(
        f"/api/v3/projects/{project_id}/episodes/{episode_id}/commands/source-evidence",
        headers={"Idempotency-Key": "p6-v4-adjudication"},
    )
    assert task.status_code == 202
    task_id = task.json()["id"]
    task_read = client.get(f"/api/v3/projects/{project_id}/tasks/{task_id}").json()
    assert task_read["status"] == "succeeded"

    result = client.get(
        f"/api/v3/projects/{project_id}/episodes/{episode_id}/source-evidence"
    ).json()
    assert result["status"] == "CURRENT"
    assert result["dialogue_count"] == 1
    line = result["dialogue"][0]
    assert line["text"] == "乙阿姨"
    assert line["text_source"] == "OCR_SUBTITLE_ADJUDICATED"
    assert line["asr_text"] == "甲阿姨"
    assert line["ocr_text"] == "乙阿姨"
    assert line["ocr_span_numbers"]
    assert line["adjudication_policy"] == P6_TEXT_ADJUDICATION_POLICY

    with session_factory() as db:
        raw = db.scalar(select(AsrEvidenceSegment).where(AsrEvidenceSegment.project_id == project_id))
        assert raw is not None
        assert raw.text == "甲阿姨"
        assert raw.provenance_json["raw_marker"] == "preserve-me"
        assert raw.provenance_json["canonical_policy"] == P6_CANONICAL_POLICY
        assert raw.provenance_json["canonical_text_source"] == "OCR_SUBTITLE_ADJUDICATED"
        assert raw.provenance_json["canonical_asr_text"] == "甲阿姨"
        assert raw.provenance_json["canonical_text"] == "乙阿姨"
        assert raw.provenance_json["canonical_adjudication_policy"] == P6_TEXT_ADJUDICATION_POLICY

        artifact = db.scalar(
            select(ArtifactNode).where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == "SOURCE_DIALOGUE",
                ArtifactNode.is_current.is_(True),
            )
        )
        assert artifact is not None
        assert artifact.metadata_json["evidence_profile"] == P6_PROFILE_VERSION
        assert artifact.metadata_json["canonical_policy"] == P6_CANONICAL_POLICY
