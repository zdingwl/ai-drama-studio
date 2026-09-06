from copy import deepcopy
from dataclasses import replace
import json

import cv2
import numpy as np
import pytest
from sqlalchemy import select

from engine.app import source_dialogue_reconcile_v1 as dialogue
from engine.app import source_person_capture_v2 as capture
from engine.app import source_person_assets_v1 as people
from engine.app import studio_v2 as studio
from engine.app.breakdown_p2_sidecar_v1 import P2EvidenceRecord as Evidence, P2ProviderResult as Result
from engine.app.review_issue_v1 import ReviewIssue
from engine.tests.v2.test_character_assets_workflow_v1 import setup


def evidence(confidence=.4):
    asr = Result(component="ASR", provider="test", model="test", status="READY", evidence=(
        Evidence(source_type="ASR_SEGMENT", source_id="UTTERANCE", text="你今天怎么来乐", confidence=confidence,
                 source_start_us=0, source_end_us=2_000_000),
        Evidence(source_type="ASR_WORD", source_id="WORD", text="来乐", payload={"segment_id": "UTTERANCE"}),
    ))
    ocr = Result(component="OCR", provider="test", model="test", status="READY", evidence=tuple(
        Evidence(source_type="OCR_OBSERVATION", source_id=f"OCR{i}", text="你今天怎么来了", confidence=.99,
                 source_start_us=t, source_end_us=t+1,
                 payload={"polygon_norm": [[.2,.8],[.8,.8],[.8,.88],[.2,.88]]})
        for i,t in enumerate((200_000,700_000,1_200_000))
    ))
    return asr, ocr


def test_ocr_correction_keeps_raw_evidence_and_utterance_time():
    asr, ocr = evidence()
    before = deepcopy(asr)
    result = dialogue.reconcile(asr, ocr)
    assert asr == before
    assert len(result.evidence) == 1
    assert result.evidence[0].text == "你今天怎么来了"
    assert result.evidence[0].source_id == "UTTERANCE"
    assert result.evidence[0].source_end_us == 2_000_000
    assert result.metadata["dialogue_reconciliation"][0]["status"] == "CORRECTED"


def test_reliable_conflict_and_missing_asr_require_human_decision():
    asr, ocr = evidence(.95)
    result = dialogue.reconcile(asr, ocr)
    assert result.evidence == asr.evidence
    assert result.metadata["dialogue_reconciliation"][0]["status"] == "REVIEW"
    missing = dialogue.reconcile(replace(asr, evidence=(), status="NO_EVIDENCE"), ocr)
    assert not missing.evidence
    assert missing.metadata["dialogue_reconciliation"][0]["asr_text"] is None
    top = replace(ocr, evidence=tuple(replace(r,payload={"polygon_norm": [[.2,.1],[.8,.1],[.8,.2],[.2,.2]]}) for r in ocr.evidence))
    assert not dialogue.subtitle_candidates(top)


def review_setup(monkeypatch, tmp_path, *, missing=False):
    project, timeline = setup(monkeypatch, tmp_path)
    for scene in timeline["scenes"]:
        for shot in scene["shots"]:
            shot["dialogue"] = [] if missing else [{"dialogue_group_id": "UTTERANCE", "text": "旧对白"}]
    draft = {"run": {"id":"run", "episode_id":"EPISODE_1", "source_shot_revision_id":"rev", "is_current":True}}
    from engine.app import breakdown_serializer_v1, breakdown_scene_timeline_result_v1
    monkeypatch.setattr(breakdown_serializer_v1, "get_current_breakdown", lambda _: draft)
    monkeypatch.setattr(breakdown_scene_timeline_result_v1, "build_scene_timeline_result_v1", lambda _: deepcopy(timeline))
    asr,ocr = evidence(.95)
    if missing:
        asr = replace(asr, evidence=())
    decisions = dialogue.reconcile(asr,ocr).metadata["dialogue_reconciliation"]
    dialogue.publish_reviews(project,"EPISODE_1","run","rev",decisions)
    return project, timeline, draft, decisions


