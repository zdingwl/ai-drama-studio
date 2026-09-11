from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import create_artifact, create_artifact_relation, expected_namespace
from app.core.errors import AppError
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.skills.professional import get_professional_skill
from app.skills.registry import get_root_skill
from app.target_assets import service
from app.target_assets.models import ReplicaTargetAssetsCandidate, ReplicaTargetAssetsRevision
from app.target_assets.schemas import (
    CandidateReviewStatus,
    ProviderCharacterAssetSemantic,
    ProviderPropAssetSemantic,
    ProviderSceneAssetSemantic,
    ReplicaTargetAssetsContent,
    TargetAssetsCandidateProvenance,
    TargetAssetsProviderJobProvenance,
    TargetAssetsReviewCommand,
    TargetAssetsSemantic,
)
from app.target_bible.models import ReplicaTargetRevision
from app.target_bible.schemas import (
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
_SHA_C = "c" * 64


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


def _bible(source_snapshot_artifact_id: str = "snapshot-1") -> ReplicaTargetBibleContent:
    return ReplicaTargetBibleContent(
        target_language="en-US",
        target_region="US",
        source_snapshot_artifact_id=source_snapshot_artifact_id,
        target_world=ReplicaTargetWorld(
            setting_summary="Contemporary US apartment community.",
            cultural_context="US urban neighborhood etiquette.",
            social_context="Neighbors, delivery services and household conflict.",
            localization_principles=["Preserve story function", "Use natural US visual context"],
        ),
        characters=[
            ReplicaTargetCharacter(
                target_character_id="tchr_alice",
                source_character_id="src_chr_1",
                source_display_name="徐然",
                display_name="Alice",
                localized_identity="Young urban professional and apartment resident",
                appearance_direction="Grounded contemporary American urban styling",
                personality_constraints=["Direct but controlled"],
                continuity_rules=["Keep the same face identity", "Keep baseline wardrobe coherent"],
            )
        ],
        scenes=[
            ReplicaTargetScene(
                target_scene_id="tscn_hallway",
                source_scene_id="src_scn_1",
                source_display_name="居民楼公共楼道",
                display_name="Apartment Hallway",
                localized_setting="Middle-class US apartment corridor",
                visual_direction="Realistic residential corridor with unit doors and practical lighting",
                continuity_rules=["Door placement and corridor width remain fixed"],
            )
        ],
        props=[
            ReplicaTargetProp(
                target_prop_id="tprop_bouquet",
                source_prop_id="src_prop_1",
                source_display_name="蓝色玫瑰花束",
                display_name="Blue Rose Bouquet",
                localized_form="A wrapped blue rose bouquet with the same story function",
                continuity_rules=["Keep bouquet size and wrapping identity stable"],
            )
        ],
        visual_style="Naturalistic contemporary drama, controlled contrast and realistic materials",
        continuity_rules=["Keep all principal visual identities stable across shots"],
        dialogue_style_rules=["Natural spoken US English"],
        adaptation_summary="Localize the visual world without changing story or rhythm.",
    )


def _semantic(face: str = "Oval face, straight brows, warm medium skin tone") -> TargetAssetsSemantic:
    return TargetAssetsSemantic(
        characters=[
            ProviderCharacterAssetSemantic(
                target_character_id="tchr_alice",
                demographic_direction="Late-20s urban professional; grounded, contemporary presentation",
                face_direction=face,
                hair_direction="Shoulder-length dark brown hair, consistent center-left part",
                body_direction="Average-height lean build with relaxed upright posture",
                wardrobe_baseline="Neutral tailored work-casual blouse, dark trousers, minimal jewelry",
                signature_visual_features=["straight brows", "center-left hair part", "small silver stud earrings"],
                continuity_constraints=["Do not change facial proportions between shots"],
                generation_guidance=["Maintain realistic skin texture and stable facial geometry"],
                negative_constraints=["No hairstyle swaps", "No age drift", "No costume genre shift"],
            )
        ],
        scenes=[
            ProviderSceneAssetSemantic(
                target_scene_id="tscn_hallway",
                layout="Long straight corridor; apartment doors on both sides; elevator lobby at one end",
                architecture_style="Contemporary mid-rise US apartment building",
                interior_exterior_style="Interior residential common corridor",
                materials_palette=["warm off-white painted drywall", "dark wood veneer doors", "charcoal carpet"],
                fixed_landmarks=["elevator lobby", "red fire-alarm pull station", "unit-number plaques"],
                lighting_baseline="Warm-neutral ceiling fixtures with soft practical falloff",
                time_of_day_baseline="Interior baseline independent of exterior daylight",
                continuity_constraints=["Keep elevator, doors and fire alarm in fixed relative positions"],
                generation_guidance=["Preserve corridor vanishing point and unit-door spacing"],
                negative_constraints=["No luxury hotel redesign", "No corridor topology changes"],
            )
        ],
        props=[
            ProviderPropAssetSemantic(
                target_prop_id="tprop_bouquet",
                visual_form="Compact hand-held bouquet of saturated blue roses in matte paper wrap",
                materials=["fresh rose petals", "matte florist paper", "cotton ribbon"],
                color_palette=["royal blue", "charcoal gray", "off-white"],
                scale_reference="Approximately forearm length; comfortably held in one hand",
                signature_visual_features=["blue roses", "charcoal wrap", "off-white ribbon"],
                continuity_constraints=["Keep flower count impression, wrap geometry and ribbon identity stable"],
                generation_guidance=["Render believable petal texture and consistent bouquet silhouette"],
                negative_constraints=["No red roses", "No oversized wedding bouquet", "No vase"],
            )
        ],
    )


def _compose_inputs(*, base: ReplicaTargetAssetsContent | None = None) -> service.P13Inputs:
    return service.P13Inputs(
        project=SimpleNamespace(id="project-1", target_language="en-US", target_region="US"),
        target_bible_artifact=SimpleNamespace(id="bible-1", revision=4, input_fingerprint=_SHA_A),
        target_bible_revision=SimpleNamespace(),
        target_bible=_bible(),
        base_target_assets_artifact=(
            SimpleNamespace(id="assets-1", revision=1, input_fingerprint=_SHA_B) if base is not None else None
        ),
        base_target_assets=base,
    )


def _seed_target_bible(db: Session, project_id: str) -> ArtifactNode:
    snapshot = create_artifact(
        db,
        project_id=project_id,
        artifact_type=ArtifactType.SOURCE_VIDEO_SNAPSHOT,
        namespace=ArtifactNamespace.SOURCE,
        label="Snapshot",
        input_fingerprint=_SHA_A,
        skill_id="source-video-snapshot",
        skill_version="1.0.0",
    )
    bible = create_artifact(
        db,
        project_id=project_id,
        artifact_type=ArtifactType.TARGET_BIBLE,
        namespace=ArtifactNamespace.TARGET,
        label="Target Bible",
        input_fingerprint=_SHA_B,
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
            schema_version="1.0",
            content_json=_bible(snapshot.id).model_dump(mode="json"),
            provenance_json={"test": True},
        )
    )
    db.commit()
    db.refresh(bible)
    return bible


