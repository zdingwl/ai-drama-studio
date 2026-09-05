from copy import deepcopy
import json

import pytest
from sqlalchemy import select

from engine.app import source_presence_audit_v1 as audit
from engine.app import source_presence_correction_v1 as correction
from engine.app import source_person_assets_v1 as people
from engine.app.review_issue_v1 import ReviewIssue, set_review_issue_status
from engine.app.studio_v2 import get_session
from engine.tests.v2.test_character_assets_workflow_v1 import setup


def test_matching_is_one_to_one_and_frame_specific():
    left, right = [.02, .1, .4, .8], [.5, .2, .45, .75]
    detections = [{'box': left}, {'box': right}]
    subjects = [{'frame_boxes': [{'frame': 1, 'box': right}]},
                {'frame_boxes': [{'frame': 1, 'box': right}]}]
    assert audit.uncovered_regions(detections, subjects, 1) == [{**detections[0], 'reason': '人体区域未被视觉人物可靠覆盖'}]
    assert len(audit.uncovered_regions(detections, subjects, 2)) == 2
    assert audit.uncovered_regions([detections[1]], subjects[:1], 1) == []
    assert len(audit.uncovered_regions(detections, subjects, 1, review_all=True)) == 3


def test_single_subject_without_every_frame_box_is_not_reported_as_a_missing_person():
    detection = {'box': [.02, .05, .95, .9]}
    subject = {'frame_boxes': [{'frame': 1, 'box': [.01, .04, .96, .91]}]}

    assert audit.uncovered_regions([detection], [subject], 2) == []
    # 已有同帧定位却明显冲突时，仍保留核对，避免把人物切换误当成同一个人。
    assert audit.uncovered_regions([detection], [{'frame_boxes': [{'frame': 2, 'box': [.7, .1, .2, .5]}]}], 2)
    # 两个人体区域仍必须提示，不能被单人物语义结果吞掉。
    assert len(audit.uncovered_regions([detection, {'box': [.7, .1, .2, .5]}], [subject], 2)) == 2


def test_invalid_boxes_cannot_hide_missing_people():
    assert audit.frame_boxes([{'frame': True, 'box': [0, 0, 1, 1]},
                              {'frame': 1, 'box': [0, 0, float('nan'), 1]},
                              {'frame': 2, 'box': [.9, 0, .5, 1]}]) == []
    from engine.app.breakdown_p2_vlm_v1 import Qwen3VLSemanticProvider
    subject = Qwen3VLSemanticProvider()._normalize_subjects([{'label': 'subject_A', 'visibility': 'BACK_VIEW', 'frame_boxes': [{'frame': 1, 'box': [0, 0, .5, 1]}]}])[0]
    assert subject['visibility'] == 'BACK_VIEW'
    assert subject['frame_boxes'][0]['frame'] == 1


def test_model_worker_geometry_needs_no_business_dependencies():
    import subprocess
    import sys
    from pathlib import Path
    command = "from scripts.run_breakdown_vlm_exact_shot_compact_v3 import _canonical_subjects; assert _canonical_subjects([{'visibility':'BACK_VIEW','frame_boxes':[{'frame':1,'box':[0,0,.5,1]}]}])[0]['frame_boxes']"
    subprocess.run([sys.executable, '-S', '-c', command], cwd=Path(__file__).resolve().parents[3], check=True, capture_output=True)


def seed_review(monkeypatch, tmp_path):
    project, timeline = setup(monkeypatch, tmp_path)
    inv = people.inventory(project)
    bound = people.assign(project, [inv['observations'][0]['key']], '徐然', None, inv['revision'])
    character = next(c['id'] for c in bound['characters'] if c['name'] == '徐然')
    timeline['scenes'][0]['shots'][0]['thumbnail_url'] = '/version-thumb'
    from engine.app import breakdown_serializer_v1 as serializer
    from engine.app import breakdown_shot_rerun_v1 as rerun
    monkeypatch.setattr(serializer, 'get_current_breakdown', lambda _: {'current': True})
    monkeypatch.setattr(rerun, '_anchors', lambda _: ('run', project, 'EPISODE_1', 'rev'))
    regions = [dict(id='left', image_url='/exact-frame', box=[0, .1, .4, .8]),
               dict(id='right', image_url='/exact-frame', box=[.55, .1, .4, .8])]
    row = dict(shot_id='SHOT_1', ordinal=1, candidates=regions, needs_review=True)
    audit.publish(project, 'EPISODE_1', 'run', 'rev', [row])
    issue = audit.pending('EPISODE_1', 'run', 'rev')[0]
    return project, character, issue, row


