from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import UniqueConstraint, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

# Import asset workspace before Base.create_all so Final Asset / Binding / Revision
# tables are present in the same test database. P1 tests never call its write APIs.
from engine.app import asset_workspace_v3  # noqa: F401
from engine.app import (
    breakdown_routes_v1,
    breakdown_serializer_v1,
    breakdown_service_v1,
    breakdown_validator_v1,
    shot_edit_routes_v2,
    shot_revision_v2,
    studio_v2,
)
from engine.app.asset_workspace_v3 import (
    AssetRevision,
    ShotCharacterBinding,
    ShotPropBinding,
    ShotSceneBinding,
)
from engine.app.breakdown_models_v1 import (
    BreakdownEvidenceLink,
    BreakdownRun,
    DraftPropHint,
    DraftPropOccurrence,
    LocalSubject,
    SceneSegmentDraft,
    ShotLocalSubject,
    ShotSemanticDraft,
    TimelineEvent,
    TimelineEventSubject,
)
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem


BREAKDOWN_TABLES = {
    "v2_breakdown_runs",
    "v2_scene_segment_drafts",
    "v2_shot_semantic_drafts",
    "v2_local_subjects",
    "v2_shot_local_subjects",
    "v2_timeline_events",
    "v2_timeline_event_subjects",
    "v2_draft_prop_hints",
    "v2_draft_prop_occurrences",
    "v2_breakdown_evidence_links",
}
FINAL_TABLES = {
    "v2_characters",
    "v2_scenes",
    "v2_props",
    "v2_shot_character_bindings",
    "v2_shot_scene_bindings",
    "v2_shot_prop_bindings",
    "v2_asset_revisions",
}
FORBIDDEN_FINAL_COLUMNS = {"character_id", "scene_id", "prop_id", "shot_id"}


def setup_episode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, seed_final: bool = False):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)

    source = tmp_path / "source.mp4"
    source.write_bytes(b"episode-source")

    with factory() as session:
        project = studio_v2.Project(
            id="PROJECT_1",
            name="Breakdown P1 Contract",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        )
        episode = studio_v2.Episode(
            id="EPISODE_1",
            project_id=project.id,
            title="EP01",
            original_filename="ep01.mp4",
            source_path=str(source),
            source_sha256="x" * 64,
            sort_order=1,
            status="SHOTS_READY",
            duration_us=3_000_000,
        )
        session.add_all([project, episode])
        session.flush()

        for ordinal, start_us, end_us in [
            (1, 0, 1_000_000),
            (2, 1_000_000, 2_000_000),
            (3, 2_000_000, 3_000_000),
        ]:
            reference = tmp_path / f"old-reference-{ordinal}.mp4"
            thumbnail = tmp_path / f"old-thumbnail-{ordinal}.jpg"
            reference.write_bytes(f"old-reference-{ordinal}".encode())
            thumbnail.write_bytes(f"old-thumbnail-{ordinal}".encode())
            session.add(studio_v2.Shot(
                id=f"SHOT_{ordinal}",
                episode_id=episode.id,
                ordinal=ordinal,
                start_us=start_us,
                end_us=end_us,
                duration_us=end_us - start_us,
                reference_clip_path=str(reference),
                thumbnail_path=str(thumbnail),
                keyframes_json="[]",
                short_description=f"shot {ordinal}",
                shot_type=None,
                camera_motion=None,
                status="READY",
            ))
        session.flush()

        if seed_final:
            character = studio_v2.Character(
                id="CHAR_FINAL",
                project_id=project.id,
                name="已确认人物",
                status="CONFIRMED",
                metadata_json=json.dumps({"source": "sentinel"}),
            )
            scene = studio_v2.Scene(
                id="SCENE_FINAL",
                project_id=project.id,
                name="已确认场景",
                status="CONFIRMED",
                metadata_json=json.dumps({"source": "sentinel"}),
            )
            prop = studio_v2.Prop(
                id="PROP_FINAL",
                project_id=project.id,
                name="已确认道具",
                is_key_prop=True,
                metadata_json=json.dumps({"source": "sentinel"}),
            )
            session.add_all([character, scene, prop])
            session.flush()
            session.add_all([
                ShotCharacterBinding(
                    id="BIND_CHAR",
                    project_id=project.id,
                    shot_id="SHOT_1",
                    character_id=character.id,
                    source="MANUAL",
                    confidence=1.0,
                ),
                ShotSceneBinding(
                    id="BIND_SCENE",
                    project_id=project.id,
                    shot_id="SHOT_1",
                    scene_id=scene.id,
                    source="MANUAL",
                    confidence=1.0,
                ),
                ShotPropBinding(
                    id="BIND_PROP",
                    project_id=project.id,
                    shot_id="SHOT_1",
                    prop_id=prop.id,
                    source="MANUAL",
                    confidence=1.0,
                ),
                AssetRevision(
                    id="ASSETREV_1",
                    project_id=project.id,
                    revision=1,
                    kind="MANUAL",
                    is_current=True,
                    source_run_id=None,
                    source_revision_id=None,
                    note="sentinel final state",
                    snapshot_json=json.dumps({"sentinel": True}),
                ),
            ])
        session.commit()

    return factory


