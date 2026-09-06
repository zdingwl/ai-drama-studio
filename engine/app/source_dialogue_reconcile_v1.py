"""模块 3：时间对齐的字幕校正。原始 ASR/OCR 不变，只生成带来源的派生对白。

底部文字只是字幕候选：需多帧稳定且与音频文本相符才自动校正。
无 ASR 或严重冲突保留候选供人工决定，不把招牌/水印直接变成台词。
"""
from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher
import math
import re

from engine.app.breakdown_p2_sidecar_v1 import P2ProviderResult
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from engine.app.studio_v2 import Base


class SourceDialogueTextDecision(Base):
    """正式源对白修订；证据、原始 ASR/OCR 以及旧 Run 始终保留。"""
    __tablename__ = "v2_source_dialogue_text_decisions"
    review_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    episode_id: Mapped[str] = mapped_column(String(80), index=True)
    run_id: Mapped[str] = mapped_column(String(80), index=True)
    decision_json: Mapped[str] = mapped_column(Text)

PROFILE = "time-aligned-subtitle-correction-v1"


def _text(value):
    return re.sub(r"[\W_]+", "", str(value or "")).casefold()


def subtitle_candidates(ocr: P2ProviderResult) -> list[dict]:
    groups: list[dict] = []
    for record in sorted(ocr.evidence, key=lambda r: (r.source_start_us or 0, r.source_id)):
        if record.source_type != "OCR_OBSERVATION" or record.source_start_us is None:
            continue
        polygon = record.payload.get("polygon_norm")
        score = record.confidence
        if not polygon or score is None or not math.isfinite(score) or score < .92 or not _text(record.text):
            continue
        try:
            xs, ys = zip(*polygon)
            # 排除角落水印、竖排文字及常见顶部标题。几何不是字幕的唯一判据。
            if min(ys) < .55 or max(ys) - min(ys) > .22 or max(xs) - min(xs) < .12:
                continue
            if not .2 <= (min(xs) + max(xs)) / 2 <= .8:
                continue
        except (TypeError, ValueError):
            continue
        match = next((g for g in reversed(groups) if g["normalized"] == _text(record.text)
                      and 0 <= record.source_start_us - g["last_us"] <= 800_000), None)
        if match is None:
            match = dict(text=record.text, normalized=_text(record.text), start_us=record.source_start_us,
                         last_us=record.source_start_us, times=set(), evidence_ids=[], confidence=score)
            groups.append(match)
        match["last_us"] = record.source_start_us
        match["times"].add(record.source_start_us)
        match["evidence_ids"].append(record.source_id)
        match["confidence"] = min(score, match["confidence"])
    result = []
    for group in groups:
        if len(group["times"]) < 2:
            continue
        result.append({k: v for k, v in group.items() if k not in {"times", "normalized", "last_us"}} |
                      {"end_us": group["last_us"] + 500_000, "sample_count": len(group["times"])})
    return result


