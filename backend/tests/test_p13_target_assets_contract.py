import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import create_artifact
from app.projects.enums import ProjectType
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.skills.professional import get_professional_skill
from app.skills.registry import get_root_skill
from app.target_assets import service
from app.target_assets.models import ReplicaTargetAssetsCandidate, ReplicaTargetAssetsRevision
from app.target_assets.providers import (
    TargetAssetImageProviderResult,
    TargetAssetsSpecProviderResult,
)
from app.target_assets.schemas import (
    TargetAssetCandidateStatus,
    TargetAssetsSemantic,
    TargetCharacterAssetSemantic,
    TargetPropAssetSemantic,
    TargetSceneAssetSemantic,
)
from app.target_bible.models import ReplicaTargetRevision
from app.target_bible.schemas import (
    P11_SCHEMA_VERSION,
    ReplicaTargetBibleContent,
    ReplicaTargetCharacter,
    ReplicaTargetProp,
    ReplicaTargetScene,
    ReplicaTargetWorld,
    TargetBibleArtifactKind,
)
from app.workflow.models import ProviderJob, Task


_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _project(client: TestClient, project_type: str = "REPLICA") -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": f"P13-{project_type}",
            "project_type": project_type,
            "source_language": "zh-CN" if project_type in {"REPLICA", "REDRAW", "TRANSLATION"} else None,
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _bible_content(source_snapshot_artifact_id: str, *, suffix: str = "1") -> ReplicaTargetBibleContent:
    return ReplicaTargetBibleContent(
        target_language="en-US",
        target_region="US",
        source_snapshot_artifact_id=source_snapshot_artifact_id,
        target_world=ReplicaTargetWorld(
            setting_summary="美国城市公寓社区",
            cultural_context="美国本地生活语境",
            social_context="普通城市租住社区",
            localization_principles=["故事因果不变"],
        ),
        characters=[
            ReplicaTargetCharacter(
                target_character_id=f"tchar-{suffix}",
                source_character_id="source-char-1",
                source_display_name="徐然",
                display_name="Ryan",
                localized_identity="年轻上班族邻居",
                appearance_direction="现实主义都市休闲装",
                personality_constraints=["保持克制反击的故事功能"],
                continuity_rules=["脸型、发型和服装主色跨镜一致"],
            )
        ],
        scenes=[
            ReplicaTargetScene(
                target_scene_id=f"tscene-{suffix}",
                source_scene_id="source-scene-1",
                source_display_name="徐然家客厅",
                display_name="Ryan's Living Room",
                localized_setting="美国城市公寓客厅",
                visual_direction="现实主义住宅内景",
                continuity_rules=["门、沙发和入户动线固定"],
            )
        ],
        props=[
            ReplicaTargetProp(
                target_prop_id=f"tprop-{suffix}",
                source_prop_id="source-prop-1",
                source_display_name="货到付款包裹",
                display_name="COD Parcel",
                localized_form="本地快递货到付款纸箱",
                continuity_rules=["纸箱尺寸、胶带和标签布局固定"],
            )
        ],
        visual_style="现实主义竖屏短剧，可信自然光和生活化材质",
        continuity_rules=["人物、场景和关键道具必须跨镜保持同一视觉身份"],
        dialogue_style_rules=["自然美式口语"],
        adaptation_summary="只做文化视觉本土化，不改变故事功能。",
    )


def _install_target_bible(
    db: Session,
    *,
    project_id: str,
    suffix: str = "1",
    fingerprint: str = _SHA_A,
) -> tuple[ArtifactNode, ReplicaTargetBibleContent]:
    snapshot = db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == ArtifactType.SOURCE_VIDEO_SNAPSHOT.value,
            ArtifactNode.is_current.is_(True),
        )
    )
    if snapshot is None:
        snapshot = create_artifact(
            db,
            project_id=project_id,
            artifact_type=ArtifactType.SOURCE_VIDEO_SNAPSHOT,
            namespace=ArtifactNamespace.SOURCE,
            label="Source Snapshot",
            input_fingerprint=_SHA_A,
            skill_id="source-video-snapshot",
            skill_version="1.0.0",
        )
    content = _bible_content(snapshot.id, suffix=suffix)
    bible = create_artifact(
        db,
        project_id=project_id,
        artifact_type=ArtifactType.TARGET_BIBLE,
        namespace=ArtifactNamespace.TARGET,
        label=f"Target Bible {suffix}",
        input_fingerprint=fingerprint,
        skill_id="replica-target-bible",
        skill_version="1.0.0",
    )
    db.add(
        ReplicaTargetRevision(
            project_id=project_id,
            artifact_id=bible.id,
            artifact_kind=TargetBibleArtifactKind.TARGET_BIBLE.value,
            source_snapshot_artifact_id=snapshot.id,
            generated_by_task_id=None,
            schema_version=P11_SCHEMA_VERSION,
            content_json=content.model_dump(mode="json"),
            provenance_json={},
        )
    )
    db.commit()
    db.refresh(bible)
    return bible, content


