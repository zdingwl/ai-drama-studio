from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact, create_artifact_relation, expected_namespace
from app.projects.enums import ProjectType
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.skills.professional import get_professional_skill, get_professional_skill_detail
from app.skills.registry import get_root_skill
from app.source_snapshot import service
from app.source_snapshot.schemas import (
    P10_REQUIRED_ARTIFACT_TYPES,
    FrozenArtifactRef,
    SourceVideoSnapshotEpisodeProvenance,
    SourceVideoSnapshotProvenance,
)
from app.workflow.models import ProviderJob, Task


_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _project(client: TestClient) -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": "P10-contract",
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _frozen_refs() -> list[FrozenArtifactRef]:
    return [
        FrozenArtifactRef(
            artifact_type=artifact_type,
            artifact_id=f"artifact-{index}",
            revision=1,
            input_fingerprint=(f"{index:064x}"[-64:]),
        )
        for index, artifact_type in enumerate(P10_REQUIRED_ARTIFACT_TYPES, start=1)
    ]


def _episode_context() -> SimpleNamespace:
    return SimpleNamespace(
        episode=SimpleNamespace(
            id="episode-1",
            episode_order=1,
            duration_us=5_000_000,
            width=1080,
            height=1920,
            codec_name="h264",
            avg_frame_rate="25/1",
            has_audio=True,
        ),
        asset=SimpleNamespace(id="asset-1", original_filename="episode.mp4", sha256=_SHA_A),
        shot_boundary=SimpleNamespace(id="boundary-1", input_fingerprint=_SHA_B),
        evidence_set=SimpleNamespace(id="evidence-1", input_fingerprint="c" * 64),
        shot_anchors=[
            SimpleNamespace(
                id="shot-1",
                shot_number=1,
                start_us=0,
                end_us=5_000_000,
                duration_us=5_000_000,
            )
        ],
        dialogue=[
            SimpleNamespace(
                id="utt-1",
                utterance_number=1,
                start_us=1_000_000,
                end_us=2_000_000,
                text="这是 P6 canonical 台词",
                language="zh-CN",
            )
        ],
        visual_text=[
            SimpleNamespace(
                id="ocr-1",
                span_number=1,
                start_us=2_000_000,
                end_us=3_000_000,
                text="原片字幕",
                confidence=0.99,
            )
        ],
    )


def test_p10_professional_skill_and_root_contract_require_independent_speakers() -> None:
    skill = get_professional_skill("source-video-snapshot")
    detail = get_professional_skill_detail("source-video-snapshot")
    assert skill.version == "1.0.0"
    assert skill.required_capabilities == (Capability.SOURCE_SNAPSHOT,)
    assert skill.output_contracts == (ArtifactType.SOURCE_VIDEO_SNAPSHOT,)
    assert set(skill.required_inputs) == set(P10_REQUIRED_ARTIFACT_TYPES)
    assert ArtifactType.SOURCE_SPEAKERS in skill.required_inputs
    assert "SOURCE_SPEAKERS" in detail.manual
    rules = "\n".join(detail.provider_rules)
    assert "ProviderJob" in rules
    assert "GET" in rules
    assert "Target" in rules

    for project_type in (ProjectType.REPLICA, ProjectType.REDRAW):
        root = get_root_skill(project_type)
        assert "source-video-snapshot" in root.subskills
        finalize = next(step for step in root.steps if step.id == "source_finalize")
        assert set(finalize.requires) == set(P10_REQUIRED_ARTIFACT_TYPES)
        assert ArtifactType.SOURCE_SPEAKERS in finalize.requires
        assert finalize.produces == (ArtifactType.SOURCE_VIDEO_SNAPSHOT,)

    redraw = get_root_skill(ProjectType.REDRAW)
    source_breakdown = next(step for step in redraw.steps if step.id == "source_breakdown")
    assert ArtifactType.SOURCE_CHARACTERS in source_breakdown.produces
    assert ArtifactType.SOURCE_SPEAKERS in source_breakdown.produces
    assert ArtifactType.SOURCE_SCENES in source_breakdown.produces
    assert ArtifactType.SOURCE_PROPS in source_breakdown.produces