def create_contract_draft(factory: Any) -> BreakdownRun:
    run = breakdown_service_v1.create_breakdown_run(
        "EPISODE_1",
        pipeline_profile="p1.5-fixture",
        component_status={"fixture": "READY"},
        provider_metadata={"provider": "fixture"},
    )

    with factory() as session:
        items = list(session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == run.source_shot_revision_id)
            .order_by(ShotRevisionItem.ordinal)
        ).all())
        assert len(items) == 3
        item1, item2, item3 = items

        segment1 = SceneSegmentDraft(
            id="SCENESEG_1",
            run_id=run.id,
            episode_id=run.episode_id,
            ordinal=1,
            source_start_us=item1.start_us,
            source_end_us=item2.end_us,
            location_hint="住宅楼走廊",
            interior_exterior="INTERIOR",
            time_of_day="DAY",
            summary="人物A与人物B在走廊发生争执",
            confidence=0.93,
        )
        segment2 = SceneSegmentDraft(
            id="SCENESEG_2",
            run_id=run.id,
            episode_id=run.episode_id,
            ordinal=2,
            source_start_us=item3.start_us,
            source_end_us=item3.end_us,
            location_hint="病房",
            interior_exterior="INTERIOR",
            time_of_day="DAY",
            summary="另一局部人物A进入病房",
            confidence=0.90,
        )
        drafts = [
            ShotSemanticDraft(
                id="SHOTDRAFT_1",
                run_id=run.id,
                scene_segment_id=segment1.id,
                source_shot_revision_item_id=item1.id,
                source_shot_id_snapshot=item1.original_shot_id,
                shot_ordinal_snapshot=item1.ordinal,
                source_start_us=item1.start_us,
                source_end_us=item1.end_us,
                summary="人物A走近人物B",
                confidence=0.95,
            ),
            ShotSemanticDraft(
                id="SHOTDRAFT_2",
                run_id=run.id,
                scene_segment_id=segment1.id,
                source_shot_revision_item_id=item2.id,
                source_shot_id_snapshot=item2.original_shot_id,
                shot_ordinal_snapshot=item2.ordinal,
                source_start_us=item2.start_us,
                source_end_us=item2.end_us,
                summary="人物A质问人物B",
                confidence=0.96,
            ),
            ShotSemanticDraft(
                id="SHOTDRAFT_3",
                run_id=run.id,
                scene_segment_id=segment2.id,
                source_shot_revision_item_id=item3.id,
                source_shot_id_snapshot=item3.original_shot_id,
                shot_ordinal_snapshot=item3.ordinal,
                source_start_us=item3.start_us,
                source_end_us=item3.end_us,
                summary="人物A进入病房",
                confidence=0.91,
            ),
        ]
        subject_a = LocalSubject(
            id="LOCAL_A_SEG1",
            run_id=run.id,
            scene_segment_id=segment1.id,
            ordinal=1,
            display_label="人物A",
            appearance_summary="年轻女性，黑色上衣",
            first_seen_us=100_000,
            last_seen_us=1_900_000,
            speaking_state_summary="mixed",
            confidence=0.91,
        )
        subject_b = LocalSubject(
            id="LOCAL_B_SEG1",
            run_id=run.id,
            scene_segment_id=segment1.id,
            ordinal=2,
            display_label="人物B",
            appearance_summary="中年女性，手提袋",
            first_seen_us=1_050_000,
            last_seen_us=1_900_000,
            speaking_state_summary="silent",
            confidence=0.88,
        )
        subject_a_other_segment = LocalSubject(
            id="LOCAL_A_SEG2",
            run_id=run.id,
            scene_segment_id=segment2.id,
            ordinal=1,
            display_label="人物A",
            appearance_summary="穿白色外套的人",
            first_seen_us=2_100_000,
            last_seen_us=2_900_000,
            speaking_state_summary="unknown",
            confidence=0.82,
        )

        presences = [
            ShotLocalSubject(
                id="PRES_A_1",
                run_id=run.id,
                shot_draft_id="SHOTDRAFT_1",
                local_subject_id=subject_a.id,
                first_seen_us=100_000,
                last_seen_us=900_000,
                speaking_state="SILENT",
                confidence=0.9,
            ),
            ShotLocalSubject(
                id="PRES_A_2",
                run_id=run.id,
                shot_draft_id="SHOTDRAFT_2",
                local_subject_id=subject_a.id,
                first_seen_us=1_050_000,
                last_seen_us=1_900_000,
                speaking_state="SPEAKING",
                confidence=0.94,
            ),
            ShotLocalSubject(
                id="PRES_B_2",
                run_id=run.id,
                shot_draft_id="SHOTDRAFT_2",
                local_subject_id=subject_b.id,
                first_seen_us=1_050_000,
                last_seen_us=1_900_000,
                speaking_state="SILENT",
                confidence=0.9,
            ),
            ShotLocalSubject(
                id="PRES_A_3",
                run_id=run.id,
                shot_draft_id="SHOTDRAFT_3",
                local_subject_id=subject_a_other_segment.id,
                first_seen_us=2_100_000,
                last_seen_us=2_900_000,
                speaking_state="UNKNOWN",
                confidence=0.82,
            ),
        ]

        event = TimelineEvent(
            id="EVENT_CONFRONT",
            run_id=run.id,
            shot_draft_id="SHOTDRAFT_2",
            ordinal=1,
            event_type="DIALOGUE",
            source_start_us=1_200_000,
            source_end_us=1_600_000,
            shot_relative_start_us=200_000,
            shot_relative_end_us=600_000,
            content_text="人物A拦住人物B并质问",
            language="zh-CN",
            emotion_hint="质问",
            confidence=0.93,
            origin="FUSION",
        )
        participants = [
            TimelineEventSubject(
                id="PARTICIPANT_ACTOR",
                event_id=event.id,
                local_subject_id=subject_a.id,
                role="ACTOR",
                confidence=0.94,
            ),
            TimelineEventSubject(
                id="PARTICIPANT_SPEAKER",
                event_id=event.id,
                local_subject_id=subject_a.id,
                role="SPEAKER",
                confidence=0.96,
            ),
            TimelineEventSubject(
                id="PARTICIPANT_TARGET",
                event_id=event.id,
                local_subject_id=subject_b.id,
                role="TARGET",
                confidence=0.91,
            ),
        ]

        prop = DraftPropHint(
            id="PROPHINT_PHONE",
            run_id=run.id,
            scene_segment_id=segment1.id,
            ordinal=1,
            label_hint="手机",
            normalized_hint="phone",
            importance="SUPPORTING",
            narrative_reason="人物B拿出手机展示消息",
            first_seen_us=1_250_000,
            last_seen_us=1_700_000,
            confidence=0.84,
        )
        occurrence = DraftPropOccurrence(
            id="PROPOCC_PHONE",
            prop_hint_id=prop.id,
            shot_draft_id="SHOTDRAFT_2",
            source_start_us=1_250_000,
            source_end_us=1_700_000,
            screen_position_hint="RIGHT",
            interaction_summary="人物B手持手机",
            confidence=0.86,
        )
        evidence = BreakdownEvidenceLink(
            id="EVIDENCE_RULE",
            run_id=run.id,
            owner_type="TIMELINE_EVENT",
            owner_id=event.id,
            source_type="RULE",
            role="SUPPORT",
            confidence=0.7,
        )

        session.add_all([
            segment1,
            segment2,
            *drafts,
            subject_a,
            subject_b,
            subject_a_other_segment,
            *presences,
            event,
            *participants,
            prop,
            occurrence,
            evidence,
        ])
        session.commit()

    return run