class _FakeSpecProvider:
    provider_name = "fake-spec"
    model_name = "fake-spec-v1"

    def profile(self) -> dict:
        return {"provider": self.provider_name, "model": self.model_name, "mode": "TEST"}

    def design(self, payload) -> TargetAssetsSpecProviderResult:
        semantic = TargetAssetsSemantic(
            characters=[
                TargetCharacterAssetSemantic(
                    target_character_id=item["target_character_id"],
                    face_identity="oval face, warm brown eyes, straight brows",
                    hair_identity="short dark side-parted hair",
                    body_silhouette="lean average-height young adult",
                    wardrobe_baseline="navy overshirt, white tee, dark straight trousers",
                    signature_features=["thin silver watch", "clean-shaven face"],
                    palette_materials=["navy cotton", "white jersey", "dark denim"],
                    continuity_constraints=["watch remains on left wrist"],
                    generation_guidance=["neutral expression sheet with front, three-quarter and full-body views"],
                    negative_constraints=["no beard", "no hair color change", "no formal suit"],
                )
                for item in payload.characters
            ],
            scenes=[
                TargetSceneAssetSemantic(
                    target_scene_id=item["target_scene_id"],
                    spatial_identity="compact rectangular apartment living room connected to entry door",
                    layout="entry door camera-left, sofa on back wall, low table centered",
                    architecture_style="contemporary mid-market US apartment",
                    materials_palette=["warm oak", "off-white plaster", "charcoal fabric"],
                    fixed_landmarks=["blue-gray sofa", "oak entry console", "black floor lamp"],
                    lighting_baseline="soft daylight from right-side window with warm practical fill",
                    time_of_day_baseline="late afternoon",
                    continuity_constraints=["entry door and sofa positions never swap"],
                    generation_guidance=["wide reference plus layout callouts, no people"],
                    negative_constraints=["no luxury penthouse", "no layout mirror flip"],
                )
                for item in payload.scenes
            ],
            props=[
                TargetPropAssetSemantic(
                    target_prop_id=item["target_prop_id"],
                    visual_form="medium rectangular corrugated shipping carton with taped center seam",
                    materials=["brown corrugated cardboard", "clear packing tape", "paper label"],
                    color_palette=["kraft brown", "clear", "white label"],
                    scale="approximately 45 x 30 x 25 cm",
                    functional_identity="cash-on-delivery parcel that remains visibly identifiable",
                    signature_details=["white shipping label on top-right", "single clear tape seam"],
                    continuity_constraints=["label and tape placement remain fixed"],
                    generation_guidance=["front, top and three-quarter reference views on neutral sheet"],
                    negative_constraints=["no gift wrapping", "no damaged carton", "no brand logo"],
                )
                for item in payload.props
            ],
        )
        return TargetAssetsSpecProviderResult(semantic=semantic, remote_job_id="spec-remote-1")


class _FakeImageProvider:
    provider_name = "fake-image"
    model_name = "fake-image-v1"

    def __init__(self, *, fail_on_call: int | None = None):
        self.calls = 0
        self.fail_on_call = fail_on_call

    def profile(self) -> dict:
        return {"provider": self.provider_name, "model": self.model_name, "mode": "TEST_PNG"}

    def generate(self, payload) -> TargetAssetImageProviderResult:
        self.calls += 1
        if self.fail_on_call == self.calls:
            raise RuntimeError("simulated image failure")
        buffer = io.BytesIO()
        Image.new("RGB", (640, 640), (230, 230, 230)).save(buffer, format="PNG")
        return TargetAssetImageProviderResult(
            image_bytes=buffer.getvalue(),
            media_type="image/png",
            remote_job_id=f"image-remote-{self.calls}",
        )


def _fake_providers(image_provider: _FakeImageProvider | None = None) -> service.P13Providers:
    return service.P13Providers(spec=_FakeSpecProvider(), image=image_provider or _FakeImageProvider())


