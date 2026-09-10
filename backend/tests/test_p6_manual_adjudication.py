import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.models import ArtifactNode
from app.core.config import get_settings
from app.evidence.models import AsrEvidenceSegment, OcrEvidenceObservation, SourceEvidenceSet, SourceVisualTextSpan
from app.evidence.providers import AsrSegmentResult, EvidenceProviders, OcrDetectionResult
from app.evidence.manual_adjudication import P6_MANUAL_ADJUDICATION_POLICY


class _FakeAsr:
    profile = {
        "provider": "fake-continuous-asr",
        "model": "manual-adjudication-test",
        "continuous_episode_input": True,
    }

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
                provenance={"provider": "fake", "raw_marker": "asr-preserved"},
            )
        ]


class _FakeOcr:
    profile = {"provider": "fake-timeline-ocr", "engine": "manual-adjudication-test"}

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


def _build_current_p6(client: TestClient, tmp_path: Path, monkeypatch) -> tuple[str, str, dict]:
    providers = EvidenceProviders(asr=_FakeAsr(), ocr=_FakeOcr())
    monkeypatch.setattr("app.evidence.service.build_evidence_providers", lambda settings: providers)

    project_response = client.post(
        "/api/v3/projects",
        json={
            "name": "P6-human-adjudication",
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert project_response.status_code == 201, project_response.text
    project_id = project_response.json()["id"]

    upload = client.post(
        f"/api/v3/projects/{project_id}/sources/videos",
        files=[("files", ("episode.mp4", _video(tmp_path / "episode.mp4"), "video/mp4"))],
    )
    assert upload.status_code == 201, upload.text
    episode_id = upload.json()[0]["id"]

    started = client.post(
        f"/api/v3/projects/{project_id}/episodes/{episode_id}/commands/source-evidence",
        headers={"Idempotency-Key": "p6-human-seed"},
    )
    assert started.status_code == 202, started.text
    task = client.get(f"/api/v3/projects/{project_id}/tasks/{started.json()['id']}").json()
    assert task["status"] == "succeeded"

    result = client.get(
        f"/api/v3/projects/{project_id}/episodes/{episode_id}/source-evidence"
    ).json()
    assert result["revision"] == 1
    assert result["dialogue"][0]["text"] == "乙阿姨"
    assert result["dialogue"][0]["text_source"] == "OCR_SUBTITLE_ADJUDICATED"
    return project_id, episode_id, result


def _adjudicate(
    client: TestClient,
    project_id: str,
    episode_id: str,
    *,
    key: str,
    payload: dict,
):
    return client.post(
        f"/api/v3/projects/{project_id}/episodes/{episode_id}/source-evidence/commands/adjudicate-dialogue",
        headers={"Idempotency-Key": key},
        json=payload,
    )


def test_user_can_choose_asr_ocr_and_custom_text_without_mutating_raw_evidence(
    client: TestClient,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id, episode_id, initial = _build_current_p6(client, tmp_path, monkeypatch)

    asr_choice = _adjudicate(
        client,
        project_id,
        episode_id,
        key="p6-human-asr",
        payload={
            "expected_revision": 1,
            "utterance_id": initial["dialogue"][0]["id"],
            "choice": "ASR",
        },
    )
    assert asr_choice.status_code == 201, asr_choice.text
    asr_result = asr_choice.json()
    assert asr_result["revision"] == 2
    assert asr_result["artifact_revision"] == 2
    assert asr_result["dialogue"][0]["text"] == "甲阿姨"
    assert asr_result["dialogue"][0]["text_source"] == "USER_ASR_SELECTED"
    assert asr_result["dialogue"][0]["asr_text"] == "甲阿姨"

    current_ocr_span = asr_result["visual_text"][0]["span_number"]
    ocr_choice = _adjudicate(
        client,
        project_id,
        episode_id,
        key="p6-human-ocr",
        payload={
            "expected_revision": 2,
            "utterance_id": asr_result["dialogue"][0]["id"],
            "choice": "OCR",
            "ocr_span_number": current_ocr_span,
        },
    )
    assert ocr_choice.status_code == 201, ocr_choice.text
    ocr_result = ocr_choice.json()
    assert ocr_result["revision"] == 3
    assert ocr_result["artifact_revision"] == 3
    assert ocr_result["dialogue"][0]["text"] == "乙阿姨"
    assert ocr_result["dialogue"][0]["text_source"] == "USER_OCR_SELECTED"
    assert ocr_result["dialogue"][0]["ocr_text"] == "乙阿姨"
    assert ocr_result["dialogue"][0]["ocr_span_numbers"] == [current_ocr_span]

    custom_choice = _adjudicate(
        client,
        project_id,
        episode_id,
        key="p6-human-custom",
        payload={
            "expected_revision": 3,
            "utterance_id": ocr_result["dialogue"][0]["id"],
            "choice": "CUSTOM",
            "custom_text": "人工确认后的台词",
        },
    )
    assert custom_choice.status_code == 201, custom_choice.text
    custom_result = custom_choice.json()
    assert custom_result["revision"] == 4
    assert custom_result["artifact_revision"] == 4
    assert custom_result["dialogue"][0]["text"] == "人工确认后的台词"
    assert custom_result["dialogue"][0]["text_source"] == "USER_EDITED"
    assert custom_result["dialogue"][0]["asr_text"] == "甲阿姨"
    assert custom_result["dialogue"][0]["adjudication_policy"] == P6_MANUAL_ADJUDICATION_POLICY

    with session_factory() as db:
        current_set = db.scalar(
            select(SourceEvidenceSet).where(
                SourceEvidenceSet.project_id == project_id,
                SourceEvidenceSet.episode_id == episode_id,
                SourceEvidenceSet.is_current.is_(True),
            )
        )
        assert current_set is not None
        assert current_set.revision == 4
        assert db.scalar(
            select(func.count(SourceEvidenceSet.id)).where(
                SourceEvidenceSet.project_id == project_id,
                SourceEvidenceSet.episode_id == episode_id,
            )
        ) == 4

        raw_asr = db.scalar(
            select(AsrEvidenceSegment).where(
                AsrEvidenceSegment.source_evidence_set_id == current_set.id
            )
        )
        assert raw_asr is not None
        assert raw_asr.text == "甲阿姨"
        assert raw_asr.provenance_json["raw_marker"] == "asr-preserved"
        assert raw_asr.provenance_json["manual_adjudication_policy"] == P6_MANUAL_ADJUDICATION_POLICY
        assert raw_asr.provenance_json["manual_original_asr_text"] == "甲阿姨"
        assert raw_asr.provenance_json["manual_canonical_text"] == "人工确认后的台词"

        raw_ocr_texts = list(
            db.scalars(
                select(OcrEvidenceObservation.text).where(
                    OcrEvidenceObservation.source_evidence_set_id == current_set.id
                )
            ).all()
        )
        assert raw_ocr_texts
        assert set(raw_ocr_texts) == {"乙阿姨"}

        dialogue_artifacts = list(
            db.scalars(
                select(ArtifactNode)
                .where(
                    ArtifactNode.project_id == project_id,
                    ArtifactNode.artifact_type == "SOURCE_DIALOGUE",
                )
                .order_by(ArtifactNode.revision)
            ).all()
        )
        assert [row.revision for row in dialogue_artifacts] == [1, 2, 3, 4]
        assert [row.is_current for row in dialogue_artifacts] == [False, False, False, True]
        assert [row.validity.value for row in dialogue_artifacts] == ["STALE", "STALE", "STALE", "CURRENT"]


def test_manual_adjudication_fails_closed_for_stale_revision_and_nonoverlapping_ocr(
    client: TestClient,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id, episode_id, initial = _build_current_p6(client, tmp_path, monkeypatch)

    stale = _adjudicate(
        client,
        project_id,
        episode_id,
        key="p6-human-stale",
        payload={
            "expected_revision": 99,
            "utterance_id": initial["dialogue"][0]["id"],
            "choice": "ASR",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "SOURCE_EVIDENCE_REVISION_CHANGED"

    span_number = initial["visual_text"][0]["span_number"]
    with session_factory() as db:
        current_set = db.scalar(
            select(SourceEvidenceSet).where(
                SourceEvidenceSet.project_id == project_id,
                SourceEvidenceSet.episode_id == episode_id,
                SourceEvidenceSet.is_current.is_(True),
            )
        )
        assert current_set is not None
        span = db.scalar(
            select(SourceVisualTextSpan).where(
                SourceVisualTextSpan.source_evidence_set_id == current_set.id,
                SourceVisualTextSpan.span_number == span_number,
            )
        )
        assert span is not None
        span.start_us = 1_500_000
        span.end_us = 1_900_000
        db.add(span)
        db.commit()

    nonoverlap = _adjudicate(
        client,
        project_id,
        episode_id,
        key="p6-human-nonoverlap",
        payload={
            "expected_revision": 1,
            "utterance_id": initial["dialogue"][0]["id"],
            "choice": "OCR",
            "ocr_span_number": span_number,
        },
    )
    assert nonoverlap.status_code == 422
    assert nonoverlap.json()["error"]["code"] == "SOURCE_EVIDENCE_OCR_SPAN_NOT_OVERLAPPING"

    after = client.get(
        f"/api/v3/projects/{project_id}/episodes/{episode_id}/source-evidence"
    ).json()
    assert after["revision"] == 1
