from copy import deepcopy
import json
import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import select
from engine.tests.v2.test_asset_workspace_v3 import seed_project
from engine.app import source_person_assets_v1 as people
from engine.app import character_assets_routes_v1 as routes
from engine.app import studio_v2
from engine.app.asset_workspace_v3 import ShotCharacterBinding, AssetRevision


def setup(monkeypatch, tmp_path):
    project_id, ids = seed_project(monkeypatch, tmp_path)
    timeline = {"is_current": True, "source_breakdown_run_id": "run", "source_shot_revision_id": "rev", "scenes": []}
    for i in (1, 2):
        timeline["scenes"].append({"ordinal": i, "title": f"场景{i}", "people": [{"ref": "P1", "display_name": "人物1", "appearance": "女主"}],
                                  "shots": [{"ordinal": i, "start_us": (i-1)*1000000, "end_us": i*1000000, "people": ["P1"], "thumbnail_url": None}]})
    monkeypatch.setattr(people, "get_current_breakdown", lambda _: {})
    # A current run object is truthy, unlike an absent run.
    monkeypatch.setattr(people, "get_current_breakdown", lambda _: {"run": "current"})
    monkeypatch.setattr(people, "build_scene_timeline_result_v1", lambda _: deepcopy(timeline))
    return project_id, timeline


def test_merge_binds_all_shots_and_read_model_without_mutating_evidence(monkeypatch, tmp_path):
    project, timeline = setup(monkeypatch, tmp_path)
    before = deepcopy(timeline)
    inv = people.inventory(project)
    result = people.assign(project, [o["key"] for o in inv["observations"]], "女主", None, inv["revision"])
    assert len(result["characters"]) == 1
    assert result["characters"][0]["shot_ids"] == ["SHOT_1", "SHOT_2"]
    assert all(o["character_id"] for o in result["observations"])
    payload = {"timeline": timeline, "identity": {"scenes": [{"scene_ordinal": i, "people": [{"ref": "P1", "character": None}]} for i in (1, 2)]}}
    projected = people.apply_person_mapping("EPISODE_1", payload)
    assert projected["identity"]["resolved_count"] == 2
    assert timeline == before
    with studio_v2.get_session() as session:
        revision = session.scalar(select(AssetRevision).where(AssetRevision.is_current.is_(True)))
        assert '女主' in revision.snapshot_json
    with pytest.raises(ValueError, match="已更新"):
        people.assign(project, [inv["observations"][0]["key"]], "重复", None, inv["revision"])


def test_reassignment_splits_only_mapping_owned_binding(monkeypatch, tmp_path):
    project, _ = setup(monkeypatch, tmp_path)
    inv = people.inventory(project)
    inv = people.assign(project, [o["key"] for o in inv["observations"]], "女主", None, inv["revision"])
    old = inv["characters"][0]["id"]
    inv = people.assign(project, [inv["observations"][1]["key"]], "另一人", None, inv["revision"])
    assert next(c for c in inv["characters"] if c["id"] == old)["shot_ids"] == ["SHOT_1"]
    assert len({o["character_id"] for o in inv["observations"]}) == 2


def test_same_shot_cannot_merge_and_changed_evidence_drops_mapping(monkeypatch, tmp_path):
    project, timeline = setup(monkeypatch, tmp_path)
    timeline["scenes"][0]["people"].append({"ref": "P2", "display_name": "人物2", "appearance": "另一人"})
    timeline["scenes"][0]["shots"][0]["people"].append("P2")
    inv = people.inventory(project)
    with pytest.raises(ValueError, match="不能合并"):
        people.assign(project, [o["key"] for o in inv["observations"]], "错合并", None, inv["revision"])
    inv = people.assign(project, [inv["observations"][0]["key"]], "女主", None, inv["revision"])
    assert inv["observations"][0]["character_id"]
    timeline["source_breakdown_run_id"] = "new_run"
    assert not people.inventory(project)["observations"][0]["character_id"]


def test_runtime_offline_does_not_create_task(monkeypatch, tmp_path):
    project, _ = setup(monkeypatch, tmp_path)
    character = dict(id="T", project_id=project, source_character_signature="s", target_language="en", target_region="US", target_name="New", appearance_profile="adult", generation_prompt="new actor")
    monkeypatch.setattr(routes, "require_current", lambda _: character)
    class Offline:
        def status(self): return {"fl2va": {"ready": False}}
    monkeypatch.setattr(routes, "get_video_generation_provider_v1", lambda _: Offline())
    with pytest.raises(HTTPException) as exc:
        routes.generate_views("T", routes.GenerateRequest(fingerprint=routes.signature(character)), BackgroundTasks(), "key")
    assert exc.value.status_code == 503
    with studio_v2.get_session() as session:
        assert not session.scalars(select(routes.BackgroundTaskRecord)).all()


