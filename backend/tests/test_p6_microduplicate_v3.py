import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.evidence.models import AsrEvidenceSegment, SourceEvidenceSet
from app.evidence.providers import AsrSegmentResult, EvidenceProviders
from app.evidence.service_v3 import (
    P6_CANONICAL_GUARD,
    P6_CANONICAL_POLICY,
    P6_PROFILE_VERSION,
    _canonical_dialogue,
)


def _segment(start_us: int, end_us: int, text: str) -> AsrSegmentResult:
    return AsrSegmentResult(
        start_us=start_us,
        end_us=end_us,
        text=text,
        language="zh",
        confidence=0.95,
        provenance={"provider": "fake"},
    )


def test_p6_v3_short_nonduplicate_is_not_rejected() -> None:
    dialogue = _canonical_dialogue([_segment(0, 60_000, "快走")])
    assert [(item.start_us, item.end_us, item.text) for item in dialogue] == [
        (0, 60_000, "快走")
    ]


def test_p6_v3_plausible_adjacent_duplicate_is_not_rejected() -> None:
    dialogue = _canonical_dialogue(
        [
            _segment(0, 500_000, "真的要走"),
            _segment(520_000, 1_020_000, "真的要走"),
        ]
    )
    assert [item.text for item in dialogue] == ["真的要走", "真的要走"]


def test_p6_v3_rejects_only_implausible_copy_next_to_plausible_duplicate() -> None:
    dialogue = _canonical_dialogue(
        [
            _segment(0, 500_000, "这是完整一句话"),
            _segment(500_000, 600_000, "这是完整一句话"),
        ]
    )
    assert [(item.start_us, item.end_us, item.text, item.segment_indexes) for item in dialogue] == [
        (0, 500_000, "这是完整一句话", [0])
    ]


def test_p6_v3_rejects_both_adjacent_duplicate_microsegments_when_both_implausible() -> None:
    dialogue = _canonical_dialogue(
        [
            _segment(0, 20_000, "这是完整一句话"),
            _segment(20_000, 200_000, "这是完整一句话"),
        ]
    )
    assert dialogue == []


class _MicroAsrProvider:
    profile = {
        "provider": "fake-continuous-asr",
        "model": "microduplicate-test",
        "continuous_episode_input": True,
    }

    def transcribe(
        self,
        source_path: Path,
        *,
        language_hint: str | None,
        duration_us: int,
        on_progress=None,
    ) -> list[AsrSegmentResult]:
        if on_progress is not None:
            on_progress(1.0)
        return [
            _segment(200_000, 700_000, "正常对白"),
            _segment(1_500_000, 1_520_000, "这是完整一句话"),
            _segment(1_520_000, 1_700_000, "这是完整一句话"),
        ]


class _EmptyOcrProvider:
    profile = {"provider": "fake-empty-ocr", "engine": "test"}

    def recognize(self, image: object) -> list:
        return []


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


def test_p6_v3_keeps_rejected_microsegments_as_auditable_raw_evidence(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
    session_factory: sessionmaker[Session],
) -> None:
    project_response = client.post(
        "/api/v3/projects",
        json={
            "name": "P6-v3-microduplicate",
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()
    upload = client.post(
        f"/api/v3/projects/{project['id']}/sources/videos",
        files=[("files", ("episode.mp4", _video(tmp_path / "episode.mp4"), "video/mp4"))],
    )
    assert upload.status_code == 201
    episode = upload.json()[0]

    providers = EvidenceProviders(asr=_MicroAsrProvider(), ocr=_EmptyOcrProvider())
    monkeypatch.setattr(
        "app.evidence.service.build_evidence_providers",
        lambda settings: providers,
    )

    started = client.post(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/commands/source-evidence",
        headers={"Idempotency-Key": "p6-v3-microduplicate"},
    )
    assert started.status_code == 202, started.text
    task_id = started.json()["id"]
    task = client.get(f"/api/v3/projects/{project['id']}/tasks/{task_id}").json()
    assert task["status"] == "succeeded"

    result = client.get(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/source-evidence"
    ).json()
    assert result["raw_asr_segment_count"] == 3
    assert result["dialogue_count"] == 1
    assert [item["text"] for item in result["dialogue"]] == ["正常对白"]

    with session_factory() as db:
        evidence_set = db.scalar(
            select(SourceEvidenceSet).where(
                SourceEvidenceSet.project_id == project["id"],
                SourceEvidenceSet.episode_id == episode["id"],
                SourceEvidenceSet.is_current.is_(True),
            )
        )
        assert evidence_set is not None
        assert evidence_set.sampling_hints_json["canonical_dialogue_policy"] == P6_CANONICAL_POLICY
        assert evidence_set.sampling_hints_json["canonical_guard"] == P6_CANONICAL_GUARD
        assert evidence_set.sampling_hints_json["canonical_excluded_asr_segment_count"] == 2
        rows = list(
            db.scalars(
                select(AsrEvidenceSegment)
                .where(AsrEvidenceSegment.source_evidence_set_id == evidence_set.id)
                .order_by(AsrEvidenceSegment.segment_number)
            ).all()
        )
        assert [row.provenance_json["canonical_included"] for row in rows] == [True, False, False]
        assert rows[1].provenance_json["canonical_exclusion_reason"] == (
            "IMPLAUSIBLE_ADJACENT_DUPLICATE_MICROSEGMENT"
        )
        assert rows[2].provenance_json["canonical_exclusion_reason"] == (
            "IMPLAUSIBLE_ADJACENT_DUPLICATE_MICROSEGMENT"
        )

    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    evidence = next(
        node
        for node in graph["nodes"]
        if node["artifact_type"] == "SOURCE_DIALOGUE" and node["is_current"]
    )
    assert evidence["metadata_json"]["evidence_profile"] == P6_PROFILE_VERSION
    assert evidence["metadata_json"]["canonical_policy"] == P6_CANONICAL_POLICY