def reconcile(asr: P2ProviderResult, ocr: P2ProviderResult) -> P2ProviderResult:
    """保持 utterance ID/音频时间不变；修正文字不能重新使用旧 ASR 单词拼回原文。"""
    candidates = subtitle_candidates(ocr)
    records, decisions, used = [], [], set()
    segments = [r for r in asr.evidence if r.source_type == "ASR_SEGMENT"]
    corrected_ids = set()
    for record in asr.evidence:
        if record.source_type != "ASR_SEGMENT" or record.source_start_us is None or record.source_end_us is None:
            records.append(record)
            continue
        overlaps = [(i, c) for i, c in enumerate(candidates)
                    if min(c["end_us"], record.source_end_us) > max(c["start_us"], record.source_start_us)]
        if not overlaps:
            records.append(record)
            continue
        index, candidate = overlaps[0]
        if len(overlaps) > 1:
            candidate = {**candidate, "text": " ".join(c["text"] for _, c in overlaps),
                         "evidence_ids": [eid for _, c in overlaps for eid in c["evidence_ids"]]}
        # 一条字幕同时覆盖多个 ASR 句子时，不把整句复制给每个片段。
        owners = [s for s in segments if s.source_start_us is not None and s.source_end_us is not None
                  and min(candidate["end_us"], s.source_end_us) > max(candidate["start_us"], s.source_start_us)]
        similarity = SequenceMatcher(None, _text(record.text), _text(candidate["text"])).ratio()
        supported = (len(overlaps) == 1 and len(owners) == 1 and .65 <= similarity < 1 and len(_text(record.text)) >= 4
                     and record.confidence is not None and record.confidence < .85)
        if similarity == 1:
            used.add(index)
            records.append(record)
            continue
        decision = dict(profile=PROFILE, status="CORRECTED" if supported else "REVIEW",
                        utterance_id=record.source_id, asr_text=record.text,
                        requires_full_text=len(owners) != 1,
                        subtitle_text=candidate["text"], evidence_ids=candidate["evidence_ids"],
                        start_us=record.source_start_us, end_us=record.source_end_us)
        decisions.append(decision)
        used.update(i for i, _ in overlaps)
        if supported:
            corrected_ids.add(record.source_id)
            records.append(replace(record, text=candidate["text"], payload={**record.payload, "dialogue_correction": decision}))
        else:
            records.append(record)
    for index, candidate in enumerate(candidates):
        if index not in used:
            decisions.append({**candidate, "profile": PROFILE, "status": "REVIEW", "asr_text": None,
                              "subtitle_text": candidate["text"], "reason": "字幕缺少可靠音频对应，请确认是否为对白"})
    # 原始 word 仍留在不可变 sidecar，派生文本不能受错误单词覆盖。
    records = [r for r in records if not (r.source_type == "ASR_WORD" and r.payload.get("segment_id") in corrected_ids)]
    return replace(asr, evidence=tuple(records), metadata={**asr.metadata, "dialogue_reconciliation": decisions})


def publish_reviews(project_id, episode_id, run_id, revision_id, decisions, *, scope=None, scope_range=None):
    """显式 Worker 发布，一个完整台词冲突只建一个正式决定。"""
    import hashlib
    import json
    from sqlalchemy import select
    from engine.app import studio_v2 as studio
    from engine.app.review_issue_v1 import ReviewIssue
    with studio.get_session() as session:
        for previous in session.scalars(select(ReviewIssue).where(ReviewIssue.episode_id == episode_id,
                                                                 ReviewIssue.issue_type == "SOURCE_DIALOGUE")):
            old = json.loads(previous.ai_suggestion_json or "{}")
            replaced = (scope is not None and (old.get("scope") == scope or
                        (scope_range and min(old.get("end_us", 0), scope_range[1]) > max(old.get("start_us", 0), scope_range[0]))))
            if old.get("run_id") != run_id or old.get("shot_revision_id") != revision_id or replaced:
                previous.status = "SUPERSEDED"
                previous.updated_at = studio.utcnow()
        for decision in decisions:
            if decision["status"] != "REVIEW":
                continue
            payload = {**decision, "run_id": run_id, "shot_revision_id": revision_id, "scope": scope}
            key = "dialogue:" + hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            existing = session.scalar(select(ReviewIssue).where(ReviewIssue.project_id == project_id, ReviewIssue.source_key == key))
            if existing:
                # 同一不可变输入重试复用原决定；新证据形成新 key。
                if existing.status == "SUPERSEDED":
                    existing.status = "RESOLVED" if session.get(SourceDialogueTextDecision, existing.id) else "OPEN"
                continue
            session.add(ReviewIssue(id=studio.new_id("REVIEW"), project_id=project_id, episode_id=episode_id,
                                    source_key=key, issue_type="SOURCE_DIALOGUE", severity="BLOCKING", status="OPEN",
                                    reason="语音与字幕存在差异，请确认完整源对白",
                                    ai_suggestion_json=json.dumps(payload, ensure_ascii=False)))
        session.commit()


def reviews(episode_id, run_id, revision_id):
    import hashlib
    import json
    from sqlalchemy import select
    from engine.app.studio_v2 import get_session
    from engine.app.review_issue_v1 import ReviewIssue
    result = []
    with get_session() as session:
        for issue in session.scalars(select(ReviewIssue).where(ReviewIssue.episode_id == episode_id, ReviewIssue.issue_type == "SOURCE_DIALOGUE")):
            data = json.loads(issue.ai_suggestion_json or "{}")
            if issue.status == "SUPERSEDED" or data.get("run_id") != run_id or data.get("shot_revision_id") != revision_id:
                continue
            formal = session.get(SourceDialogueTextDecision, issue.id)
            result.append({**data, "id": issue.id, "status": issue.status,
                           "decision": json.loads(formal.decision_json) if formal else {},
                           "revision": hashlib.sha256((issue.ai_suggestion_json + (issue.resolution_json or "")).encode()).hexdigest()})
    return result


