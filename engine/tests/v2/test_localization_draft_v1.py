from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import localization_draft_v1 as draft
from engine.app import studio_v2
from engine.app.localization_draft_contract_v1 import LocalizationDraftEditV1


def use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}", connect_args={"check_same_thread": False})
    studio_v2.Base.metadata.create_all(engine)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))


def seed_episode(monkeypatch, tmp_path: Path) -> None:
    use_temp_database(monkeypatch, tmp_path)
    with studio_v2.get_session() as session:
        session.add(studio_v2.Project(
            id="PROJECT_1",
            name="本土化测试",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        ))
        session.add(studio_v2.Episode(
            id="EPISODE_1",
            project_id="PROJECT_1",
            title="第一集",
            original_filename="e1.mp4",
            source_path=str(tmp_path / "e1.mp4"),
            source_sha256="a" * 64,
            sort_order=1,
            status="READY",
        ))
        session.commit()


def source_payload(*, shot_revision_id: str = "SHOTREV_1", ocr_text: str = "门牌 302") -> dict[str, object]:
    return {
        "schema_version": "localization-source-v1",
        "status": "READY",
        "project_id": "PROJECT_1",
        "episode_id": "EPISODE_1",
        "source_language": "zh-CN",
        "target_language": "en-US",
        "target_region": "US",
        "source_breakdown_run_id": "RUN_1",
        "source_shot_revision_id": shot_revision_id,
        "source_asset_revision_id": "ASSETREV_1",
        "scene_count": 1,
        "shot_count": 1,
        "source_dialogue_count": 1,
        "source_on_screen_text_count": 1,
        "warnings": [],
        "scenes": [
            {
                "ordinal": 1,
                "start_us": 0,
                "end_us": 2_000_000,
                "duration_us": 2_000_000,
                "title": "走廊",
                "story_summary": "人物在走廊交谈。",
                "scene_info": {
                    "location": "走廊",
                    "interior_exterior": "室内",
                    "time_of_day": "白天",
                    "environment": "公寓走廊",
                },
                "final_scene": None,
                "people": [],
                "shots": [
                    {
                        "ordinal": 1,
                        "start_us": 0,
                        "end_us": 2_000_000,
                        "duration_us": 2_000_000,
                        "thumbnail_url": "/thumb.jpg",
                        "reference_url": "/ref.mp4",
                        "visual_description": "一名人物站在走廊。",
                        "people": [],
                        "performance": [],
                        "source_dialogue": [
                            {
                                "source_key": "S1:H1:D1",
                                "start_us": 200_000,
                                "end_us": 900_000,
                                "source_text": "你终于来了。",
                                "speakers": [],
                            }
                        ],
                        "observed_props": [],
                        "final_props": [],
                        "cinematography": {
                            "shot_type": "中景",
                            "composition": None,
                            "camera_motion": None,
                        },
                        "source_on_screen_text": [
                            {
                                "source_key": "S1:H1:T1",
                                "start_us": 0,
                                "end_us": 2_000_000,
                                "source_text": ocr_text,
                            }
                        ],
                    }
                ],
            }
        ],
    }


def install_source(monkeypatch, payload_holder: dict[str, dict[str, object]]) -> None:
    monkeypatch.setattr(
        draft,
        "load_episode_localization_source_v1",
        lambda episode_id: payload_holder["value"] if episode_id == "EPISODE_1" else None,
    )


def entry(view: dict[str, object], source_key: str) -> dict[str, object]:
    scenes = view["scenes"]
    assert isinstance(scenes, list)
    entries = scenes[0]["shots"][0]["entries"]
    return next(item for item in entries if item["source_key"] == source_key)


def test_write_contract_has_no_source_text_field() -> None:
    assert "source_text" not in LocalizationDraftEditV1.model_fields
    with pytest.raises(ValidationError):
        LocalizationDraftEditV1.model_validate({
            "source_key": "S1:H1:D1",
            "source_text": "篡改源文本",
            "decision": "KEEP_SOURCE",
        })