def test_p10_snapshot_stays_source_and_capability_is_available_after_real_acceptance() -> None:
    assert expected_namespace(ArtifactType.SOURCE_VIDEO_SNAPSHOT) == ArtifactNamespace.SOURCE
    assert CAPABILITY_BY_ID[Capability.SOURCE_SNAPSHOT].availability == CapabilityAvailability.AVAILABLE


def test_p10_provenance_rejects_provider_jobs_and_missing_speaker_input() -> None:
    refs = _frozen_refs()
    episode = SourceVideoSnapshotEpisodeProvenance(
        episode_id="episode-1",
        source_asset_id="asset-1",
        source_asset_sha256=_SHA_A,
        shot_boundary_set_id="boundary-1",
        shot_boundary_fingerprint=_SHA_B,
        source_evidence_set_id="evidence-1",
        source_evidence_fingerprint="c" * 64,
    )
    with pytest.raises(ValidationError):
        SourceVideoSnapshotProvenance(
            professional_skill_version="1.0.0",
            source_chain_fingerprint="d" * 64,
            frozen_artifacts=refs,
            episode_inputs=[episode],
            provider_jobs=[{"provider_job_id": "forbidden"}],
        )

    without_speakers = [item for item in refs if item.artifact_type != ArtifactType.SOURCE_SPEAKERS]
    with pytest.raises(ValidationError):
        SourceVideoSnapshotProvenance(
            professional_skill_version="1.0.0",
            source_chain_fingerprint="d" * 64,
            frozen_artifacts=without_speakers,
            episode_inputs=[episode],
        )


def test_p10_episode_freeze_copies_p5_and_p6_values_without_rewriting() -> None:
    context = _episode_context()
    frozen = service._snapshot_episodes(SimpleNamespace(p9=SimpleNamespace(contexts=[context])))
    assert len(frozen) == 1
    episode = frozen[0]
    assert episode.source_asset_sha256 == context.asset.sha256
    assert episode.shot_boundary_fingerprint == context.shot_boundary.input_fingerprint
    assert episode.source_evidence_fingerprint == context.evidence_set.input_fingerprint

    shot = episode.shot_anchors[0]
    assert (shot.shot_anchor_id, shot.start_us, shot.end_us, shot.duration_us) == (
        context.shot_anchors[0].id,
        context.shot_anchors[0].start_us,
        context.shot_anchors[0].end_us,
        context.shot_anchors[0].duration_us,
    )
    utterance = episode.canonical_dialogue[0]
    assert (utterance.utterance_id, utterance.start_us, utterance.end_us, utterance.text, utterance.language) == (
        context.dialogue[0].id,
        context.dialogue[0].start_us,
        context.dialogue[0].end_us,
        context.dialogue[0].text,
        context.dialogue[0].language,
    )
    visual_text = episode.canonical_visual_text[0]
    assert (visual_text.span_id, visual_text.start_us, visual_text.end_us, visual_text.text, visual_text.confidence) == (
        context.visual_text[0].id,
        context.visual_text[0].start_us,
        context.visual_text[0].end_us,
        context.visual_text[0].text,
        context.visual_text[0].confidence,
    )