def test_p13_skill_keeps_only_target_bible_as_artifact_input_and_capability_planned() -> None:
    skill = get_professional_skill("replica-target-assets")
    assert skill.version == "1.0.0"
    assert skill.required_inputs == (ArtifactType.TARGET_BIBLE,)
    assert skill.readable_artifacts == (ArtifactType.TARGET_BIBLE,)
    assert skill.output_contracts == (ArtifactType.TARGET_ASSETS,)
    assert skill.required_capabilities == (Capability.TARGET_BIBLE, Capability.TARGET_SCRIPT)

    root = get_root_skill(ProjectType.REPLICA)
    step = next(item for item in root.steps if item.id == "target_assets")
    assert step.requires == (ArtifactType.TARGET_BIBLE,)
    assert step.produces == (ArtifactType.TARGET_ASSETS,)
    assert step.capabilities == (Capability.TARGET_ASSETS,)
    assert CAPABILITY_BY_ID[Capability.TARGET_ASSETS].availability == CapabilityAvailability.PLANNED
    for capability in (
        Capability.TTS,
        Capability.TIMING,
        Capability.STORYBOARD,
        Capability.VIDEO_GENERATION,
        Capability.QC_SELECTION,
        Capability.LIP_SYNC,
        Capability.POST_PRODUCTION,
    ):
        assert CAPABILITY_BY_ID[capability].availability == CapabilityAvailability.PLANNED


def test_p13_get_is_read_only_and_command_requires_current_target_bible(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)

    def counts() -> tuple[int, int, int, int]:
        with session_factory() as db:
            return (
                int(db.scalar(select(func.count()).select_from(ArtifactNode)) or 0),
                int(db.scalar(select(func.count()).select_from(Task)) or 0),
                int(db.scalar(select(func.count()).select_from(ProviderJob)) or 0),
                int(db.scalar(select(func.count()).select_from(ReplicaTargetAssetsCandidate)) or 0),
            )

    before = counts()
    result = client.get(f"/api/v3/projects/{project['id']}/target-assets")
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "NOT_BUILT"
    revisions = client.get(f"/api/v3/projects/{project['id']}/target-assets/revisions")
    assert revisions.status_code == 200, revisions.text
    assert revisions.json() == []
    assert counts() == before

    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-assets",
        headers={"Idempotency-Key": "p13-no-bible"},
        json={"target_asset_ids": []},
    )
    assert start.status_code == 409, start.text
    assert start.json()["error"]["code"] == "P13_TARGET_BIBLE_REQUIRED"
    assert counts() == before


def test_p13_generate_candidate_then_explicit_approval_and_targeted_regeneration(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(client)
    with session_factory() as db:
        bible, _ = _install_target_bible(db, project_id=project["id"])

    providers = _fake_providers()
    monkeypatch.setattr(service, "_providers", lambda inputs, settings=None: providers)
    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-assets",
        headers={"Idempotency-Key": "p13-first-generation"},
        json={"target_asset_ids": []},
    )
    assert start.status_code == 202, start.text

    read = client.get(f"/api/v3/projects/{project['id']}/target-assets")
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["status"] == "NOT_BUILT"
    candidate = body["latest_candidate"]
    assert candidate["status"] == "READY_FOR_REVIEW"
    assert len(candidate["content"]["character_assets"]) == 1
    assert len(candidate["content"]["scene_assets"]) == 1
    assert len(candidate["content"]["prop_assets"]) == 1

    with session_factory() as db:
        assert int(
            db.scalar(
                select(func.count()).select_from(ArtifactNode).where(
                    ArtifactNode.project_id == project["id"],
                    ArtifactNode.artifact_type == ArtifactType.TARGET_ASSETS.value,
                )
            )
            or 0
        ) == 0
        task = db.scalar(select(Task).where(Task.project_id == project["id"], Task.task_type == service.P13_TASK_TYPE))
        assert task is not None
        assert task.input_artifact_ids_json == [bible.id]
        assert int(db.scalar(select(func.count()).select_from(ProviderJob).where(ProviderJob.task_id == task.id)) or 0) == 4

    content = candidate["content"]
    all_assets = [*content["character_assets"], *content["scene_assets"], *content["prop_assets"]]
    for asset in all_assets:
        assert asset["asset_revision"] == 1
        assert len(asset["reference_assets"]) == 1
        reference_id = asset["reference_assets"][0]["reference_asset_id"]
        media = client.get(f"/api/v3/projects/{project['id']}/target-assets/references/{reference_id}")
        assert media.status_code == 200
        assert media.headers["content-type"].startswith("image/png")

    approved = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-assets/{candidate['candidate_id']}/approve",
        headers={"Idempotency-Key": "p13-approve-v1"},
    )
    assert approved.status_code == 200, approved.text
    approved_body = approved.json()
    assert approved_body["status"] == "CURRENT"
    assert approved_body["revision"] == 1
    current_id = approved_body["artifact_id"]
    stable_character_asset_id = approved_body["content"]["character_assets"][0]["target_asset_id"]

    approved_again = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-assets/{candidate['candidate_id']}/approve",
        headers={"Idempotency-Key": "p13-approve-v1-other-key"},
    )
    assert approved_again.status_code == 200, approved_again.text
    assert approved_again.json()["artifact_id"] == current_id
    assert approved_again.json()["revision"] == 1

    with session_factory() as db:
        edge = db.scalar(
            select(ArtifactEdge).where(
                ArtifactEdge.source_node_id == bible.id,
                ArtifactEdge.target_node_id == current_id,
                ArtifactEdge.relation_type == ArtifactRelationType.DERIVED_FROM,
            )
        )
        assert edge is not None
        assert db.scalar(select(ReplicaTargetAssetsRevision).where(ReplicaTargetAssetsRevision.artifact_id == current_id)) is not None

    second = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-assets",
        headers={"Idempotency-Key": "p13-character-regeneration"},
        json={"target_asset_ids": [stable_character_asset_id]},
    )
    assert second.status_code == 202, second.text
    pending = client.get(f"/api/v3/projects/{project['id']}/target-assets").json()
    assert pending["status"] == "CURRENT"
    second_candidate = pending["latest_candidate"]
    assert second_candidate["status"] == "READY_FOR_REVIEW"
    assert second_candidate["content"]["character_assets"][0]["target_asset_id"] == stable_character_asset_id
    assert second_candidate["content"]["character_assets"][0]["asset_revision"] == 2
    assert second_candidate["content"]["scene_assets"][0]["asset_revision"] == 1
    assert second_candidate["content"]["prop_assets"][0]["asset_revision"] == 1

    publish_v2 = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-assets/{second_candidate['candidate_id']}/approve",
        headers={"Idempotency-Key": "p13-approve-v2"},
    )
    assert publish_v2.status_code == 200, publish_v2.text
    assert publish_v2.json()["revision"] == 2
    new_id = publish_v2.json()["artifact_id"]
    assert new_id != current_id
    with session_factory() as db:
        old = db.get(ArtifactNode, current_id)
        new = db.get(ArtifactNode, new_id)
        assert old is not None and old.validity == ArtifactValidity.STALE and not old.is_current
        assert new is not None and new.validity == ArtifactValidity.CURRENT and new.is_current
        supersedes = db.scalar(
            select(ArtifactEdge).where(
                ArtifactEdge.source_node_id == new_id,
                ArtifactEdge.target_node_id == current_id,
                ArtifactEdge.relation_type == ArtifactRelationType.SUPERSEDES,
            )
        )
        assert supersedes is not None
    assert CAPABILITY_BY_ID[Capability.TARGET_ASSETS].availability == CapabilityAvailability.PLANNED


