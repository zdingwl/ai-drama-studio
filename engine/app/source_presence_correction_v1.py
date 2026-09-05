"""模块 4：漏人补录，保留冻结模型输出，以版本化人工证据补充出镜关系。"""
import json
from sqlalchemy import select
from engine.app import source_person_assets_v1 as people
from engine.app.asset_workspace_v3 import ShotCharacterBinding, _manual_revision
from engine.app.studio_v2 import Character, Shot, Episode, get_session, new_id
from engine.app import source_presence_audit_v1 as audit
from engine.app.review_issue_v1 import ReviewIssue

KEY = 'manual_shot_presences_v1'


def context(project_id, shot_id):
    workspace = people.inventory(project_id)
    with get_session() as session:
        shot = session.get(Shot, shot_id)
        if shot is None:
            raise ValueError('镜头不存在')
        episode_id, ordinal = shot.episode_id, shot.ordinal
        episode = session.get(Episode, episode_id)
        if not episode or episode.project_id != project_id:
            raise ValueError('镜头不属于当前项目的有效人物审核范围')
    draft = people.get_current_breakdown(episode_id)
    timeline = people.build_scene_timeline_result_v1(draft) if draft else None
    if not timeline or not timeline.get('is_current'):
        raise ValueError('本集拉片结果未就绪或已过期')
    scene = next((s for s in timeline['scenes'] if any(h['ordinal'] == ordinal for h in s['shots'])), None)
    if not scene:
        raise ValueError('当前版本没有此镜头')
    frame = next(h for h in scene['shots'] if h['ordinal'] == ordinal)
    candidates = {}
    for row in workspace['observations']:
        if row['episode_id'] == episode_id and row['scene_ordinal'] == scene['ordinal'] and row.get('character_id') and not row.get('identity_issue'):
            candidates.setdefault(row['character_id'], row['ref'])
    reviews = [r for r in audit.pending(episode_id, timeline['source_breakdown_run_id'], timeline['source_shot_revision_id']) if r['shot_id'] == shot_id]
    return dict(revision=workspace['revision'], shot_id=shot_id, episode_id=episode_id, ordinal=ordinal,
                scene_ordinal=scene['ordinal'], run_id=timeline['source_breakdown_run_id'],
                shot_revision_id=timeline['source_shot_revision_id'], image_url=frame.get('thumbnail_url'),
                candidates=[{**c, 'ref': candidates[c['id']]} for c in workspace['characters'] if c['id'] in candidates],
                reviews=reviews)


def supplement(project_id, shot_id, character_id, mark, expected_revision, *, issue_id=None, candidate_id=None, decision='BIND', reason=''):
    with people.LOCK:
        current = context(project_id, shot_id)
        if current['revision'] != expected_revision:
            raise ValueError('原片人物版本已更新，请重新核对')
        review = next((r for r in current['reviews'] if r['id'] == issue_id), None) if issue_id else None
        region = next((r for r in review['ai_suggestion']['candidates'] if r['id'] == candidate_id), None) if review else None
        if issue_id and not region:
            raise ValueError('漏人核对证据已更新，请重新打开')
        if region and decision == 'NOT_PERSON' and not region.get('box'):
            raise ValueError('人数结构变化需要人物核对，不能作为检测误报关闭')
        if decision not in ('BIND', 'NOT_PERSON') or (decision == 'NOT_PERSON' and (not region or len(reason.strip()) < 2)):
            raise ValueError('请提交明确的人物绑定或带原因的检测误报修正')
        candidate = next((c for c in current['candidates'] if c['id'] == character_id), None)
        if decision == 'BIND' and not candidate:
            raise ValueError('请选择当前场景已确认的正式人物；身份不确定时不要提交')
        image_url = region['image_url'] if region else current['image_url']
        row = {'shots': [{'id': shot_id, 'thumbnail_url': image_url}]}
        if decision == 'BIND' and (not people._valid_localization(row, mark) or mark.get('source') != 'MANUAL_BOX'):
            raise ValueError('请在当前版本原图框出漏掉的人物')
        if region and decision == 'BIND' and region.get('box') and audit.iou(region['box'], mark['box']) < .2:
            raise ValueError('框选偏离待核对区域，请框选该区域中的人物')
        evidence = {k: current[k] for k in ('episode_id', 'ordinal', 'scene_ordinal', 'run_id', 'shot_revision_id')}
        if candidate:
            evidence.update(shot_id=shot_id, ref=candidate['ref'], localization=mark)
            if region:
                evidence.update(presence_issue_id=issue_id, presence_candidate_id=candidate_id)
        with get_session() as session:
            review_row = session.get(ReviewIssue, issue_id) if region else None
            if region and (not review_row or review_row.status != 'OPEN'):
                raise ValueError('该审核已更新，请重新打开')
            decisions = json.loads(review_row.editable_payload_json or '{}') if review_row else {}
            if region and candidate_id in decisions:
                raise ValueError('该区域已经核对，请刷新，不能覆盖已有决定')
            if region and decision == 'BIND':
                for other in review['ai_suggestion']['candidates']:
                    prior = decisions.get(other['id'], {})
                    if (prior.get('character_id') == character_id and other['image_url'] == region['image_url']
                            and prior.get('localization') and audit.iou(prior['localization']['box'], mark['box']) < .45):
                        raise ValueError('同一画面不同人体区域不能确认成同一个人物')
            if decision == 'NOT_PERSON':
                _save_region_decision(session, review_row, decisions, region, {'decision': decision, 'reason': reason.strip()})
                _manual_revision(session, project_id, '人工修正出镜检测误报')
                session.commit()
                return context(project_id, shot_id)
            character = session.get(Character, character_id)
            if not character or character.project_id != project_id:
                raise ValueError('人物不属于当前项目')
            meta = people._json(character.metadata_json)
            existing = meta.get(KEY, [])
            binding = session.scalar(select(ShotCharacterBinding).where(ShotCharacterBinding.project_id == project_id, ShotCharacterBinding.shot_id == shot_id, ShotCharacterBinding.character_id == character_id))
            if evidence in existing and binding and not region:
                return current
            # 每个精确帧保留独立确认记录，不能用后一帧覆盖前一帧人工证据。
            meta[KEY] = existing if evidence in existing else existing + [evidence]
            character.metadata_json = json.dumps(meta, ensure_ascii=False)
            if not binding:
                session.add(ShotCharacterBinding(id=new_id('SHOTCHAR'), project_id=project_id, shot_id=shot_id, character_id=character_id, source='MANUAL'))
            if region:
                _save_region_decision(session, review_row, decisions, region, {'decision': 'BIND', 'character_id': character_id, 'localization': mark})
            _manual_revision(session, project_id, f'补充镜头 {current["ordinal"]} 出镜人物及框选证据')
            session.commit()
        return context(project_id, shot_id)