def new_auto_payloads(tmp_path: Path) -> list[dict[str, Any]]:
    bounds = [(1, 0, 1_400_000), (2, 1_400_000, 3_000_000)]
    payloads: list[dict[str, Any]] = []
    for ordinal, start_us, end_us in bounds:
        reference = tmp_path / f"new-reference-{ordinal}.mp4"
        thumbnail = tmp_path / f"new-thumbnail-{ordinal}.jpg"
        reference.write_bytes(f"new-reference-{ordinal}".encode())
        thumbnail.write_bytes(f"new-thumbnail-{ordinal}".encode())
        payloads.append({
            "ordinal": ordinal,
            "start_us": start_us,
            "end_us": end_us,
            "duration_us": end_us - start_us,
            "reference_clip_path": str(reference),
            "thumbnail_path": str(thumbnail),
            "keyframes_json": "[]",
            "short_description": None,
            "shot_type": None,
            "camera_motion": None,
            "status": "READY",
        })
    return payloads


def final_state(factory: Any) -> dict[str, list[tuple[Any, ...]]]:
    with factory() as session:
        return {
            "characters": [
                (row.id, row.name, row.status, row.metadata_json)
                for row in session.scalars(select(studio_v2.Character).order_by(studio_v2.Character.id)).all()
            ],
            "scenes": [
                (row.id, row.name, row.status, row.metadata_json)
                for row in session.scalars(select(studio_v2.Scene).order_by(studio_v2.Scene.id)).all()
            ],
            "props": [
                (row.id, row.name, row.is_key_prop, row.metadata_json)
                for row in session.scalars(select(studio_v2.Prop).order_by(studio_v2.Prop.id)).all()
            ],
            "character_bindings": [
                (row.id, row.shot_id, row.character_id, row.source, row.confidence)
                for row in session.scalars(select(ShotCharacterBinding).order_by(ShotCharacterBinding.id)).all()
            ],
            "scene_bindings": [
                (row.id, row.shot_id, row.scene_id, row.source, row.confidence)
                for row in session.scalars(select(ShotSceneBinding).order_by(ShotSceneBinding.id)).all()
            ],
            "prop_bindings": [
                (row.id, row.shot_id, row.prop_id, row.source, row.confidence)
                for row in session.scalars(select(ShotPropBinding).order_by(ShotPropBinding.id)).all()
            ],
            "asset_revisions": [
                (row.id, row.revision, row.kind, row.is_current, row.snapshot_json)
                for row in session.scalars(select(AssetRevision).order_by(AssetRevision.id)).all()
            ],
        }