def apply_reviews(draft, timeline):
    """只读投影，字幕补漏形成一个 utterance，跨镜使用同一个 ID。"""
    from copy import deepcopy
    run = draft["run"]
    decisions = reviews(run["episode_id"], run["id"], run["source_shot_revision_id"])
    if not decisions:
        return timeline
    output = deepcopy(timeline)
    for item in decisions:
        if item["status"] != "RESOLVED" or not item["decision"].get("text"):
            continue
        text = item["decision"]["text"]
        for scene in output["scenes"]:
            for shot in scene["shots"]:
                matches = [d for d in shot["dialogue"] if d.get("dialogue_group_id") == item.get("utterance_id")]
                if item.get("utterance_id"):
                    for dialogue in matches:
                        dialogue["text"] = text
                else:
                    start, end = max(shot["start_us"], item["start_us"]), min(shot["end_us"], item["end_us"])
                    if end > start:
                        group_id = f'SUBTITLE:{item["id"]}'
                        shot["dialogue"] = [d for d in shot["dialogue"] if d.get("dialogue_group_id") != group_id]
                        shot["dialogue"].append(dict(dialogue_group_id=group_id, start_us=start,
                                                     end_us=end, text=text, speakers=[], source_language=None))
                        shot["dialogue"].sort(key=lambda d: (d["start_us"], d["end_us"]))
    return output


def decide(episode_id, review_id, revision, choice, text=None):
    import json
    from engine.app import studio_v2 as studio
    from engine.app.breakdown_serializer_v1 import get_current_breakdown
    from engine.app.review_issue_v1 import ReviewIssue
    from engine.app.source_person_assets_v1 import LOCK
    with LOCK:
        draft = get_current_breakdown(episode_id)
        if not draft or not draft["run"].get("is_current"):
            raise ValueError("源对白版本已变化，请刷新")
        run = draft["run"]
        item = next((r for r in reviews(episode_id, run["id"], run["source_shot_revision_id"]) if r["id"] == review_id), None)
        if not item or item["revision"] != revision or item["status"] != "OPEN":
            raise ValueError("对白已更新或已确认，请刷新")
        if choice == "SUBTITLE":
            if item.get("requires_full_text"):
                raise ValueError("字幕仅覆盖部分完整对白，请编辑确认整句台词")
            selected = item.get("subtitle_text")
        elif choice == "ASR":
            selected = item.get("asr_text")
        elif choice == "EDIT":
            selected = str(text or "").strip()
        elif choice == "NOT_DIALOGUE" and not item.get("utterance_id"):
            selected = None
        else:
            raise ValueError("请选择有效的对白修正方式")
        if choice != "NOT_DIALOGUE" and (not selected or len(selected) > 4000):
            raise ValueError("对白不能为空或超过 4000 字")
        if item["end_us"] <= item["start_us"]:
            raise ValueError("对白时间无效")
        from engine.app.breakdown_scene_timeline_result_v1 import build_scene_timeline_result_v1
        timeline = build_scene_timeline_result_v1(draft)
        shots = [shot for scene in timeline["scenes"] for shot in scene["shots"]]
        if item.get("utterance_id"):
            if not any(d.get("dialogue_group_id") == item["utterance_id"] for shot in shots for d in shot["dialogue"]):
                raise ValueError("源对白对应关系已变化，需重新拉片后核对")
        elif not any(min(shot["end_us"], item["end_us"]) > max(shot["start_us"], item["start_us"]) for shot in shots):
            raise ValueError("字幕不属于当前分镜版本")
        decision = dict(text=selected, choice=choice, source_revision=revision, decided_at=studio.utcnow().isoformat())
        with studio.get_session() as session:
            # 主键防止并发重复保存；业务修订与 Review 状态在同一事务提交。
            session.add(SourceDialogueTextDecision(review_id=review_id, episode_id=episode_id, run_id=run["id"],
                                                  decision_json=json.dumps(decision, ensure_ascii=False)))
            issue = session.get(ReviewIssue, review_id)
            issue.status, issue.resolved_at, issue.updated_at = "RESOLVED", studio.utcnow(), studio.utcnow()
            issue.resolution_json = json.dumps({"source_dialogue_decision_id": review_id, "validated": True})
            session.commit()
        return decision