def _save_region_decision(session, review, decisions, region, value):
    from engine.app.studio_v2 import utcnow
    decisions[region['id']] = {**value, 'decided_at': utcnow().isoformat()}
    review.editable_payload_json = json.dumps(decisions, ensure_ascii=False)
    review.updated_at = utcnow()
    candidates = json.loads(review.ai_suggestion_json)['candidates']
    # 每个实际证据区域都有正式决定后才关闭；未确定身份没有“已处理”捷径。
    if candidates and all(item['id'] in decisions for item in candidates):
        review.status = 'RESOLVED'
        review.resolved_at = utcnow()
        review.resolution_json = json.dumps({'candidate_decisions': decisions}, ensure_ascii=False)


def _evidence_frame(session, evidence, fallback):
    """接受当前版本审核生成的精确帧，不能用其他镜头/任意 URL 代替。"""
    if not evidence.get('presence_issue_id'):
        return fallback
    issue = session.get(ReviewIssue, evidence['presence_issue_id'])
    if not issue or issue.shot_id != evidence['shot_id']:
        return None
    data = json.loads(issue.ai_suggestion_json or '{}')
    if data.get('run_id') != evidence['run_id'] or data.get('shot_revision_id') != evidence['shot_revision_id']:
        return None
    region = next((r for r in data.get('candidates', []) if r['id'] == evidence.get('presence_candidate_id')), None)
    return region['image_url'] if region else None


def overlay(result, episode_id):
    if not result or not result['timeline'].get('is_current'):
        return {}
    timeline = result['timeline']
    output = {}
    with get_session() as session:
        bindings = list(session.execute(select(ShotCharacterBinding, Character).join(Character, Character.id == ShotCharacterBinding.character_id).join(Shot, Shot.id == ShotCharacterBinding.shot_id).where(Shot.episode_id == episode_id)))
        for binding, character in bindings:
            for evidence in people._json(character.metadata_json).get(KEY, []):
                if evidence.get('shot_id') != binding.shot_id or evidence.get('episode_id') != episode_id or evidence.get('run_id') != timeline['source_breakdown_run_id'] or evidence.get('shot_revision_id') != timeline['source_shot_revision_id']:
                    continue
                scene = next((s for s in result['identity']['scenes'] if s['scene_ordinal'] == evidence['scene_ordinal']), None)
                if not scene or not any(p['ref'] == evidence['ref'] and (p.get('character') or {}).get('id') == character.id for p in scene['people']):
                    continue
                source_scene = next((s for s in timeline['scenes'] if s['ordinal'] == evidence['scene_ordinal']), None)
                frame = next((s for s in (source_scene or {}).get('shots', []) if s['ordinal'] == evidence['ordinal']), None)
                if not frame or not people._valid_localization({'shots': [{'id': binding.shot_id, 'thumbnail_url': _evidence_frame(session, evidence, frame.get('thumbnail_url'))}]}, evidence['localization']):
                    continue
                output.setdefault(str(evidence['ordinal']), []).append(evidence['ref'])
    return {key: sorted(set(refs)) for key, refs in output.items()}
