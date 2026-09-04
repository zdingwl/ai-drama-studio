from copy import deepcopy
import pytest
from sqlalchemy import select
from engine.tests.v2.test_character_assets_workflow_v1 import setup
from engine.app import source_person_assets_v1 as people
from engine.app import source_presence_correction_v1 as presence
from engine.app.asset_workspace_v3 import ShotCharacterBinding, AssetRevision
from engine.app.studio_v2 import get_session


def test_supplement_is_scoped_versioned_and_does_not_change_frozen_evidence(monkeypatch, tmp_path):
    project, timeline = setup(monkeypatch, tmp_path)
    missing = timeline['scenes'][1]['shots'][0]
    missing['people'] = []
    missing['thumbnail_url'] = '/revision-frame-2'
    timeline['scenes'][0]['shots'].append(missing)
    timeline['scenes'] = timeline['scenes'][:1]
    frozen = deepcopy(timeline)
    inv = people.inventory(project)
    bound = people.assign(project, [inv['observations'][0]['key']], '徐然', None, inv['revision'])
    character = bound['characters'][0]['id']
    ctx = presence.context(project, 'SHOT_2')
    mark = dict(shot_id='SHOT_2', image_url='/revision-frame-2', box=[.1, .2, .3, .4], source='MANUAL_BOX')
    with pytest.raises(ValueError, match='版本已更新'):
        presence.supplement(project, 'SHOT_2', character, mark, 'old')
    with pytest.raises(ValueError, match='框出'):
        presence.supplement(project, 'SHOT_2', character, {**mark, 'image_url': '/wrong'}, ctx['revision'])
    saved = presence.supplement(project, 'SHOT_2', character, mark, ctx['revision'])
    assert saved['revision'] != ctx['revision']
    assert timeline == frozen
    with get_session() as session:
        assert set(session.scalars(select(ShotCharacterBinding.shot_id).where(ShotCharacterBinding.character_id == character))) == {'SHOT_1', 'SHOT_2'}
        revision_count = len(list(session.scalars(select(AssetRevision))))
    presence.supplement(project, 'SHOT_2', character, mark, saved['revision'])
    with get_session() as session:
        assert len(list(session.scalars(select(AssetRevision)))) == revision_count
    result = {'timeline': timeline, 'identity': {'scenes': [{'scene_ordinal': 1, 'people': [{'ref': 'P1', 'character': {'id': character}}]}]}}
    assert presence.overlay(result, 'EPISODE_1') == {'2': ['P1']}
    timeline['source_shot_revision_id'] = 'new'
    assert presence.overlay(result, 'EPISODE_1') == {}