def test_decisions_preserved_and_no_same_frame_identity_merge(monkeypatch, tmp_path):
    project, character, issue, row = seed_review(monkeypatch, tmp_path)
    ctx = correction.context(project, 'SHOT_1')
    mark = dict(shot_id='SHOT_1', image_url='/exact-frame', box=[0, .1, .4, .8], source='MANUAL_BOX')
    with pytest.raises(ValueError, match='原图'):
        correction.supplement(project, 'SHOT_1', character, {**mark, 'image_url': '/other'}, ctx['revision'], issue_id=issue['id'], candidate_id='left')
    saved = correction.supplement(project, 'SHOT_1', character, mark, ctx['revision'], issue_id=issue['id'], candidate_id='left')
    with pytest.raises(ValueError, match='同一画面'):
        correction.supplement(project, 'SHOT_1', character, {**mark, 'box': [.55, .1, .4, .8]}, saved['revision'], issue_id=issue['id'], candidate_id='right')
    with pytest.raises(ValueError, match='对应编辑器'):
        set_review_issue_status(issue['id'], status='RESOLVED')
    audit.publish(project, 'EPISODE_1', 'run', 'rev', [row])
    assert audit.pending('EPISODE_1', 'run', 'rev')[0]['editable_payload']['left']['character_id'] == character
    extra = deepcopy(row)
    extra['candidates'] = [dict(id='later', image_url='/later-frame', box=[0, .1, .4, .8])]
    audit.publish(project, 'EPISODE_1', 'run', 'rev', [extra])
    remaining = audit.pending('EPISODE_1', 'run', 'rev')
    assert len(remaining) == 1
    assert {r['id'] for r in remaining[0]['ai_suggestion']['candidates']} == {'left', 'right', 'later'}
    assert not audit.pending('EPISODE_1', 'other-run', 'rev')


def test_only_all_explicit_decisions_close_issue(monkeypatch, tmp_path):
    project, character, issue, _ = seed_review(monkeypatch, tmp_path)
    for region in issue['ai_suggestion']['candidates']:
        ctx = correction.context(project, 'SHOT_1')
        correction.supplement(project, 'SHOT_1', '', {}, ctx['revision'], issue_id=issue['id'],
                              candidate_id=region['id'], decision='NOT_PERSON', reason='测试背景误报')
    assert audit.pending('EPISODE_1', 'run', 'rev') == []
    with get_session() as session:
        stored = session.get(ReviewIssue, issue['id'])
        assert set(json.loads(stored.resolution_json)['candidate_decisions']) == {'left', 'right'}


def test_current_recheck_pass_closes_old_presence_false_positive(monkeypatch, tmp_path):
    project, _, issue, _ = seed_review(monkeypatch, tmp_path)
    audit.publish(project, 'EPISODE_1', 'run', 'rev', [{
        'shot_id': 'SHOT_1',
        'ordinal': 1,
        'profile': audit.PROFILE,
        'candidates': [],
        'needs_review': False,
    }])

    assert audit.pending('EPISODE_1', 'run', 'rev') == []
    with get_session() as session:
        stored = session.get(ReviewIssue, issue['id'])
        assert stored.status == 'RESOLVED'
        assert json.loads(stored.resolution_json)['automated_recheck'] == 'PASS'


def test_snapshot_blocks_unresolved_presence():
    from engine.tests.v2.test_source_drama_snapshot_v1 import _read_model, _episode_snapshot
    from engine.app.source_drama_snapshot_v1 import SourceDramaSnapshotError
    data = _read_model()
    data['presence_review'] = {'1': 'REVIEW_1'}
    with pytest.raises(SourceDramaSnapshotError, match='出镜人物覆盖'):
        _episode_snapshot(data)
