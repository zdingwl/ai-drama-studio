import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.evidence.models import ShotDialogueProjection
from app.evidence.providers import AsrSegmentResult, EvidenceProviders, OcrDetectionResult
from app.preprocessing.detector import ShotRange


class FakeAsrProvider:
    profile = {"provider":"fake-continuous-asr","model":"test","continuous_episode_input":True}
    def __init__(self) -> None: self.calls: list[Path] = []
    def transcribe(self, source_path: Path, *, language_hint: str | None, duration_us: int, on_progress=None) -> list[AsrSegmentResult]:
        self.calls.append(source_path)
        assert "shot-boundary" not in source_path.as_posix()
        assert "reference" not in source_path.name.lower()
        if on_progress is not None: on_progress(0.5); on_progress(1.0)
        return [
            AsrSegmentResult(start_us=700_000,end_us=950_000,text="你好，",language="zh",confidence=.95,provenance={"provider":"fake","raw":1}),
            AsrSegmentResult(start_us=950_000,end_us=1_300_000,text="世界。",language="zh",confidence=.96,provenance={"provider":"fake","raw":2}),
        ]


class FakeOcrProvider:
    profile = {"provider":"fake-timeline-ocr","engine":"test"}
    def __init__(self) -> None: self.calls = 0
    def recognize(self, image: object) -> list[OcrDetectionResult]:
        self.calls += 1
        return [OcrDetectionResult(text="画面字幕",confidence=.99,bbox=[[10,10],[100,10],[100,40],[10,40]])]


def _project(client: TestClient) -> dict:
    response = client.post("/api/v3/projects",json={"name":"P6-source-evidence","project_type":"REPLICA","source_language":"zh-CN","target_language":"en-US","target_region":"US"})
    assert response.status_code == 201, response.text
    return response.json()


def _video(path: Path, duration: float = 2.0) -> bytes:
    subprocess.run([get_settings().ffmpeg_binary,"-y","-v","error","-f","lavfi","-i",f"color=c=black:s=320x180:d={duration}:r=12","-f","lavfi","-i",f"sine=frequency=440:duration={duration}:sample_rate=16000","-shortest","-c:v","mpeg4","-pix_fmt","yuv420p","-c:a","aac",str(path)],check=True)
    return path.read_bytes()


def _upload(client: TestClient, project_id: str, payload: bytes, filename: str = "episode.mp4") -> dict:
    response = client.post(f"/api/v3/projects/{project_id}/sources/videos",files=[("files",(filename,payload,"video/mp4"))])
    assert response.status_code == 201, response.text
    return response.json()[0]


def _task(client: TestClient, project_id: str, task_id: str) -> dict:
    response = client.get(f"/api/v3/projects/{project_id}/tasks/{task_id}"); assert response.status_code == 200
    return response.json()


def _fake(monkeypatch) -> tuple[FakeAsrProvider, FakeOcrProvider]:
    asr, ocr = FakeAsrProvider(), FakeOcrProvider(); providers = EvidenceProviders(asr=asr,ocr=ocr)
    monkeypatch.setattr("app.evidence.service.build_evidence_providers",lambda settings: providers)
    return asr, ocr


def _run(client: TestClient, project_id: str, episode_id: str, key: str) -> None:
    response = client.post(f"/api/v3/projects/{project_id}/episodes/{episode_id}/commands/source-evidence",headers={"Idempotency-Key":key})
    assert response.status_code == 202, response.text
    assert _task(client,project_id,response.json()["id"])["status"] == "succeeded"


def test_p6_get_is_read_only_and_asr_uses_full_episode_without_shots(client: TestClient,tmp_path: Path,monkeypatch) -> None:
    project = _project(client); episode = _upload(client,project["id"],_video(tmp_path/"full.mp4")); asr, ocr = _fake(monkeypatch)
    before = client.get(f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/source-evidence")
    assert before.status_code == 200 and before.json()["status"] == "NOT_BUILT"
    assert client.get(f"/api/v3/projects/{project['id']}/tasks").json() == []
    _run(client,project["id"],episode["id"],"p6-full-1")
    assert len(asr.calls) == 1 and asr.calls[0].is_file() and ocr.calls >= 3
    result = client.get(f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/source-evidence").json()
    assert result["status"] == "CURRENT" and result["revision"] == 1
    assert result["dialogue_count"] == 1 and result["dialogue"][0]["text"] == "你好，世界。"
    assert result["dialogue"][0]["projected_shot_numbers"] == []
    assert result["raw_asr_segment_count"] == 2 and result["visual_text_count"] == 1
    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    source = next(n for n in graph["nodes"] if n["artifact_type"]=="SOURCE_VIDEO" and n["is_current"])
    evidence = next(n for n in graph["nodes"] if n["artifact_type"]=="SOURCE_DIALOGUE" and n["is_current"])
    assert evidence["validity"] == "CURRENT" and evidence["revision"] == 1
    assert any(e["source_node_id"]==source["id"] and e["target_node_id"]==evidence["id"] and e["relation_type"]=="DERIVED_FROM" for e in graph["edges"])


def test_p6_cross_shot_dialogue_stays_one_canonical_with_1_to_n_projection(client: TestClient,tmp_path: Path,monkeypatch) -> None:
    project = _project(client); episode = _upload(client,project["id"],_video(tmp_path/"cross.mp4")); asr,_ = _fake(monkeypatch)
    monkeypatch.setattr("app.preprocessing.service.detect_shot_ranges",lambda path,*,duration_us,on_progress=None:[ShotRange(start_us=0,end_us=1_000_000),ShotRange(start_us=1_000_000,end_us=duration_us)])
    p5 = client.post(f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/commands/shot-boundary",headers={"Idempotency-Key":"p6-p5"})
    assert _task(client,project["id"],p5.json()["id"])["status"] == "succeeded"
    _run(client,project["id"],episode["id"],"p6-projection")
    result = client.get(f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/source-evidence").json()
    assert len(asr.calls) == 1 and result["dialogue_count"] == 1
    assert result["dialogue"][0]["text"] == "你好，世界。" and result["dialogue"][0]["projected_shot_numbers"] == [1,2]
    assert "text" not in ShotDialogueProjection.__table__.columns


def test_p6_source_video_change_stales_evidence(client: TestClient,tmp_path: Path,monkeypatch) -> None:
    project = _project(client); episode = _upload(client,project["id"],_video(tmp_path/"first.mp4")); _fake(monkeypatch)
    _run(client,project["id"],episode["id"],"p6-stale")
    _upload(client,project["id"],_video(tmp_path/"second.mp4",1.0),"second.mp4")
    result = client.get(f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/source-evidence").json(); assert result["status"] == "STALE"
    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json(); nodes = [n for n in graph["nodes"] if n["artifact_type"]=="SOURCE_DIALOGUE"]
    assert len(nodes)==1 and nodes[0]["validity"]=="STALE" and nodes[0]["is_current"] is False
