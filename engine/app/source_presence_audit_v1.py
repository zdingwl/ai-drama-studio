"""模块 3/4：帧级出镜覆盖检查。检测/位置不是身份，所有修订保留人工决定。"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from sqlalchemy import select

from engine.app import studio_v2 as studio
from engine.app.review_issue_v1 import ReviewIssue, serialize_review_issue
from engine.app.person_presence_geometry_v1 import frame_boxes, valid_box

ISSUE_TYPE = "PERSON_PRESENCE"
PROFILE = "person-presence-coverage-v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def iou(a, b):
    x, y = max(a[0], b[0]), max(a[1], b[1])
    w = max(0, min(a[0] + a[2], b[0] + b[2]) - x)
    h = max(0, min(a[1] + a[3], b[1] + b[3]) - y)
    intersection = w * h
    return intersection / max(1e-9, a[2]*a[3] + b[2]*b[3] - intersection)


def uncovered_regions(detections, subjects, frame_index, *, review_all=False):
    """同帧一对一位置匹配；人数相同不代表覆盖正确，不跨帧/按姓名合并。"""
    locations = [(index, loc['box']) for index, person in enumerate(subjects)
                 for loc in frame_boxes(person.get('frame_boxes')) if loc['frame'] == frame_index]
    pairs = sorted(((iou(det['box'], box), d, s) for d, det in enumerate(detections)
                    for s, (_, box) in enumerate(locations)), reverse=True)
    matched_d, matched_s = set(), set()
    for score, d, s in pairs:
        if score >= .45 and d not in matched_d and s not in matched_s:
            matched_d.add(d); matched_s.add(s)
    rows = [{**det, 'reason': '重拉人物结构变化，请核对出镜身份' if review_all else '人体区域未被视觉人物可靠覆盖'}
            for d, det in enumerate(detections) if review_all or d not in matched_d]
    # 检测器也可能漏人；VLM 新增且未匹配到检测框的区域仍保留待核对。
    if review_all:
        rows.extend({'box': box, 'score': None, 'reason': '模型新增人物区域，身份待核对'}
                    for s, (_, box) in enumerate(locations) if s not in matched_s)
    return rows


@lru_cache(maxsize=1)
def detector():
    # 独立 CPU 检测，不占用 Qwen 显存，不加载 Face/ReID、不改变身份阈值。
    from engine.app.content_models_v2 import MODEL_SPECS, model_dir, _verify
    from engine.app.character_visual_v4 import _YoloXPersonDetector
    spec = next(s for s in MODEL_SPECS if s.logical_id == 'person_detection.yolox.2022nov')
    path = model_dir() / spec.filename
    _verify(path, spec)
    return _YoloXPersonDetector(path)


def frame_path(project_id, frame_id):
    if not isinstance(frame_id, str) or len(frame_id) != 64 or any(c not in '0123456789abcdef' for c in frame_id):
        raise ValueError('无效画面标识')
    return studio.workspace_root() / project_id / 'presence-evidence' / f'{frame_id}.jpg'


def inspect_shot(project_id, target, payload, *, previous_count=None, detect=None):
    """仅由显式分析 Worker 调用。图片内容寻址；框与生成它的原帧绑定。"""
    import cv2
    from engine.app.breakdown_p2_vlm_fast_grounded_v1 import frame_sample_ratios
    semantic = payload.get('exact_shot_semantic') or payload.get('semantic') or {}
    subjects = [s for s in semantic.get('subjects', []) if isinstance(s, dict)]
    ratios = (payload.get('exact_shot_grounding') or {}).get('frame_sample_ratios')
    ratios = ratios or list(frame_sample_ratios(target.duration_us))
    if not isinstance(ratios, list) or not ratios or len(ratios) > 12 or any(type(r) not in (int, float) or not math.isfinite(r) or not 0 <= r < 1 for r in ratios):
        raise ValueError('帧采样元数据无效，不能核对出镜覆盖')
    changed = previous_count is not None and len(subjects) != previous_count
    detect = detect or detector().detect
    rows, counts = [], []
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg or not Path(target.reference_clip_path).is_file():
        raise RuntimeError('出镜覆盖检查缺少 ffmpeg 或当前版本视频，不能宣称检查通过')
    with tempfile.TemporaryDirectory(prefix='presence-coverage-') as temp:
        for index, ratio in enumerate(ratios, 1):
            offset = min(max(0, target.duration_us * ratio / 1_000_000), max(0, target.duration_us / 1_000_000 - .01))
            path = Path(temp) / f'{index}.jpg'
            subprocess.run([ffmpeg, '-y', '-ss', f'{offset:.6f}', '-i', target.reference_clip_path,
                            '-frames:v', '1', '-q:v', '2', str(path)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
            frame = cv2.imread(str(path))
            if frame is None:
                raise RuntimeError('出镜核对帧读取失败')
            h, w = frame.shape[:2]
            detections = [{'box': [x/w, y/h, bw/w, bh/h], 'score': float(score)}
                          for (x,y,bw,bh), score in detect(frame)]
            counts.append(len(detections))
            candidates = uncovered_regions(detections, subjects, index, review_all=changed)
            if changed and not candidates:
                candidates = [{'box': None, 'score': None, 'reason': '人数变化但无可靠定位，请核对本帧并手动框人'}]
            if not candidates:
                continue
            frame_id = hashlib.sha256(path.read_bytes()).hexdigest()
            dest = frame_path(project_id, frame_id)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copyfile(path, dest)
            url = f'/api/projects/{project_id}/presence-frames/{frame_id}'
            for candidate in candidates:
                candidate.update(frame_id=frame_id, frame_index=index, image_url=url,
                                 source_time_us=target.start_us + round(offset*1_000_000))
                candidate['id'] = digest(candidate)[:24]
                rows.append(candidate)
    return dict(profile=PROFILE, ordinal=target.ordinal, shot_id=target.original_shot_id,
                revision_item_id=target.revision_item_id, start_us=target.start_us, end_us=target.end_us,
                subject_count=len(subjects), detector_counts=counts, candidates=rows,
                structure_changed=changed,
                # 即便检测框为空，人数变化也不能变成“检查通过”。
                needs_review=bool(rows) or changed)


def publish(project_id, episode_id, run_id, revision_id, audits):
    """一个镜头一个根问题；重复发布不清除决定，新证据不继承旧确认。"""
    with studio.get_session() as session:
        for audit in audits:
            if not audit['needs_review']:
                continue
            payload = {**audit, 'run_id': run_id, 'shot_revision_id': revision_id}
            fingerprint = digest(payload)
            key = f'presence:{run_id}:{audit["shot_id"]}:{fingerprint[:20]}'
            if session.scalar(select(ReviewIssue).where(ReviewIssue.project_id == project_id, ReviewIssue.source_key == key)):
                continue
            # 同版本重跑产生不同证据时，旧问题保留历史但不再计入当前队列。
            for old in session.scalars(select(ReviewIssue).where(ReviewIssue.project_id == project_id, ReviewIssue.shot_id == audit['shot_id'], ReviewIssue.issue_type == ISSUE_TYPE, ReviewIssue.status == 'OPEN')):
                old.status = 'RESOLVED'
                old.resolution_json = json.dumps({'superseded_by': key})
                old.resolved_at = studio.utcnow()
            payload['fingerprint'] = fingerprint
            session.add(ReviewIssue(id=studio.new_id('REVIEW'), project_id=project_id, episode_id=episode_id,
                shot_id=audit['shot_id'], source_key=key, issue_type=ISSUE_TYPE, severity='BLOCKING', status='OPEN',
                reason='出镜人物覆盖待核对（检测框不是正式身份）', ai_suggestion_json=json.dumps(payload, ensure_ascii=False)))
        session.commit()


def inspect_artifact(context, artifact):
    raw = json.loads(Path(artifact.path).read_text(encoding='utf-8'))
    records = {item.get('shot_revision_item_id'): item.get('payload', {}) for item in raw.get('evidence', [])}
    return [inspect_shot(context.project_id, shot, records.get(shot.revision_item_id, {})) for shot in context.shots]


def pending(episode_id, run_id, revision_id):
    with studio.get_session() as session:
        rows = session.scalars(select(ReviewIssue).where(ReviewIssue.episode_id == episode_id, ReviewIssue.issue_type == ISSUE_TYPE, ReviewIssue.status == 'OPEN')).all()
        return [serialize_review_issue(row) for row in rows
                if (data := json.loads(row.ai_suggestion_json or '{}')).get('run_id') == run_id
                and data.get('shot_revision_id') == revision_id]


def is_current(issue):
    from engine.app.breakdown_serializer_v1 import get_current_breakdown
    from engine.app.breakdown_shot_rerun_v1 import _anchors
    draft = get_current_breakdown(issue['episode_id'])
    if not draft:
        return False
    run_id, _, _, revision_id = _anchors(draft)
    data = issue.get('ai_suggestion') or {}
    return data.get('run_id') == run_id and data.get('shot_revision_id') == revision_id