def test_edit_review_final_creates_immutable_revision_history(monkeypatch, tmp_path: Path) -> None:
    seed_episode(monkeypatch, tmp_path)
    holder = {"value": source_payload()}
    install_source(monkeypatch, holder)

    created = draft.create_localization_draft("EPISODE_1")
    assert created["revision"] == 1
    assert created["status"] == "DRAFT"
    assert created["progress"] == {"total": 2, "pending": 2, "localized": 0, "keep_source": 0, "omitted": 0}
    assert entry(created, "S1:H1:D1")["source_text"] == "你终于来了。"

    edited = draft.edit_localization_draft(
        "EPISODE_1",
        base_revision_id=created["revision_id"],
        entries=[
            {
                "source_key": "S1:H1:D1",
                "decision": "LOCALIZE",
                "translated_text": "You finally came.",
                "localized_text": "You made it.",
                "final_text": "You made it.",
            },
            {
                "source_key": "S1:H1:T1",
                "decision": "KEEP_SOURCE",
            },
        ],
    )
    assert edited["revision"] == 2
    assert edited["progress"]["pending"] == 0
    assert entry(edited, "S1:H1:D1")["source_text"] == "你终于来了。"
    assert entry(edited, "S1:H1:D1")["effective_final_text"] == "You made it."
    assert entry(edited, "S1:H1:T1")["effective_final_text"] == "门牌 302"

    review = draft.set_localization_draft_status(
        "EPISODE_1",
        base_revision_id=edited["revision_id"],
        status="IN_REVIEW",
    )
    assert review["revision"] == 3
    assert review["status"] == "IN_REVIEW"

    final = draft.set_localization_draft_status(
        "EPISODE_1",
        base_revision_id=review["revision_id"],
        status="FINAL",
    )
    assert final["revision"] == 4
    assert final["status"] == "FINAL"

    revisions = draft.list_localization_revisions("EPISODE_1")
    assert [item["revision"] for item in revisions] == [4, 3, 2, 1]
    assert revisions[0]["is_current"] is True
    assert all(item["is_current"] is False for item in revisions[1:])

    with studio_v2.get_session() as session:
        rows = list(session.scalars(select(draft.LocalizationRevision).where(
            draft.LocalizationRevision.episode_id == "EPISODE_1"
        )).all())
        assert len(rows) == 4
        assert sum(item.is_current for item in rows) == 1


def test_pending_and_state_machine_block_unsafe_finalize(monkeypatch, tmp_path: Path) -> None:
    seed_episode(monkeypatch, tmp_path)
    holder = {"value": source_payload()}
    install_source(monkeypatch, holder)
    created = draft.create_localization_draft("EPISODE_1")

    with pytest.raises(draft.LocalizationDraftConflictError, match="未处理"):
        draft.set_localization_draft_status(
            "EPISODE_1",
            base_revision_id=created["revision_id"],
            status="IN_REVIEW",
        )

    with pytest.raises(draft.LocalizationDraftConflictError, match="不允许"):
        draft.set_localization_draft_status(
            "EPISODE_1",
            base_revision_id=created["revision_id"],
            status="FINAL",
        )


def test_optimistic_revision_id_prevents_lost_update(monkeypatch, tmp_path: Path) -> None:
    seed_episode(monkeypatch, tmp_path)
    holder = {"value": source_payload()}
    install_source(monkeypatch, holder)
    created = draft.create_localization_draft("EPISODE_1")

    first = draft.edit_localization_draft(
        "EPISODE_1",
        base_revision_id=created["revision_id"],
        entries=[{"source_key": "S1:H1:D1", "decision": "KEEP_SOURCE"}],
    )
    assert first["revision"] == 2

    with pytest.raises(draft.LocalizationDraftConflictError, match="刷新"):
        draft.edit_localization_draft(
            "EPISODE_1",
            base_revision_id=created["revision_id"],
            entries=[{"source_key": "S1:H1:T1", "decision": "KEEP_SOURCE"}],
        )


def test_stale_source_blocks_edit_and_rebase_only_carries_exact_source_rows(monkeypatch, tmp_path: Path) -> None:
    seed_episode(monkeypatch, tmp_path)
    holder = {"value": source_payload()}
    install_source(monkeypatch, holder)
    created = draft.create_localization_draft("EPISODE_1")
    edited = draft.edit_localization_draft(
        "EPISODE_1",
        base_revision_id=created["revision_id"],
        entries=[
            {
                "source_key": "S1:H1:D1",
                "decision": "LOCALIZE",
                "final_text": "You made it.",
            },
            {"source_key": "S1:H1:T1", "decision": "KEEP_SOURCE"},
        ],
    )

    holder["value"] = source_payload(shot_revision_id="SHOTREV_2", ocr_text="门牌 305")
    stale = draft.get_current_localization_draft("EPISODE_1")
    assert stale is not None and stale["stale"] is True

    with pytest.raises(draft.LocalizationDraftStaleError):
        draft.edit_localization_draft(
            "EPISODE_1",
            base_revision_id=edited["revision_id"],
            entries=[{"source_key": "S1:H1:D1", "decision": "KEEP_SOURCE"}],
        )

    rebased = draft.rebase_localization_draft("EPISODE_1")
    assert rebased["revision"] == 3
    assert rebased["kind"] == "REBASE"
    assert rebased["status"] == "DRAFT"
    assert rebased["stale"] is False
    assert entry(rebased, "S1:H1:D1")["final_text"] == "You made it."
    assert entry(rebased, "S1:H1:T1")["source_text"] == "门牌 305"
    assert entry(rebased, "S1:H1:T1")["decision"] == "PENDING"
