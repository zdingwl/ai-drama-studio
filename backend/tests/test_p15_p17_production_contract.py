from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace
from app.artifacts.models import ArtifactNode
from app.artifacts.service import expected_namespace
from app.p15.compiler import P15Inputs, _nearest_h3_ratio, compile_bundle
from app.p16.models import ReplicaGenerationAttempt, ReplicaGenerationSelectionCandidate
from app.p16.provider import MiniMaxH3Config, MiniMaxH3Provider
from app.p16.schemas import P16SelectionCandidateContent
from app.p17.media import write_srt
from app.p17.models import ReplicaFinalOutputRevision, ReplicaPostCandidate
from app.projects.enums import ProjectType
from app.shot_breakdown.schemas import CameraLanguage
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.skills.professional import get_professional_skill
from app.skills.registry import get_root_skill
from app.workflow.models import ProviderJob, Task


def _project(client: TestClient, project_type: str = "REPLICA") -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": f"Production-{project_type}",
            "project_type": project_type,
            "source_language": "zh-CN" if project_type in {"REPLICA", "REDRAW", "TRANSLATION"} else None,
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_root_p15_p17_contract_exists_but_capabilities_remain_planned() -> None:
    root = get_root_skill(ProjectType.REPLICA)
    assert root.version == "1.5.0"
    steps = {step.id: step for step in root.steps}
    assert steps["replica_storyboard"].requires == (
        ArtifactType.SOURCE_VIDEO_SNAPSHOT,
        ArtifactType.TARGET_BIBLE,
        ArtifactType.TARGET_SCRIPT,
        ArtifactType.TARGET_ASSETS,
        ArtifactType.TARGET_AUDIO,
        ArtifactType.TIMING_PLAN,
    )
    assert steps["generate"].produces == (ArtifactType.GENERATED_VIDEO, ArtifactType.GENERATION_SELECTION)
    assert steps["post"].requires == (
        ArtifactType.GENERATION_SELECTION,
        ArtifactType.TARGET_AUDIO,
        ArtifactType.TARGET_SCRIPT,
        ArtifactType.TIMING_PLAN,
    )
    assert steps["post"].produces == (ArtifactType.FINAL_OUTPUT,)

    assert get_professional_skill("storyboard-directing").required_capabilities == (Capability.STORYBOARD,)
    assert get_professional_skill("video-generation-qc").required_capabilities == (Capability.VIDEO_GENERATION, Capability.QC_SELECTION)
    assert get_professional_skill("post-production").required_capabilities == (Capability.LIP_SYNC, Capability.POST_PRODUCTION)
    for capability in (Capability.STORYBOARD, Capability.VIDEO_GENERATION, Capability.QC_SELECTION, Capability.LIP_SYNC, Capability.POST_PRODUCTION):
        assert CAPABILITY_BY_ID[capability].availability == CapabilityAvailability.PLANNED
    assert expected_namespace(ArtifactType.TARGET_STORYBOARD) == ArtifactNamespace.PRODUCTION
    assert expected_namespace(ArtifactType.GENERATION_SEGMENTS) == ArtifactNamespace.PRODUCTION
    assert expected_namespace(ArtifactType.GENERATED_VIDEO) == ArtifactNamespace.PRODUCTION
    assert expected_namespace(ArtifactType.GENERATION_SELECTION) == ArtifactNamespace.PRODUCTION
    assert expected_namespace(ArtifactType.FINAL_OUTPUT) == ArtifactNamespace.PRODUCTION


