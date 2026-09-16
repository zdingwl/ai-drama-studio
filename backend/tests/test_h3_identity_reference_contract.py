import hashlib

from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.p16.common import _validate_reference_contract
from app.replica_pipeline.h3_prompting import _references
from app.target_assets.schemas import ReferenceMediaRole, TargetAssetRef, TargetAssetType


def _media(role: ReferenceMediaRole, name: str):
    return SimpleNamespace(
        reference_id=f"ref:{name}",
        role=role,
        uri=f"/media/{name}.png",
        mime_type="image/png",
        sha256=hashlib.sha256(name.encode("utf-8")).hexdigest(),
        width=384,
        height=768,
        provider_job_id="job-1",
        storage_relpath=f"refs/{name}.png",
    )


def _asset(entity_id: str, asset_type: TargetAssetType, media: list):
    return SimpleNamespace(
        target_asset_id=f"asset:{entity_id}",
        target_asset_revision=1,
        asset_type=asset_type,
        target_entity_id=entity_id,
        reference_media=media,
    )


def test_h3_reference_priority_locks_visible_character_face_and_body_before_scene_and_prop() -> None:
    visible = _asset("char-visible", TargetAssetType.CHARACTER, [
        _media(ReferenceMediaRole.OTHER, "v-board"),
        _media(ReferenceMediaRole.FULL_BODY, "v-front"),
        _media(ReferenceMediaRole.FACE, "v-face"),
    ])
    offscreen = _asset("char-offscreen", TargetAssetType.CHARACTER, [
        _media(ReferenceMediaRole.FULL_BODY, "o-front"),
        _media(ReferenceMediaRole.FACE, "o-face"),
    ])
    scene = _asset("scene-1", TargetAssetType.SCENE, [_media(ReferenceMediaRole.LAYOUT, "s-layout")])
    prop = _asset("prop-1", TargetAssetType.PROP, [_media(ReferenceMediaRole.DETAIL, "p-detail")])
    shot = SimpleNamespace(
        target_character_ids=["char-visible"],
        target_scene_ids=["scene-1"],
        target_prop_ids=["prop-1"],
    )

    conditions, refs = _references(
        shot,
        [SimpleNamespace(target_character_id="char-offscreen")],
        "assets-artifact-1",
        {item.target_entity_id: item for item in (visible, offscreen, scene, prop)},
    )

    assert [(item.picture_index, item.target_entity_id, item.reference_role) for item in conditions] == [
        (1, "char-visible", "FACE"),
        (2, "char-visible", "FULL_BODY"),
        (3, "scene-1", "LAYOUT"),
        (4, "prop-1", "DETAIL"),
    ]
    assert [item.target_entity_id for item in refs] == ["char-visible", "scene-1", "prop-1"]
    assert all(item.target_entity_id != "char-offscreen" for item in conditions)
    assert all(item.reference_id != "ref:v-board" for item in conditions)


def test_h3_reference_compilation_fails_closed_without_face_and_front_body() -> None:
    character = _asset("char-1", TargetAssetType.CHARACTER, [
        _media(ReferenceMediaRole.OTHER, "board"),
        _media(ReferenceMediaRole.FULL_BODY, "front"),
    ])
    shot = SimpleNamespace(target_character_ids=["char-1"], target_scene_ids=[], target_prop_ids=[])

    with pytest.raises(AppError) as captured:
        _references(shot, [], "assets-artifact-1", {"char-1": character})

    assert captured.value.code == "H3_PROMPT_CHARACTER_IDENTITY_REFERENCES_REQUIRED"


def test_h3_reference_compilation_never_drops_character_identity_to_fit_nine_slots() -> None:
    characters = {}
    ids = []
    for index in range(5):
        entity_id = f"char-{index}"
        ids.append(entity_id)
        characters[entity_id] = _asset(entity_id, TargetAssetType.CHARACTER, [
            _media(ReferenceMediaRole.FACE, f"f{index}"),
            _media(ReferenceMediaRole.FULL_BODY, f"b{index}"),
        ])
    shot = SimpleNamespace(target_character_ids=ids, target_scene_ids=[], target_prop_ids=[])

    with pytest.raises(AppError) as captured:
        _references(shot, [], "assets-artifact-1", characters)

    assert captured.value.code == "H3_PROMPT_CHARACTER_REFERENCE_CAPACITY_EXCEEDED"


def test_p16_reference_contract_matches_current_asset_media_and_requires_character_pair() -> None:
    character = _asset("char-1", TargetAssetType.CHARACTER, [
        _media(ReferenceMediaRole.OTHER, "board"),
        _media(ReferenceMediaRole.FACE, "face"),
        _media(ReferenceMediaRole.FULL_BODY, "front"),
    ])
    shot = SimpleNamespace(target_character_ids=["char-1"], target_scene_ids=[], target_prop_ids=[])
    conditions, refs = _references(shot, [], "assets-artifact-1", {"char-1": character})
    segment = SimpleNamespace(
        generation_segment_id="seg-1",
        reference_conditions=conditions,
        target_asset_refs=refs,
    )
    assets = SimpleNamespace(assets=[character])
    segments = SimpleNamespace(segments=[segment])
    artifact = SimpleNamespace(id="assets-artifact-1")

    _validate_reference_contract(assets_artifact=artifact, assets=assets, segments=segments)

    face_only = SimpleNamespace(
        generation_segment_id="seg-1",
        reference_conditions=[conditions[0]],
        target_asset_refs=refs,
    )
    with pytest.raises(AppError) as captured:
        _validate_reference_contract(
            assets_artifact=artifact,
            assets=assets,
            segments=SimpleNamespace(segments=[face_only]),
        )
    assert captured.value.code == "P16_CHARACTER_IDENTITY_REFERENCES_REQUIRED"


def test_p16_reference_contract_rejects_hash_mapping_drift() -> None:
    character = _asset("char-1", TargetAssetType.CHARACTER, [
        _media(ReferenceMediaRole.FACE, "face"),
        _media(ReferenceMediaRole.FULL_BODY, "front"),
    ])
    shot = SimpleNamespace(target_character_ids=["char-1"], target_scene_ids=[], target_prop_ids=[])
    conditions, refs = _references(shot, [], "assets-artifact-1", {"char-1": character})
    tampered = conditions[0].model_copy(update={"reference_sha256": "f" * 64})
    segment = SimpleNamespace(
        generation_segment_id="seg-1",
        reference_conditions=[tampered, conditions[1]],
        target_asset_refs=refs,
    )

    with pytest.raises(AppError) as captured:
        _validate_reference_contract(
            assets_artifact=SimpleNamespace(id="assets-artifact-1"),
            assets=SimpleNamespace(assets=[character]),
            segments=SimpleNamespace(segments=[segment]),
        )

    assert captured.value.code == "P16_REFERENCE_CONTRACT_MISMATCH"