def test_p10_source_chain_fingerprint_changes_for_speaker_or_frozen_revision(monkeypatch) -> None:
    class Dump:
        def __init__(self, value: object) -> None:
            self.value = value

        def model_dump(self, mode: str = "python") -> object:
            return deepcopy(self.value)

    refs = _frozen_refs()
    episode = service._snapshot_episodes(
        SimpleNamespace(p9=SimpleNamespace(contexts=[_episode_context()]))
    )[0]
    content = SimpleNamespace(
        frozen_artifacts=refs,
        episodes=[episode],
        source_bible=Dump({"bible": 1}),
        source_shot_facts=Dump({"facts": 1}),
        source_characters=Dump({"characters": 1}),
        source_speakers=Dump({"speakers": 1}),
        source_scenes=Dump({"scenes": 1}),
        source_props=Dump({"props": 1}),
    )
    baseline = service._source_chain_fingerprint(SimpleNamespace(), content)

    changed_speaker = deepcopy(content)
    changed_speaker.source_speakers = Dump({"speakers": 2})
    assert service._source_chain_fingerprint(SimpleNamespace(), changed_speaker) != baseline

    changed_ref = deepcopy(content)
    speaker_ref = next(item for item in changed_ref.frozen_artifacts if item.artifact_type == ArtifactType.SOURCE_SPEAKERS)
    speaker_ref.revision = 2
    speaker_ref.input_fingerprint = "f" * 64
    assert service._source_chain_fingerprint(SimpleNamespace(), changed_ref) != baseline


def test_p10_get_is_read_only_and_failed_post_creates_no_task_provider_or_artifact(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)

    def counts() -> tuple[int, int, int]:
        with session_factory() as db:
            return (
                int(db.scalar(select(func.count()).select_from(ArtifactNode)) or 0),
                int(db.scalar(select(func.count()).select_from(Task)) or 0),
                int(db.scalar(select(func.count()).select_from(ProviderJob)) or 0),
            )

    before = counts()
    result = client.get(f"/api/v3/projects/{project['id']}/source-video-snapshot")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "NOT_BUILT"
    assert counts() == before

    revisions = client.get(f"/api/v3/projects/{project['id']}/source-video-snapshot/revisions")
    assert revisions.status_code == 200, revisions.text
    assert revisions.json() == []
    assert counts() == before

    start = client.post(f"/api/v3/projects/{project['id']}/commands/source-video-snapshot")
    assert start.status_code == 409, start.text
    assert start.json()["error"]["code"] == "SOURCE_VIDEO_REQUIRED"
    assert counts() == before


def test_p10_upstream_speaker_revision_marks_snapshot_stale(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    with session_factory() as db:
        speakers_v1 = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_SPEAKERS,
            namespace=ArtifactNamespace.SOURCE,
            label="说话人归一 v1",
            input_fingerprint=_SHA_A,
            skill_id="speaker-attribution",
            skill_version="1.0.0",
        )
        snapshot = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_VIDEO_SNAPSHOT,
            namespace=ArtifactNamespace.SOURCE,
            label="原片分析定稿",
            input_fingerprint=_SHA_B,
            skill_id="source-video-snapshot",
            skill_version="1.0.0",
        )
        create_artifact_relation(
            db,
            project_id=project["id"],
            source_node_id=speakers_v1.id,
            target_node_id=snapshot.id,
            relation_type=ArtifactRelationType.CONTAINS,
        )

        create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.SOURCE_SPEAKERS,
            namespace=ArtifactNamespace.SOURCE,
            label="说话人归一 v2",
            input_fingerprint="c" * 64,
            skill_id="speaker-attribution",
            skill_version="1.0.0",
        )

        old_snapshot = db.get(ArtifactNode, snapshot.id)
        assert old_snapshot is not None
        assert old_snapshot.validity == ArtifactValidity.STALE
        assert old_snapshot.is_current is False


def test_p10_command_fails_before_freeze_when_migration_is_missing(monkeypatch) -> None:
    db = SimpleNamespace(get_bind=lambda: object())
    monkeypatch.setattr(service, "inspect", lambda _bind: SimpleNamespace(has_table=lambda _name: False))

    with pytest.raises(Exception) as captured:
        service._assert_storage_ready(db)

    assert getattr(captured.value, "code", None) == "P10_DATABASE_MIGRATION_REQUIRED"