@pytest.mark.parametrize("missing", [False, True])
def test_formal_text_decision_projects_one_utterance_across_shots(monkeypatch,tmp_path,missing):
    project,timeline,draft,decisions = review_setup(monkeypatch,tmp_path,missing=missing)
    row = dialogue.reviews("EPISODE_1","run","rev")[0]
    dialogue.decide("EPISODE_1",row["id"],row["revision"],"SUBTITLE")
    applied = dialogue.apply_reviews(draft,timeline)
    projections = [s["dialogue"][0] for c in applied["scenes"] for s in c["shots"]]
    assert {d["text"] for d in projections} == {"你今天怎么来了"}
    assert len({d["dialogue_group_id"] for d in projections}) == 1
    assert dialogue.apply_reviews(draft,applied) == applied
    with studio.get_session() as session:
        assert session.get(dialogue.SourceDialogueTextDecision,row["id"])
    with pytest.raises(ValueError,match="已更新"):
        dialogue.decide("EPISODE_1",row["id"],row["revision"],"SUBTITLE")


def test_unmapped_utterance_cannot_resolve_and_scoped_rerun_retires_old_conflict(monkeypatch,tmp_path):
    project,timeline,draft,decisions = review_setup(monkeypatch,tmp_path)
    row = dialogue.reviews("EPISODE_1","run","rev")[0]
    for c in timeline["scenes"]:
        c["shots"][0]["dialogue"] = []
    with pytest.raises(ValueError,match="对应关系"):
        dialogue.decide("EPISODE_1",row["id"],row["revision"],"SUBTITLE")
    assert dialogue.reviews("EPISODE_1","run","rev")[0]["status"] == "OPEN"
    dialogue.publish_reviews(project,"EPISODE_1","run","rev",[],scope=1,scope_range=(0,1_000_000))
    assert not dialogue.reviews("EPISODE_1","run","rev")


def test_partial_subtitle_requires_editing_the_complete_utterance(monkeypatch,tmp_path):
    project,timeline,draft,decisions = review_setup(monkeypatch,tmp_path)
    decisions[0]["requires_full_text"] = True
    dialogue.publish_reviews(project,"EPISODE_1","run","rev",decisions,scope=1,scope_range=(0,1_000_000))
    row=dialogue.reviews("EPISODE_1","run","rev")[0]
    with pytest.raises(ValueError,match="完整对白"):
        dialogue.decide("EPISODE_1",row["id"],row["revision"],"SUBTITLE")
    dialogue.decide("EPISODE_1",row["id"],row["revision"],"EDIT","已经核对的完整台词")
    applied=dialogue.apply_reviews(draft,timeline)
    assert {s["dialogue"][0]["text"] for c in applied["scenes"] for s in c["shots"]} == {"已经核对的完整台词"}


def store_image(project,row,image_id,quality):
    with studio.get_session() as session:
        session.add(capture.SourcePersonImage(id=image_id,project_id=project,episode_id=row["episode_id"],
                    shot_id=row["shots"][0]["id"],observation_key=row["key"],anchor=row["anchor"],image=b"PNG",mask=b"MASK",
                    evidence_json=json.dumps({"display_quality":quality})))
        session.commit()


def test_merge_uses_one_best_cover_retains_images_and_rejects_stale_capture(monkeypatch,tmp_path):
    project,_ = setup(monkeypatch,tmp_path)
    before = people.inventory(project)
    a,b = before["observations"]
    store_image(project,a,"low",.2)
    store_image(project,a,"best",.95)
    store_image(project,b,"side",.6)
    inv = people.inventory(project)
    marks = {r["key"]:r["extracted_localization"] for r in inv["observations"]}
    saved = people.assign(project,list(marks),"同一人物",None,inv["revision"],marks)
    assert saved["characters"][0]["cover_url"] == capture.image_url("best")
    assert saved["characters"][0]["shot_ids"] == ["SHOT_1","SHOT_2"]
    assert "gallery" not in saved["characters"][0]
    with studio.get_session() as session:
        assert len(session.scalars(select(capture.SourcePersonImage)).all()) == 3
        session.add(capture.SourcePersonCaptureState(id="state",observation_key=a["key"],shot_id="SHOT_1",anchor=a["anchor"],image_ids_json="[]"))
        session.commit()
    assert not capture.valid_mark(a,marks[a["key"]])
    assert people.inventory(project)["characters"][0]["cover_url"] == capture.image_url("side")


def test_mask_contains_only_model_foreground_inside_one_person():
    class Segmenter:
        def setInput(self, blob):
            assert blob.shape == (1,3,192,192)
        def forward(self):
            logits=np.zeros((1,2,192,192),np.float32)
            logits[:,0]=1
            logits[:,1,20:175,30:165]=2
            return logits
    png,mask = capture.isolate(np.full((100,100,3),127,np.uint8),(10,10,70,80),
                               segmenter=Segmenter(),other_boxes=[(60,0,40,100)])
    rgba=cv2.imdecode(np.frombuffer(png,np.uint8),cv2.IMREAD_UNCHANGED)
    alpha=cv2.imdecode(np.frombuffer(mask,np.uint8),cv2.IMREAD_GRAYSCALE)
    assert rgba.shape[2] == 4
    assert np.array_equal(rgba[:,:,3],alpha)
    assert alpha.max()==255 and alpha.min()==0
    assert not alpha[:,-20:].any()