def test_p13_partial_image_failure_creates_no_candidate_or_current_artifact(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(client)
    with session_factory() as db:
        _install_target_bible(db, project_id=project["id"])
    providers = _fake_providers(_FakeImageProvider(fail_on_call=2))
    monkeypatch.setattr(service, "_providers", lambda inputs, settings=None: providers)

    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-assets",
        headers={"Idempotency-Key": "p13-partial-failure"},
        json={"target_asset_ids": []},
    )
    assert start.status_code == 202, start.text
    with session_factory() as db:
        task = db.scalar(select(Task).where(Task.project_id == project["id"], Task.task_type == service.P13_TASK_TYPE))
        assert task is not None and task.status == "FAILED"
        assert int(db.scalar(select(func.count()).select_from(ReplicaTargetAssetsCandidate)) or 0) == 0
        assert int(
            db.scalar(
                select(func.count()).select_from(ArtifactNode).where(
                    ArtifactNode.project_id == project["id"],
                    ArtifactNode.artifact_type == ArtifactType.TARGET_ASSETS.value,
                )
            )
            or 0
        ) == 0
        jobs = list(db.scalars(select(ProviderJob).where(ProviderJob.task_id == task.id)).all())
        assert len(jobs) == 3
        assert any(job.status == "FAILED" for job in jobs)


def test_p13_target_bible_revision_stales_candidate_or_published_assets(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(client)
    with session_factory() as db:
        _install_target_bible(db, project_id=project["id"], suffix="1", fingerprint=_SHA_A)
    monkeypatch.setattr(service, "_providers", lambda inputs, settings=None: _fake_providers())

    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-assets",
        headers={"Idempotency-Key": "p13-stale-candidate"},
        json={"target_asset_ids": []},
    )
    assert start.status_code == 202, start.text
    candidate_id = client.get(f"/api/v3/projects/{project['id']}/target-assets").json()["latest_candidate"]["candidate_id"]

    with session_factory() as db:
        _install_target_bible(db, project_id=project["id"], suffix="2", fingerprint=_SHA_B)

    stale_read = client.get(f"/api/v3/projects/{project['id']}/target-assets")
    assert stale_read.status_code == 200, stale_read.text
    assert stale_read.json()["latest_candidate"]["status"] == TargetAssetCandidateStatus.STALE.value
    rejected = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-assets/{candidate_id}/approve",
        headers={"Idempotency-Key": "p13-stale-approval"},
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["error"]["code"] == "P13_CANDIDATE_STALE"
