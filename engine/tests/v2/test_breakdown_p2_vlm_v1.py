from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import breakdown_p2_vlm_v1 as vlm, breakdown_service_v1, studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun


def make_context(tmp_path: Path, *, with_clips: bool = True) -> vlm.p2.P2RunContext:
    shots = []
    for ordinal, start_us, end_us in [
        (1, 0, 1_000_000),
        (2, 1_000_000, 2_500_000),
    ]:
        clip = tmp_path / f"历史 VLM 镜头 {ordinal}.mp4"
        if with_clips:
            clip.write_bytes(b"clip")
        shots.append(vlm.p2.P2ShotInput(
            revision_item_id=f"REVISION_ITEM_{ordinal}",
            original_shot_id=f"SHOT_{ordinal}",
            ordinal=ordinal,
            start_us=start_us,
            end_us=end_us,
            duration_us=end_us - start_us,
            reference_clip_path=str(clip),
            thumbnail_path=None,
            keyframes=(),
        ))
    return vlm.p2.P2RunContext(
        run_id="BREAKDOWN_RUN_VLM",
        project_id="PROJECT_VLM",
        episode_id="EPISODE_VLM",
        source_language="zh-CN",
        source_shot_revision_id="SHOT_REVISION_VLM",
        audio_path=None,
        shots=tuple(shots),
    )


def semantic_for(summary: str) -> dict:
    return {
        "scene": {
            "location_hint": "住宅楼走廊",
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "狭长走廊，墙边有门。",
        },
        "shot": {
            "summary": summary,
            "visual_description": "两名人物面对面站立。",
            "shot_type_hint": "中景",
            "camera_motion_hint": "固定",
            "narrative_function_hint": "冲突建立",
            "composition_hint": "双人构图",
        },
        "subjects": [
            {
                "label": "subject_A",
                "appearance_summary": "年轻女性，深色上衣",
                "activity_summary": "抬手拦住另一人",
                "screen_position": "画面左侧",
                "visibility": "FULL",
                "speaking_state": "LIKELY_SPEAKING",
            },
            {
                "label": "subject_B",
                "appearance_summary": "中年女性",
                "activity_summary": "站在门边",
                "screen_position": "画面右侧",
                "visibility": "PARTIAL",
                "speaking_state": "UNKNOWN",
            },
        ],
        "events": [
            {
                "event_type": "ACTION",
                "start_ratio": 0.1,
                "end_ratio": 0.8,
                "content": "subject_A 抬手拦住 subject_B。",
                "subject_labels": ["subject_A", "subject_B"],
            }
        ],
        "props": [
            {
                "label": "黑色塑料袋",
                "importance": "HIGH",
                "narrative_reason": "subject_B 手中持续拿着并参与当前动作。",
                "subject_labels": ["subject_B"],
            }
        ],
    }


