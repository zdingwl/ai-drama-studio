from copy import deepcopy
from dataclasses import replace
from unittest.mock import create_autospec

import pytest
from fastapi import BackgroundTasks, HTTPException

from engine.app import breakdown_performance_v1 as service
from engine.app import breakdown_routes_v1 as routes
from engine.app import task_progress_v2 as tasks
from engine.app import studio_v2
from engine.app import breakdown_manual_override_v1 as manual
from engine.tests.v2.test_asset_workspace_v3 import seed_project
from engine.tests.v2.test_breakdown_shot_rerun_v1 import _draft, _timeline, _target, _vlm


def fixture(monkeypatch, tmp_path):
    project, _ = seed_project(monkeypatch, tmp_path)
    draft, timeline = _draft(), _timeline()
    draft['run']['project_id'] = project
    monkeypatch.setattr(service.rerun, 'get_current_breakdown', lambda _: draft)
    monkeypatch.setattr(service.rerun, 'assemble_scene_timeline_v1', lambda _: deepcopy(timeline))
    monkeypatch.setattr(service, 'build_scene_timeline_result_v1', lambda _: manual.apply_manual_overrides_v1(draft, deepcopy(timeline)))
    monkeypatch.setattr(service, 'get_project_flow_state_v1', lambda _: {'revision': 'FLOW_1'})
    full = service.rerun.p2.P2RunContext('temp', project, 'EPISODE_1', 'zh', 'REV_1', None, (_target(), replace(_target(), ordinal=2, revision_item_id='ITEM_2')))
    monkeypatch.setattr(service.rerun, '_load_full_context', lambda *a, **k: full)
    return draft, timeline


def test_proposal_only_calls_scoped_vlm_and_adoption_preserves_source(monkeypatch, tmp_path):
    draft, timeline = fixture(monkeypatch, tmp_path)
    original = deepcopy(timeline)
    command = service.context('EPISODE_1', 1)
    class Provider:
        component = 'VLM'
        def analyze(self, context):
            assert [shot.ordinal for shot in context.shots] == [1]
            result = _vlm()
            result.evidence[0].payload['semantic']['subjects'][0]['expression_summary'] = '皱眉'
            return result
    result = service.propose(command, provider=Provider())
    assert not manual.manual_override_path_v1(draft).exists()
    assert set(result['suggested']) <= set(service.FIELDS)
    assert '皱眉' == result['suggested']['expression']
    service.adopt(result, ['expression'])
    _, shot, after = service.current_input('EPISODE_1', 1)
    assert after['input_fingerprint'] != command['input_fingerprint']
    assert after['before']['performance_text'] == command['before']['performance_text']
    assert after['before']['expression'] == '皱眉'
    assert timeline == original
    for field in ('people', 'dialogue', 'start_us', 'end_us', 'cinematography', 'props'):
        assert shot[field] == original['scenes'][0]['shots'][0][field]
    with pytest.raises(ValueError, match='版本已变化'):
        service.adopt(result, ['performance_text'])


def test_rejects_stale_input_and_unknown_adoption_fields(monkeypatch, tmp_path):
    fixture(monkeypatch, tmp_path)
    command = service.context('EPISODE_1', 1)
    with pytest.raises(ValueError, match='已变化'):
        service.propose({**command, 'input_fingerprint': 'old'})
    with pytest.raises(ValueError, match='字段'):
        service.adopt({'command': command, 'suggested': {'people': ['P2']}}, ['people'])
    with pytest.raises(ValueError, match='空建议'):
        service.adopt({'command': command, 'suggested': {}}, ['expression'])


def test_durable_command_replay_scope_and_read_only_get(monkeypatch, tmp_path):
    fixture(monkeypatch, tmp_path)
    command = routes.api_performance_context('EPISODE_1', 1)
    payload = routes.PerformanceCommand(**{key: command[key] for key in ('input_fingerprint', 'workflow_revision')})
    background = BackgroundTasks()
    first = routes.api_start_performance('EPISODE_1', 1, payload, background, 'key-1')
    assert len(background.tasks) == 1
    replay = routes.api_start_performance('EPISODE_1', 1, payload, background, 'key-1')
    assert first['id'] == replay['id'] and len(background.tasks) == 1
    assert routes.api_get_performance(first['id'])['status'] == 'QUEUED'
    assert len(background.tasks) == 1
    with pytest.raises(HTTPException) as exc:
        routes.api_start_performance('EPISODE_1', 1, payload, background, 'key-2')
    assert exc.value.status_code == 409
    tasks.finish_task(first['id'], result={'command': command, 'suggested': {'expression': '抿嘴'}, 'adopted': False})
    routes.api_adopt_performance(first['id'], routes.PerformanceAdoption(fields=['expression']))
    assert routes.api_adopt_performance(first['id'], routes.PerformanceAdoption(fields=['expression'])) == {'adopted': True}
    assert routes.api_get_performance(first['id'])['result']['adopted']
    assert routes.api_start_performance('EPISODE_1', 1, payload, background, 'key-1')['id'] == first['id']
    with pytest.raises(HTTPException):
        routes.api_start_performance('EPISODE_1', 1, payload.model_copy(update={'input_fingerprint': 'changed'}), background, 'key-1')


def test_runner_uses_real_task_signatures(monkeypatch):
    start, finish, fail = (create_autospec(fn) for fn in (tasks.start_task, tasks.finish_task, tasks.fail_task))
    monkeypatch.setattr(service, 'start_task', start)
    monkeypatch.setattr(service, 'finish_task', finish)
    monkeypatch.setattr(service, 'fail_task', fail)
    monkeypatch.setattr(service, 'propose', lambda _: {'suggested': {}})
    service.run_task('TASK_1', {})
    start.assert_called_once(); finish.assert_called_once(); fail.assert_not_called()


def test_multi_person_suggestions_keep_visible_subject_descriptions():
    result = service.suggested_fields({'subjects': [
        {'appearance_summary': '白衫长发女性', 'expression_summary': '皱眉'},
        {'appearance_summary': '灰衣短发男性', 'expression_summary': '微笑', 'gaze_summary': '无法判断'},
    ]}, {})
    assert result == {'expression': '白衫长发女性：皱眉；灰衣短发男性：微笑'}