def test_four_views_remain_review_until_accepted_and_reject_stale(monkeypatch, tmp_path):
    project, _ = setup(monkeypatch, tmp_path)
    character = dict(id="T", project_id=project, source_character_signature="s", target_language="en", target_region="US", target_name="New", appearance_profile="adult", generation_prompt="new actor")
    fingerprint = routes.signature(character)
    task = routes.create_task(project_id=project, task_type="CHARACTER_FOUR_VIEWS", title="test")
    class Provider:
        def submit(self, request):
            assert request.duration_seconds == 8
            assert not request.conditions
            return type('Submission', (), {'external_job_id': 'job'})()
        def download(self, **kwargs):
            path = kwargs['destination']; path.write_bytes(b'video'); return path
    monkeypatch.setattr(routes, 'get_video_generation_provider_v1', lambda _: Provider())
    monkeypatch.setattr(routes, '_wait_for_job', lambda *a, **kw: None)
    monkeypatch.setattr(routes, 'validate_reference_video', lambda *a, **kw: None)
    monkeypatch.setattr(routes, '_extract_frame', lambda video, seconds, path: path.write_bytes(b'frame'))
    routes.run_views(task['id'], character, {'target_id': 'T', 'fingerprint': fingerprint})
    with studio_v2.get_session() as session:
        saved = session.get(routes.BackgroundTaskRecord, task['id'])
        assert saved.status == 'READY'
        assert json.loads(saved.result_json)['accepted'] is False
    monkeypatch.setattr(routes, 'require_current', lambda _: {**character, 'appearance_profile': 'changed'})
    with pytest.raises(HTTPException) as exc:
        routes.accept_views(task['id'], routes.GenerateRequest(fingerprint=fingerprint))
    assert exc.value.status_code == 409


def test_design_and_accept_selected_reference_only(monkeypatch, tmp_path):
    project, _ = setup(monkeypatch, tmp_path)
    inv = people.inventory(project)
    inv = people.assign(project, [inv['observations'][0]['key']], '原演员', None, inv['revision'])
    source_id = inv['characters'][0]['id']
    context = {'source_name': '原演员', 'signature': 'source-signature'}
    monkeypatch.setattr(routes, 'target_context', lambda _: ({'source_fingerprint': 'snapshot'}, {source_id: context}))
    request = routes.Design(source_character_id=source_id, expected_revision=inv['revision'], target_name='Emma', appearance_profile='New adult actor in a blue suit', generation_prompt='Consistent fictional actor')
    result = routes.save_design(project, request)
    target = result['targets'][0]
    assert target['source_character_id'] == source_id
    assert target['current']
    with pytest.raises(HTTPException, match='409'):
        routes.save_design(project, request)
    task = routes.create_task(project_id=project, task_type='CHARACTER_FOUR_VIEWS', title='test')
    receipt = {'target_id': target['id'], 'fingerprint': target['fingerprint'], 'accepted': False}
    routes.finish_task(task['id'], result=receipt)
    root = routes.version_root(project, task['id']); root.mkdir(parents=True)
    for view in routes.VIEWS:
        (root / f'{view}.jpg').write_bytes(b'validated image fixture')
    from engine.app.h3_reference_assets_v1 import current_target_character_reference_assets_v1
    assert current_target_character_reference_assets_v1(target) == []
    routes.accept_views(task['id'], routes.GenerateRequest(fingerprint=target['fingerprint']))
    assert len(current_target_character_reference_assets_v1(target)) == 4
    with studio_v2.get_session() as session:
        assert session.get(studio_v2.Character, source_id).name == '原演员'
        session.get(routes.TargetCharacter, target['id']).appearance_profile = 'Changed design'
        session.commit()
    assert current_target_character_reference_assets_v1(target) == []


def test_localization_validates_frame_and_persists_with_mapping(monkeypatch, tmp_path):
    project, timeline = setup(monkeypatch, tmp_path)
    timeline["scenes"][0]["shots"][0]["thumbnail_url"] = "/api/current-frame.jpg"
    inv = people.inventory(project)
    row = inv["observations"][0]
    mark = {"shot_id": row["shots"][0]["id"], "image_url": "/api/current-frame.jpg", "box": [.1, .2, .3, .5]}
    for invalid in ({}, {**mark, "image_url": "/old.jpg"}, {**mark, "box": [.9, .2, .3, .5]}, {**mark, "box": [0, 0, float("nan"), 1]}):
        with pytest.raises(ValueError, match="标记"):
            people.assign(project, [row["key"]], "人物", None, inv["revision"], {row["key"]: invalid})
    result = people.assign(project, [row["key"]], "人物", None, inv["revision"], {row["key"]: mark})
    assert result["observations"][0]["localization"] == mark
    assert result["revision"] != inv["revision"]
    timeline["source_breakdown_run_id"] = "new-run"
    assert not people.inventory(project)["observations"][0].get("localization")