def test_qwen3_vl_provider_emits_exact_shot_bound_anonymous_semantics(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    calls: list[tuple[vlm.VLMRuntimeConfig, tuple[vlm.p2.P2ShotInput, ...]]] = []

    def runner(config, shots):
        calls.append((config, tuple(shots)))
        return [
            {
                "revision_item_id": shot.revision_item_id,
                "ordinal": shot.ordinal,
                "status": "READY",
                "semantic": semantic_for(f"镜头 {shot.ordinal} 的可见动作"),
            }
            for shot in shots
        ]

    provider = vlm.Qwen3VLSemanticProvider(
        model_name="fixture-qwen3-vl",
        device="cuda",
        inference_runner=runner,
    )
    result = provider.analyze(context)

    assert result.status == "READY"
    assert result.provider == "qwen3-vl"
    assert result.model == "fixture-qwen3-vl"
    assert len(calls) == 1
    config, shots = calls[0]
    assert config.source_language == "zh-CN"
    assert [shot.ordinal for shot in shots] == [1, 2]
    assert result.metadata["semantic_schema"] == vlm.VLM_SEMANTIC_SCHEMA
    assert result.metadata["semantic_output_count"] == 2
    assert result.metadata["confidence_policy"] == "provider-output-unscored"

    first, second = result.evidence
    assert first.source_type == "VLM_OUTPUT"
    assert first.shot_revision_item_id == "REVISION_ITEM_1"
    assert first.source_start_us == 0
    assert first.source_end_us == 1_000_000
    assert first.text == "镜头 1 的可见动作"
    assert first.confidence is None
    assert first.payload["semantic"]["subjects"][0]["label"] == "subject_A"
    assert first.payload["semantic"]["events"][0]["event_type"] == "ACTION"
    assert first.payload["semantic"]["props"][0]["label"] == "黑色塑料袋"

    assert second.shot_revision_item_id == "REVISION_ITEM_2"
    assert second.source_start_us == 1_000_000
    assert second.source_end_us == 2_500_000


def test_vlm_whitelist_drops_final_asset_ids_and_unknown_model_fields(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    raw = semantic_for("人物在走廊争执")
    raw["character_id"] = "CHARACTER_SHOULD_NOT_PERSIST"
    raw["scene_id"] = "SCENE_SHOULD_NOT_PERSIST"
    raw["prop_id"] = "PROP_SHOULD_NOT_PERSIST"
    raw["subjects"][0]["character_id"] = "CHARACTER_NESTED"
    raw["shot"]["raw_chain_of_thought"] = "do not persist arbitrary model fields"

    result = vlm.Qwen3VLSemanticProvider(
        inference_runner=lambda _config, shots: [{
            "revision_item_id": shots[0].revision_item_id,
            "status": "READY",
            "semantic": raw,
        }],
    ).analyze(vlm.p2.P2RunContext(
        **{**context.__dict__, "shots": (context.shots[0],)}
    ))

    assert result.status == "READY"
    persisted = result.evidence[0].payload["semantic"]
    dumped = json.dumps(persisted, ensure_ascii=False)
    assert "character_id" not in dumped
    assert "scene_id" not in dumped
    assert "prop_id" not in dumped
    assert "raw_chain_of_thought" not in dumped
    vlm.p2.validate_provider_result(
        vlm.p2.P2RunContext(**{**context.__dict__, "shots": (context.shots[0],)}),
        result,
    )


def test_missing_reference_clips_returns_not_available_before_runner(tmp_path: Path) -> None:
    context = make_context(tmp_path, with_clips=False)
    called = False

    def runner(_config, _shots):
        nonlocal called
        called = True
        raise AssertionError("missing clips must stop before VLM inference")

    result = vlm.Qwen3VLSemanticProvider(inference_runner=runner).analyze(context)

    assert result.status == "NOT_AVAILABLE"
    assert result.evidence == ()
    assert called is False
    assert result.metadata["missing_reference_clip_count"] == 2


def test_partial_invalid_shot_output_keeps_valid_semantics_with_warning(tmp_path: Path) -> None:
    context = make_context(tmp_path)

    def runner(_config, shots):
        return [
            {
                "revision_item_id": shots[0].revision_item_id,
                "status": "READY",
                "semantic": semantic_for("第一个镜头有效"),
            },
            {
                "revision_item_id": shots[1].revision_item_id,
                "status": "READY",
                "semantic": {"scene": {}, "shot": {}, "subjects": [], "events": [], "props": []},
            },
        ]

    result = vlm.Qwen3VLSemanticProvider(inference_runner=runner).analyze(context)

    assert result.status == "READY"
    assert len(result.evidence) == 1
    assert result.metadata["semantic_output_count"] == 1
    assert result.metadata["shot_failure_count"] == 1
    assert any("Shot 2" in warning for warning in result.warnings)


def test_all_invalid_vlm_outputs_fail_closed(tmp_path: Path) -> None:
    context = make_context(tmp_path)

    def runner(_config, shots):
        return [
            {
                "revision_item_id": shot.revision_item_id,
                "status": "FAILED",
                "error_type": "FixtureError",
            }
            for shot in shots
        ]

    result = vlm.Qwen3VLSemanticProvider(inference_runner=runner).analyze(context)

    assert result.status == "FAILED"
    assert result.evidence == ()
    assert result.metadata["shot_failure_count"] == 2


def setup_real_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    home = tmp_path / "P2 VLM 工作 空间"
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(home))
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'p2 vlm.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)

    source = tmp_path / "原视频.mp4"
    source.write_bytes(b"video")
    with factory() as session:
        session.add(studio_v2.Project(
            id="PROJECT_P2_VLM",
            name="P2 VLM",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        ))
        session.add(studio_v2.Episode(
            id="EPISODE_P2_VLM",
            project_id="PROJECT_P2_VLM",
            title="EP01",
            original_filename="ep01.mp4",
            source_path=str(source),
            source_sha256="c" * 64,
            sort_order=1,
            status="SHOTS_READY",
            duration_us=2_000_000,
        ))
        session.flush()
        for ordinal, start_us, end_us in [(1, 0, 1_000_000), (2, 1_000_000, 2_000_000)]:
            clip = tmp_path / f"VLM 参考 镜头 {ordinal}.mp4"
            clip.write_bytes(b"clip")
            session.add(studio_v2.Shot(
                id=f"SHOT_P2_VLM_{ordinal}",
                episode_id="EPISODE_P2_VLM",
                ordinal=ordinal,
                start_us=start_us,
                end_us=end_us,
                duration_us=end_us - start_us,
                reference_clip_path=str(clip),
                thumbnail_path=None,
                keyframes_json="[]",
                status="READY",
            ))
        session.commit()

    run = breakdown_service_v1.create_breakdown_run(
        "EPISODE_P2_VLM",
        pipeline_profile="breakdown-p2-vlm-v1",
        component_status={"ASR": "PENDING", "OCR": "PENDING", "VLM": "PENDING"},
    )
    return factory, run


def test_vlm_entry_persists_sidecar_without_final_assets(monkeypatch, tmp_path: Path) -> None:
    factory, run = setup_real_run(monkeypatch, tmp_path)

    def runner(_config, shots):
        return [
            {
                "revision_item_id": shot.revision_item_id,
                "ordinal": shot.ordinal,
                "status": "READY",
                "semantic": semantic_for(f"历史镜头 {shot.ordinal}"),
            }
            for shot in shots
        ]

    provider = vlm.Qwen3VLSemanticProvider(
        model_name="fixture-qwen3-vl",
        inference_runner=runner,
    )
    artifact = vlm.run_qwen3_vl_semantics(run.id, provider=provider)

    payload = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
    assert payload["component"] == "VLM"
    assert payload["provider"] == "qwen3-vl"
    assert payload["model"] == "fixture-qwen3-vl"
    assert payload["status"] == "READY"
    assert [item["source_type"] for item in payload["evidence"]] == ["VLM_OUTPUT", "VLM_OUTPUT"]
    assert all(item["shot_revision_item_id"] for item in payload["evidence"])
    assert payload["evidence"][0]["payload"]["semantic"]["subjects"][0]["label"] == "subject_A"

    with factory() as session:
        row = session.get(BreakdownRun, run.id)
        assert row is not None and row.status == "PROCESSING"
        status = json.loads(row.component_status_json)["VLM"]
        assert status["status"] == "READY"
        assert status["evidence_count"] == 2
        assert session.scalars(select(studio_v2.Character)).all() == []
        assert session.scalars(select(studio_v2.Scene)).all() == []
        assert session.scalars(select(studio_v2.Prop)).all() == []