def test_p15_compiler_preserves_shot_timing_and_splits_long_shot(monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_P15_GENERATION_SEGMENT_MAX_DURATION_SECONDS", "6")
    camera = CameraLanguage(shot_size="MS", composition="centered", angle_or_type="eye-level", movement="static", focal_length_dof="normal")
    shot = SimpleNamespace(
        shot_anchor_id="anchor-1",
        shot_number=1,
        start_us=0,
        end_us=13_000_000,
        duration_us=13_000_000,
        visual_description="A quiet room",
        camera_language=camera,
        bindings=SimpleNamespace(characters=[], scenes=[], props=[]),
        dialogue=[],
        sound_effects=[],
        ambience=[],
    )
    source_snapshot = SimpleNamespace(
        episodes=[SimpleNamespace(episode_id="ep-1", width=1080, height=1920)],
        source_shot_facts=SimpleNamespace(episodes=[SimpleNamespace(episode_id="ep-1", episode_order=1, shots=[shot])]),
    )
    node = lambda value: SimpleNamespace(id=value, revision=1, input_fingerprint="a" * 64)
    inputs = P15Inputs(
        project_id="project",
        target_language="en-US",
        target_region="US",
        source_snapshot_artifact=node("snapshot"),
        source_snapshot=source_snapshot,
        target_bible_artifact=node("bible"),
        target_bible=SimpleNamespace(characters=[], scenes=[], props=[], continuity_rules=[]),
        target_script_artifact=node("script"),
        target_script=SimpleNamespace(episodes=[]),
        target_assets_artifact=node("assets"),
        target_assets=SimpleNamespace(characters=[], scenes=[], props=[], visual_style="source-like"),
        target_audio_artifact=node("audio"),
        target_audio=SimpleNamespace(clips=[]),
        timing_plan_artifact=node("timing"),
        timing_plan=SimpleNamespace(items=[]),
    )
    bundle = compile_bundle(inputs)
    assert len(bundle.storyboard.shots) == 1
    compiled = bundle.storyboard.shots[0]
    assert (compiled.start_us, compiled.end_us, compiled.duration_us) == (0, 13_000_000, 13_000_000)
    assert compiled.camera_language == camera
    assert [item.duration_us for item in bundle.generation_segments.segments] == [6_000_000, 6_000_000, 1_000_000]
    assert [item.output_ratio for item in bundle.generation_segments.segments] == ["9:16", "9:16", "9:16"]
    assert _nearest_h3_ratio(1920, 1080) == "16:9"


def test_h3_requested_duration_respects_provider_minimum_and_maximum() -> None:
    provider = MiniMaxH3Provider(MiniMaxH3Config(api_key="server-only", base_url="https://api.minimax.io", model="MiniMax-H3", resolution="768P", timeout_seconds=60, poll_interval_seconds=1))
    segment = SimpleNamespace(duration_us=1_000_000)
    assert provider.requested_duration(segment) == 4
    segment.duration_us = 14_200_000
    assert provider.requested_duration(segment) == 15
    max_provider = MiniMaxH3Provider(MiniMaxH3Config(api_key="server-only", base_url="https://api.minimax.io", model="MiniMax-H3-Max", resolution="768P", timeout_seconds=60, poll_interval_seconds=1))
    segment.duration_us = 1_000_000
    assert max_provider.requested_duration(segment) == 5


def test_p17_srt_uses_formal_utterance_numbers_and_timing(tmp_path: Path) -> None:
    path = tmp_path / "target.srt"
    write_srt(path, [(7, 1_250_000, 2_750_000, "Final target line")])
    text = path.read_text(encoding="utf-8")
    assert text.startswith("7\n00:00:01,250 --> 00:00:02,750\nFinal target line")


def test_p15_p17_get_routes_are_read_only_and_commands_fail_closed_without_hard_inputs(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)

    def counts() -> tuple[int, int, int, int, int]:
        with session_factory() as db:
            return (
                int(db.scalar(select(func.count()).select_from(ArtifactNode)) or 0),
                int(db.scalar(select(func.count()).select_from(Task)) or 0),
                int(db.scalar(select(func.count()).select_from(ProviderJob)) or 0),
                int(db.scalar(select(func.count()).select_from(ReplicaGenerationAttempt)) or 0),
                int(db.scalar(select(func.count()).select_from(ReplicaPostCandidate)) or 0),
            )

    before = counts()
    for path in (
        "target-storyboard",
        "generation-segments",
        "video-generation/attempts",
        "video-generation/candidates",
        "generation-selection",
        "post-production/candidates",
        "final-output",
    ):
        response = client.get(f"/api/v3/projects/{project['id']}/{path}")
        assert response.status_code == 200, (path, response.text)
    assert counts() == before

    p15 = client.post(f"/api/v3/projects/{project['id']}/commands/replica-storyboard", headers={"Idempotency-Key": "missing-p15"})
    assert p15.status_code == 409, p15.text
    p16 = client.post(f"/api/v3/projects/{project['id']}/commands/video-generation", headers={"Idempotency-Key": "missing-p16"})
    assert p16.status_code == 409, p16.text
    p17 = client.post(f"/api/v3/projects/{project['id']}/commands/post-production", headers={"Idempotency-Key": "missing-p17"})
    assert p17.status_code == 409, p17.text
    assert counts() == before


def test_production_tables_are_part_of_metadata(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(ReplicaGenerationSelectionCandidate)) == 0
        assert db.scalar(select(func.count()).select_from(ReplicaPostCandidate)) == 0
        assert db.scalar(select(func.count()).select_from(ReplicaFinalOutputRevision)) == 0