def _seed_candidate(db: Session, project_id: str, bible: ArtifactNode) -> ReplicaTargetAssetsCandidate:
    project = get_project(db, project_id)
    inputs = service.P13Inputs(
        project=project,
        target_bible_artifact=bible,
        target_bible_revision=db.scalar(
            select(ReplicaTargetRevision).where(ReplicaTargetRevision.artifact_id == bible.id)
        ),
        target_bible=ReplicaTargetBibleContent.model_validate(
            db.scalar(select(ReplicaTargetRevision).where(ReplicaTargetRevision.artifact_id == bible.id)).content_json
        ),
        base_target_assets_artifact=None,
        base_target_assets=None,
    )
    content = service._compose(inputs, _semantic())
    provider_job = TargetAssetsProviderJobProvenance(
        provider_job_id="provider-job-test",
        provider="test-provider",
        model="test-model",
        capability=Capability.TARGET_ASSETS.value,
        professional_skill_id="replica-target-assets",
        payload_fingerprint=_SHA_C,
    )
    provenance = TargetAssetsCandidateProvenance(
        target_bible_artifact_id=bible.id,
        target_bible_revision=bible.revision,
        target_bible_fingerprint=bible.input_fingerprint,
        target_language="en-US",
        target_region="US",
        generation_sequence=1,
        generation_base_fingerprint=_SHA_A,
        professional_skill_version="1.1.0",
        provider="test-provider",
        model="test-model",
        provider_job=provider_job,
        generated_by_task_id="test-task",
    )
    candidate = ReplicaTargetAssetsCandidate(
        project_id=project_id,
        target_bible_artifact_id=bible.id,
        base_target_assets_artifact_id=None,
        generated_by_task_id=None,
        generation_sequence=1,
        input_fingerprint=_SHA_A,
        schema_version="1.0",
        content_json=content.model_dump(mode="json"),
        provenance_json=provenance.model_dump(mode="json"),
        review_status=CandidateReviewStatus.NEEDS_REVIEW.value,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def test_p13_professional_skill_and_root_contract_keep_target_bible_as_only_hard_input() -> None:
    skill = get_professional_skill("replica-target-assets")
    assert skill.version == "1.1.0"
    assert skill.required_inputs == (ArtifactType.TARGET_BIBLE,)
    assert skill.readable_artifacts == (ArtifactType.TARGET_BIBLE,)
    assert skill.required_capabilities == (Capability.TARGET_ASSETS,)
    assert skill.output_contracts == (ArtifactType.TARGET_ASSETS,)

    root = get_root_skill(ProjectType.REPLICA)
    assert root.version == "1.3.0"
    step = next(item for item in root.steps if item.id == "target_assets")
    assert step.requires == (ArtifactType.TARGET_BIBLE,)
    assert step.produces == (ArtifactType.TARGET_ASSETS,)
    assert step.capabilities == (Capability.TARGET_ASSETS,)
    assert "replica-target-assets" in root.subskills

    assert CAPABILITY_BY_ID[Capability.TARGET_ASSETS].availability == CapabilityAvailability.AVAILABLE
    assert expected_namespace(ArtifactType.TARGET_ASSETS) == ArtifactNamespace.TARGET


def test_p13_get_routes_are_read_only_and_generate_requires_current_target_bible(
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
    candidates = client.get(f"/api/v3/projects/{project['id']}/target-assets/candidates")
    assert revisions.status_code == 200 and revisions.json() == []
    assert candidates.status_code == 200 and candidates.json() == []
    assert counts() == before

    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-assets",
        headers={"Idempotency-Key": "p13-missing-bible"},
    )
    assert start.status_code == 409, start.text
    assert start.json()["error"]["code"] == "P13_TARGET_BIBLE_REQUIRED"
    assert counts() == before


def test_p13_non_replica_fails_closed_without_side_effects(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client, "REDRAW")
    for suffix in ("target-assets", "target-assets/revisions", "target-assets/candidates"):
        response = client.get(f"/api/v3/projects/{project['id']}/{suffix}")
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "REPLICA_TARGET_ASSETS_NOT_ALLOWED"
    start = client.post(
        f"/api/v3/projects/{project['id']}/commands/target-assets",
        headers={"Idempotency-Key": "p13-redraw-forbidden"},
    )
    assert start.status_code == 422, start.text
    with session_factory() as db:
        assert int(db.scalar(select(func.count()).select_from(Task)) or 0) == 0
        assert int(db.scalar(select(func.count()).select_from(ProviderJob)) or 0) == 0


def test_p13_provider_semantic_forbids_server_owned_asset_fields() -> None:
    payload = _semantic().model_dump(mode="json")
    payload["characters"][0]["target_asset_id"] = "provider-must-not-own-this"
    with pytest.raises(ValidationError):
        TargetAssetsSemantic.model_validate(payload)


def test_p13_exact_entity_coverage_is_fail_closed() -> None:
    inputs = _compose_inputs()
    service._validate_semantic(inputs, _semantic())
    missing = _semantic().model_copy(deep=True)
    missing.characters = []
    with pytest.raises(AppError) as captured:
        service._validate_semantic(inputs, missing)
    assert captured.value.code == "P13_CHARACTER_COVERAGE_INVALID"

    wrong = _semantic().model_copy(deep=True)
    wrong.scenes[0].target_scene_id = "made-up-scene"
    with pytest.raises(AppError) as captured:
        service._validate_semantic(inputs, wrong)
    assert captured.value.code == "P13_SCENE_COVERAGE_INVALID"


def test_p13_compose_keeps_continuity_asset_local_with_stable_ids_and_revisions() -> None:
    first = service._compose(_compose_inputs(), _semantic())
    character = first.characters[0]
    scene = first.scenes[0]
    prop = first.props[0]

    assert character.identity_direction == "Young urban professional and apartment resident"
    assert scene.spatial_identity == "Middle-class US apartment corridor"
    assert prop.functional_identity == "A wrapped blue rose bouquet with the same story function"
    assert character.display_name == "Alice"

    # Target Bible remains the semantic truth/lineage, but its global/entity rules are not
    # copied into P13 review-facing asset continuity after the real-project acceptance finding.
    assert character.continuity_constraints == ["Do not change facial proportions between shots"]
    assert scene.continuity_constraints == ["Keep elevator, doors and fire alarm in fixed relative positions"]
    assert prop.continuity_constraints == [
        "Keep flower count impression, wrap geometry and ribbon identity stable"
    ]
    assert "Keep all principal visual identities stable across shots" not in character.continuity_constraints
    assert "Keep the same face identity" not in character.continuity_constraints
    assert "Door placement and corridor width remain fixed" not in scene.continuity_constraints
    assert "Keep bouquet size and wrapping identity stable" not in prop.continuity_constraints

    assert character.reference_media == []
    assert scene.reference_media == []
    assert prop.reference_media == []
    assert character.target_asset_revision == scene.target_asset_revision == prop.target_asset_revision == 1

    second = service._compose(_compose_inputs(base=first), _semantic(face="Longer oval face with a defined jawline"))
    assert second.characters[0].target_asset_id == character.target_asset_id
    assert second.characters[0].target_asset_revision == 2
    assert second.characters[0].asset_fingerprint != character.asset_fingerprint
    assert second.scenes[0].target_asset_id == scene.target_asset_id
    assert second.scenes[0].target_asset_revision == 1
    assert second.scenes[0].asset_fingerprint == scene.asset_fingerprint
    assert second.props[0].target_asset_id == prop.target_asset_id
    assert second.props[0].target_asset_revision == 1


def test_p13_candidate_must_be_explicitly_accepted_before_current_artifact_exists(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    with session_factory() as db:
        bible = _seed_target_bible(db, project["id"])
        candidate = _seed_candidate(db, project["id"], bible)
        assert service._current_artifact(db, project["id"], ArtifactType.TARGET_ASSETS) is None

    before = client.get(f"/api/v3/projects/{project['id']}/target-assets")
    assert before.status_code == 200
    assert before.json()["status"] == "NOT_BUILT"

    accept = client.post(
        f"/api/v3/projects/{project['id']}/target-assets/candidates/{candidate.id}/commands/accept",
        json={
            "expected_target_bible_artifact_id": bible.id,
            "expected_generation_sequence": 1,
            "reason": "P13 visual identity packet reviewed and accepted for formal use",
        },
    )
    assert accept.status_code == 200, accept.text
    body = accept.json()
    assert body["status"] == "CURRENT"
    assert body["content"]["target_bible_artifact_id"] == bible.id
    assert body["content"]["characters"][0]["target_character_id"] == "tchr_alice"

    with session_factory() as db:
        row = db.get(ReplicaTargetAssetsCandidate, candidate.id)
        assert row is not None and row.review_status == CandidateReviewStatus.ACCEPTED.value
        artifact = service._current_artifact(db, project["id"], ArtifactType.TARGET_ASSETS)
        assert artifact is not None
        revision = db.scalar(
            select(ReplicaTargetAssetsRevision).where(ReplicaTargetAssetsRevision.artifact_id == artifact.id)
        )
        assert revision is not None and revision.candidate_id == candidate.id
        edge = db.scalar(
            select(ArtifactEdge).where(
                ArtifactEdge.source_node_id == bible.id,
                ArtifactEdge.target_node_id == artifact.id,
                ArtifactEdge.relation_type == ArtifactRelationType.DERIVED_FROM,
            )
        )
        assert edge is not None


def test_p13_reject_candidate_does_not_publish_or_replace_formal_assets(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    with session_factory() as db:
        bible = _seed_target_bible(db, project["id"])
        candidate = _seed_candidate(db, project["id"], bible)

    reject = client.post(
        f"/api/v3/projects/{project['id']}/target-assets/candidates/{candidate.id}/commands/reject",
        json={
            "expected_target_bible_artifact_id": bible.id,
            "expected_generation_sequence": 1,
            "reason": "Visual identity direction needs another iteration",
        },
    )
    assert reject.status_code == 200, reject.text
    assert reject.json()["review_status"] == "REJECTED"
    result = client.get(f"/api/v3/projects/{project['id']}/target-assets")
    assert result.status_code == 200
    assert result.json()["status"] == "NOT_BUILT"


def test_p13_target_bible_revision_stales_assets_but_target_script_revision_does_not(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    project = _project(client)
    with session_factory() as db:
        bible_v1 = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_BIBLE,
            namespace=ArtifactNamespace.TARGET,
            label="Bible v1",
            input_fingerprint=_SHA_A,
            skill_id="replica-target-bible",
            skill_version="1.0.0",
        )
        assets = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_ASSETS,
            namespace=ArtifactNamespace.TARGET,
            label="Assets",
            input_fingerprint=_SHA_B,
            skill_id="replica-target-assets",
            skill_version="1.1.0",
        )
        create_artifact_relation(
            db,
            project_id=project["id"],
            source_node_id=bible_v1.id,
            target_node_id=assets.id,
            relation_type=ArtifactRelationType.DERIVED_FROM,
        )
        script_v1 = create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_SCRIPT,
            namespace=ArtifactNamespace.TARGET,
            label="Script v1",
            input_fingerprint=_SHA_C,
            skill_id="target-script-localization",
            skill_version="1.0.0",
        )
        create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_SCRIPT,
            namespace=ArtifactNamespace.TARGET,
            label="Script v2",
            input_fingerprint="d" * 64,
            skill_id="target-script-localization",
            skill_version="1.0.0",
        )
        db.refresh(script_v1)
        db.refresh(assets)
        assert script_v1.validity == ArtifactValidity.STALE
        assert assets.validity == ArtifactValidity.CURRENT
        assert assets.is_current is True

        create_artifact(
            db,
            project_id=project["id"],
            artifact_type=ArtifactType.TARGET_BIBLE,
            namespace=ArtifactNamespace.TARGET,
            label="Bible v2",
            input_fingerprint="e" * 64,
            skill_id="replica-target-bible",
            skill_version="1.0.0",
        )
        db.refresh(bible_v1)
        db.refresh(assets)
        assert bible_v1.validity == ArtifactValidity.STALE
        assert assets.validity == ArtifactValidity.STALE
        assert assets.is_current is False
