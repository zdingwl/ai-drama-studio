from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from engine.app import review_issue_routes_v1 as routes


class _FakeReadModel:
    def __init__(self, presence_review: dict[str, str] | None = None) -> None:
        self.presence_review = presence_review or {"5": "待核对"}
        self.timeline = SimpleNamespace(source_shot_revision_id="SHOTREV_1")

    def model_copy(self, *, deep: bool = False, update: dict | None = None):
        _ = deep
        copied = _FakeReadModel(dict(self.presence_review))
        if update and "presence_review" in update:
            copied.presence_review = dict(update["presence_review"])
        return copied


class _FakeReadModelType:
    @classmethod
    def model_validate(cls, payload):
        _ = payload
        return _FakeReadModel()


@contextmanager
def _fake_session():
    class Session:
        def get(self, model, key):
            if model is routes.Episode:
                return SimpleNamespace(
                    id="EP_1",
                    project_id="PROJECT_1",
                    title="第一集",
                    sort_order=1,
                )
            if model is routes.Project:
                return SimpleNamespace(
                    id="PROJECT_1",
                    name="测试项目",
                    source_language="zh-CN",
                )
            raise AssertionError(f"unexpected model: {model!r}, key={key!r}")

        def scalars(self, statement):
            _ = statement
            return SimpleNamespace(all=lambda: [SimpleNamespace(ordinal=5)])

    yield Session()


def test_speaker_review_snapshot_tolerates_only_pending_presence_gate(monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_session", _fake_session)
    monkeypatch.setattr(routes, "BreakdownReadModelV1", _FakeReadModelType)
    monkeypatch.setattr(routes, "load_episode_source_drama_snapshot_v1", lambda *args, **kwargs: (_ for _ in ()).throw(
        routes.SourceDramaSnapshotError("1 个镜头的出镜人物覆盖尚未核对，不能固化原片事实")
    ))
    monkeypatch.setattr(routes, "load_episode_breakdown_read_model_v1", lambda episode_id: {"episode_id": episode_id})
    monkeypatch.setattr(
        routes,
        "load_episode_source_dialogue_speaker_overrides_v1",
        lambda episode_id: {"DIALOGUE_1": {"person_key": "PERSON_1", "dialogue_signature": "sig"}},
    )

    captured: dict = {}

    def compose_episode(read_model, **kwargs):
        captured["presence_review"] = dict(read_model.presence_review)
        captured["kwargs"] = kwargs
        return {"episode_id": "EP_1", "scenes": []}

    def compose_project(**kwargs):
        captured["project"] = kwargs
        return {"project_id": kwargs["project_id"], "episodes": kwargs["episodes"]}

    monkeypatch.setattr(routes, "compose_episode_source_drama_snapshot_v1", compose_episode)
    monkeypatch.setattr(routes, "compose_project_source_drama_snapshot_v1", compose_project)

    snapshot = routes._episode_review_snapshot("PROJECT_1", "EP_1")

    assert snapshot["project_id"] == "PROJECT_1"
    assert captured["presence_review"] == {}
    assert captured["kwargs"]["infer_speakers"] is False
    assert list(captured["kwargs"]["revision_items_by_ordinal"]) == [5]
    assert captured["kwargs"]["speaker_overrides"]["DIALOGUE_1"]["person_key"] == "PERSON_1"


def test_speaker_review_snapshot_does_not_bypass_other_source_gates(monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_session", _fake_session)
    monkeypatch.setattr(routes, "load_episode_source_drama_snapshot_v1", lambda *args, **kwargs: (_ for _ in ()).throw(
        routes.SourceDramaSnapshotError("源对白与字幕差异尚未确认，不能固化原片事实")
    ))

    def unexpected_breakdown_load(episode_id: str):
        raise AssertionError(f"must not bypass non-presence gate for {episode_id}")

    monkeypatch.setattr(routes, "load_episode_breakdown_read_model_v1", unexpected_breakdown_load)

    with pytest.raises(routes.SourceDramaSnapshotError, match="源对白与字幕差异尚未确认"):
        routes._episode_review_snapshot("PROJECT_1", "EP_1")