@pytest.mark.parametrize("resolved", [True, False])
def test_auto_merge_requires_resolved_identity_and_binds_every_observation(monkeypatch,tmp_path,resolved):
    from types import SimpleNamespace
    from engine.app import character_identity_v101
    project,timeline = setup(monkeypatch,tmp_path)
    third = deepcopy(timeline["scenes"][1])
    third["ordinal"] = 3
    third["shots"][0].update(ordinal=3,start_us=2_000_000,end_us=3_000_000)
    timeline["scenes"].append(third)
    with studio.get_session() as session:
        session.add(studio.Shot(id="SHOT_3",episode_id="EPISODE_1",ordinal=3,start_us=2_000_000,end_us=3_000_000,
                    duration_us=1_000_000,reference_clip_path="3.mp4",thumbnail_path="3.jpg",keyframes_json="[]",status="READY"))
        session.commit()
    inv = people.inventory(project)
    for i,row in enumerate(inv["observations"],1):
        store_image(project,row,f"image{i}",i/4)
    def restore(raw):
        i=round(json.loads(raw)["display_quality"]*4)
        return SimpleNamespace(shot_id=f"SHOT_{i}",episode_id="EPISODE_1",episode_order=1,shot_ordinal=i,instance_id=f"instance{i}")
    monkeypatch.setattr(capture,"_restore",restore)
    def classify(tracks):
        return [SimpleNamespace(id="identity",tracks=tracks,identity_status="RESOLVED" if resolved else "UNRESOLVED",
                                v10_metadata={"confirmed_gallery_shots":3,"confirmed_gallery_images":3})]
    monkeypatch.setattr(character_identity_v101,"resolve_global_identities",classify)
    result = capture.auto_merge(project)
    assert result["auto_merged_observations"] == (3 if resolved else 0)
    final = people.inventory(project)
    assert len(final["characters"]) == (1 if resolved else 0)
    if resolved:
        assert final["characters"][0]["shot_ids"] == ["SHOT_1","SHOT_2","SHOT_3"]
        assert final["characters"][0]["status"] == "AUTO"
        assert capture.auto_merge(project)["auto_merged_observations"] == 0


def test_breakdown_receipt_survives_completion_and_checks_scope_and_revision(monkeypatch,tmp_path):
    from fastapi import BackgroundTasks, HTTPException
    from engine.app import breakdown_routes_v1 as routes
    from engine.app.task_progress_v2 import finish_task
    project,_ = setup(monkeypatch,tmp_path)
    current = {"workflow_revision":"flow1","input_fingerprint":"input1"}
    monkeypatch.setattr(routes,"_command_context",lambda *args: current)
    command=routes.PerformanceCommand(**current)
    def enqueue(background, key, ordinal=1, payload=command):
        return routes._enqueue(background,project_id=project,episode_id="EPISODE_1",task_type=routes.BREAKDOWN_SHOT_TASK_TYPE,
            title=f"Shot {ordinal}",runner=lambda *args:None,runner_args=("EPISODE_1",ordinal),total_items=1,
            command=payload,idempotency_key=key)
    first=BackgroundTasks()
    task=enqueue(first,"request")
    assert len(first.tasks)==1
    duplicate=BackgroundTasks()
    assert enqueue(duplicate,"request")["id"]==task["id"]
    assert not duplicate.tasks
    # 第二次点击产生新 key 时同样保存收据，完成后不能成为一次新的重跑。
    assert enqueue(duplicate,"second-click")["id"]==task["id"]
    finish_task(task["id"],result={"done":True},message="done")
    current.update(workflow_revision="flow2",input_fingerprint="input2")
    assert enqueue(duplicate,"request")["status"]=="READY"
    assert enqueue(duplicate,"second-click")["status"]=="READY"
    assert not duplicate.tasks
    with pytest.raises(HTTPException) as conflict:
        enqueue(duplicate,"request",ordinal=2)
    assert conflict.value.status_code==409
    with pytest.raises(HTTPException) as stale:
        enqueue(duplicate,"new-request")
    assert stale.value.status_code==409
    with pytest.raises(HTTPException) as missing:
        enqueue(duplicate,"no-command",payload=None)
    assert missing.value.status_code==428