def make_read_app(*, include_revision_media: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(breakdown_routes_v1.router)
    if include_revision_media:
        app.include_router(shot_edit_routes_v2.router)
    return app


def test_p1_schema_is_additive_anonymous_and_has_no_final_or_current_shot_fk() -> None:
    """Contract 3/8/9：Draft schema 有唯一锚点，但不把匿名提示偷绑成 Final Asset。"""

    assert BREAKDOWN_TABLES <= set(studio_v2.Base.metadata.tables)
    for table_name in BREAKDOWN_TABLES:
        table = studio_v2.Base.metadata.tables[table_name]
        assert FORBIDDEN_FINAL_COLUMNS.isdisjoint(table.c.keys())
        fk_targets = {fk.column.table.name for fk in table.foreign_keys}
        assert "v2_shots" not in fk_targets
        assert FINAL_TABLES.isdisjoint(fk_targets)

    unique_constraints = [
        constraint
        for constraint in ShotSemanticDraft.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    assert any(
        {column.name for column in constraint.columns}
        == {"run_id", "source_shot_revision_item_id"}
        for constraint in unique_constraints
    )


def test_same_run_revision_item_cannot_have_two_shot_drafts(monkeypatch, tmp_path: Path) -> None:
    """Contract 3：DB 层也必须阻断同 Run/RevisionItem 的重复 Shot Draft。"""

    factory = setup_episode(monkeypatch, tmp_path)
    run = create_contract_draft(factory)
    with factory() as session:
        original = session.get(ShotSemanticDraft, "SHOTDRAFT_1")
        assert original is not None
        session.add(ShotSemanticDraft(
            id="SHOTDRAFT_DUPLICATE",
            run_id=run.id,
            scene_segment_id=original.scene_segment_id,
            source_shot_revision_item_id=original.source_shot_revision_item_id,
            source_shot_id_snapshot=original.source_shot_id_snapshot,
            shot_ordinal_snapshot=original.shot_ordinal_snapshot,
            source_start_us=original.source_start_us,
            source_end_us=original.source_end_us,
            summary="duplicate must fail",
            confidence=0.5,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_multi_shot_segment_subject_scope_and_same_label_are_contract_safe(monkeypatch, tmp_path: Path) -> None:
    """Contract 4/5/6：Segment 连续；人物可跨本 Segment Shots；跨 Segment 同名不等于同身份。"""

    factory = setup_episode(monkeypatch, tmp_path)
    run = create_contract_draft(factory)

    result = breakdown_validator_v1.validate_breakdown_run(run.id)
    assert result.passed is True

    with factory() as session:
        segment1_shots = list(session.scalars(
            select(ShotSemanticDraft)
            .where(ShotSemanticDraft.scene_segment_id == "SCENESEG_1")
            .order_by(ShotSemanticDraft.shot_ordinal_snapshot)
        ).all())
        assert [item.shot_ordinal_snapshot for item in segment1_shots] == [1, 2]
        segment1 = session.get(SceneSegmentDraft, "SCENESEG_1")
        assert segment1 is not None
        assert (segment1.source_start_us, segment1.source_end_us) == (0, 2_000_000)

        a_presences = list(session.scalars(
            select(ShotLocalSubject)
            .where(ShotLocalSubject.local_subject_id == "LOCAL_A_SEG1")
            .order_by(ShotLocalSubject.shot_draft_id)
        ).all())
        assert [item.shot_draft_id for item in a_presences] == ["SHOTDRAFT_1", "SHOTDRAFT_2"]

        same_labels = list(session.scalars(
            select(LocalSubject)
            .where(LocalSubject.display_label == "人物A")
            .order_by(LocalSubject.scene_segment_id)
        ).all())
        assert [item.id for item in same_labels] == ["LOCAL_A_SEG1", "LOCAL_A_SEG2"]
        assert same_labels[0].scene_segment_id != same_labels[1].scene_segment_id


def test_event_participants_and_prop_hint_remain_anonymous_semantics(monkeypatch, tmp_path: Path) -> None:
    """Contract 7/8：事件支持多参与者角色；Prop 只是 Hint，不会生成 Final Prop。"""

    factory = setup_episode(monkeypatch, tmp_path)
    run = create_contract_draft(factory)
    result = breakdown_validator_v1.validate_breakdown_run(run.id)
    assert result.passed is True

    with factory() as session:
        participants = list(session.scalars(
            select(TimelineEventSubject)
            .where(TimelineEventSubject.event_id == "EVENT_CONFRONT")
        ).all())
        assert {item.role for item in participants} == {"ACTOR", "TARGET", "SPEAKER"}
        assert sum(1 for item in participants if item.local_subject_id == "LOCAL_A_SEG1") == 2

        hint = session.get(DraftPropHint, "PROPHINT_PHONE")
        occurrence = session.get(DraftPropOccurrence, "PROPOCC_PHONE")
        assert hint is not None and hint.label_hint == "手机"
        assert occurrence is not None and occurrence.prop_hint_id == hint.id
        assert session.scalars(select(studio_v2.Prop)).all() == []


def test_p1_create_publish_and_read_do_not_mutate_final_assets_or_bindings(monkeypatch, tmp_path: Path) -> None:
    """Contract 15：P1.1-P1.4 只能写 Draft，不得污染 Final Asset / Binding / AssetRevision。"""

    factory = setup_episode(monkeypatch, tmp_path, seed_final=True)
    before = final_state(factory)

    run = create_contract_draft(factory)
    published = breakdown_service_v1.publish_breakdown_run(run.id)
    assert published.status == "READY"
    assert breakdown_serializer_v1.get_current_breakdown("EPISODE_1") is not None
    assert breakdown_serializer_v1.list_breakdown_runs("EPISODE_1")

    after = final_state(factory)
    assert after == before


def test_read_only_api_exposes_history_current_and_nested_draft(monkeypatch, tmp_path: Path) -> None:
    """P1.4 compatibility：只读 API 的 list/current/by-id 与嵌套 Draft 结构保持稳定。"""

    factory = setup_episode(monkeypatch, tmp_path)
    run = create_contract_draft(factory)
    client = TestClient(make_read_app())

    assert client.get("/api/episodes/EPISODE_1/breakdown-current").json() is None
    published = breakdown_service_v1.publish_breakdown_run(run.id)
    assert published.status == "READY"

    history_response = client.get("/api/episodes/EPISODE_1/breakdown-runs")
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    assert history[0]["id"] == run.id
    assert history[0]["source_shot_revision"]["item_count"] == 3

    current_response = client.get("/api/episodes/EPISODE_1/breakdown-current")
    by_id_response = client.get(f"/api/breakdown-runs/{run.id}")
    assert current_response.status_code == 200
    assert by_id_response.status_code == 200
    current = current_response.json()
    by_id = by_id_response.json()
    assert current == by_id
    assert current["run"]["id"] == run.id
    assert [segment["ordinal"] for segment in current["scene_segments"]] == [1, 2]
    assert [shot["shot_ordinal_snapshot"] for shot in current["scene_segments"][0]["shots"]] == [1, 2]

    event = current["scene_segments"][0]["shots"][1]["events"][0]
    assert {item["role"] for item in event["participants"]} == {"ACTOR", "TARGET", "SPEAKER"}
    assert current["scene_segments"][0]["prop_hints"][0]["label_hint"] == "手机"
    source_item = current["scene_segments"][0]["shots"][0]["source_shot_revision_item"]
    assert source_item["reference_url"].startswith("/api/shot-revision-items/")
    assert "/api/shots/" not in source_item["reference_url"]
    assert all(not values for values in current["unassigned"].values())

    breakdown_paths = {
        route.path: set(route.methods or set())
        for route in make_read_app().routes
        if route.path.startswith("/api/")
    }
    assert breakdown_paths == {
        "/api/episodes/{episode_id}/breakdown-runs": {"GET"},
        "/api/episodes/{episode_id}/breakdown-current": {"GET"},
        "/api/breakdown-runs/{run_id}": {"GET"},
    }


def test_read_only_api_does_not_create_baseline_revision_for_legacy_episode(monkeypatch, tmp_path: Path) -> None:
    """P1.4 compatibility：读旧项目不能产生 BASELINE Revision 或 Breakdown 写入。"""

    factory = setup_episode(monkeypatch, tmp_path)
    with factory() as session:
        assert session.scalars(select(ShotRevision)).all() == []
        assert session.scalars(select(BreakdownRun)).all() == []

    client = TestClient(make_read_app())
    list_response = client.get("/api/episodes/EPISODE_1/breakdown-runs")
    current_response = client.get("/api/episodes/EPISODE_1/breakdown-current")
    assert list_response.status_code == 200 and list_response.json() == []
    assert current_response.status_code == 200 and current_response.json() is None
    assert client.get("/api/breakdown-runs/DOES_NOT_EXIST").status_code == 404

    with factory() as session:
        assert session.scalars(select(ShotRevision)).all() == []
        assert session.scalars(select(BreakdownRun)).all() == []


def test_auto_rerun_history_survives_and_old_reference_clip_stays_open(monkeypatch, tmp_path: Path) -> None:
    """Contract 11/12/13：P1.5 验证 STALE primitive；自动接线明确留给 P1.6。"""

    factory = setup_episode(monkeypatch, tmp_path)
    run = create_contract_draft(factory)
    breakdown_service_v1.publish_breakdown_run(run.id)
    old_payload = breakdown_serializer_v1.get_breakdown_run(run.id)
    assert old_payload is not None
    old_revision_id = old_payload["run"]["source_shot_revision_id"]
    old_shot = old_payload["scene_segments"][0]["shots"][0]
    old_item = old_shot["source_shot_revision_item"]
    old_item_id = old_item["id"]
    old_reference_url = old_item["reference_url"]
    old_shot_id = old_shot["source_shot_id_snapshot"]

    new_shots = shot_revision_v2.commit_auto_shot_revision(
        "EPISODE_1",
        new_auto_payloads(tmp_path),
        note="P1.5 auto rerun fixture",
    )
    assert old_shot_id not in {item["id"] for item in new_shots}

    # P1.6 will wire this primitive into every Shot Revision mutation automatically.
    changed = breakdown_service_v1.mark_episode_breakdown_runs_stale("EPISODE_1")
    assert changed == [run.id]

    with factory() as session:
        old_run = session.get(BreakdownRun, run.id)
        old_revision = session.get(ShotRevision, old_revision_id)
        old_revision_item = session.get(ShotRevisionItem, old_item_id)
        assert old_run is not None and old_run.status == "STALE" and old_run.is_current is False
        assert old_revision is not None and old_revision.is_current is False
        assert old_revision_item is not None
        assert Path(old_revision_item.reference_clip_path).read_bytes() == b"old-reference-1"

    historical = breakdown_serializer_v1.get_breakdown_run(run.id)
    assert historical is not None
    historical_item = historical["scene_segments"][0]["shots"][0]["source_shot_revision_item"]
    assert historical_item["id"] == old_item_id
    assert historical_item["reference_url"] == old_reference_url

    client = TestClient(make_read_app(include_revision_media=True))
    response = client.get(old_reference_url)
    assert response.status_code == 200
    assert response.content == b"old-reference-1"


def test_failed_run_remains_readable_and_does_not_replace_ready_current(monkeypatch, tmp_path: Path) -> None:
    """Contract 14 + P1.4：失败 Run 不替换旧 Current，且失败历史仍能被只读 API 查看。"""

    factory = setup_episode(monkeypatch, tmp_path)
    stable = create_contract_draft(factory)
    breakdown_service_v1.publish_breakdown_run(stable.id)

    failed = breakdown_service_v1.create_breakdown_run("EPISODE_1", pipeline_profile="invalid-fixture")
    with pytest.raises(breakdown_service_v1.BreakdownValidationGateError):
        breakdown_service_v1.publish_breakdown_run(failed.id)

    client = TestClient(make_read_app())
    current = client.get("/api/episodes/EPISODE_1/breakdown-current").json()
    assert current["run"]["id"] == stable.id
    failed_payload = client.get(f"/api/breakdown-runs/{failed.id}")
    assert failed_payload.status_code == 200
    assert failed_payload.json()["run"]["status"] == "FAILED"

    history = client.get("/api/episodes/EPISODE_1/breakdown-runs").json()
    assert {item["id"] for item in history} == {stable.id, failed.id}
    assert sum(1 for item in history if item["is_current"]) == 1

    with factory() as session:
        stable_row = session.get(BreakdownRun, stable.id)
        failed_row = session.get(BreakdownRun, failed.id)
        assert stable_row is not None and stable_row.status == "READY" and stable_row.is_current is True
        assert failed_row is not None and failed_row.status == "FAILED" and failed_row.is_current is False


def test_bad_historical_json_is_diagnostic_instead_of_breaking_read_api(monkeypatch, tmp_path: Path) -> None:
    """P1.4 compatibility：损坏历史 JSON 仍可读，并显式暴露诊断 raw。"""

    factory = setup_episode(monkeypatch, tmp_path)
    run = create_contract_draft(factory)
    with factory() as session:
        row = session.get(BreakdownRun, run.id)
        assert row is not None
        row.provider_metadata_json = "{broken-json"
        session.commit()

    client = TestClient(make_read_app())
    response = client.get(f"/api/breakdown-runs/{run.id}")
    assert response.status_code == 200
    metadata = response.json()["run"]["provider_metadata"]
    assert metadata == {"_invalid_json": True, "_raw": "{broken-json"}
