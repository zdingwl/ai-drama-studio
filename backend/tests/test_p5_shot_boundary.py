import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import app.preprocessing.detector as detector_module
from app.core.config import get_settings
from app.core.errors import AppError
from app.preprocessing.detector import ShotRange


def _create_project(client: TestClient) -> dict:
    response = client.post(
        "/api/v3/projects",
        json={
            "name": "P5-real-video",
            "project_type": "REPLICA",
            "source_language": "zh-CN",
            "target_language": "en-US",
            "target_region": "US",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _make_cut_video(path: Path) -> bytes:
    subprocess.run(
        [
            get_settings().ffmpeg_binary,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x180:d=1:r=24",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:d=1:r=24",
            "-f",
            "lavfi",
            "-i",
            "color=c=white:s=320x180:d=0.25:r=24",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=320x180:d=1:r=24",
            "-filter_complex",
            "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[outv]",
            "-map",
            "[outv]",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path.read_bytes()


def _upload_episode(client: TestClient, project_id: str, payload: bytes, filename: str = "episode.mp4") -> dict:
    response = client.post(
        f"/api/v3/projects/{project_id}/sources/videos",
        files=[("files", (filename, payload, "video/mp4"))],
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


def _task_by_id(client: TestClient, project_id: str, task_id: str) -> dict:
    response = client.get(f"/api/v3/projects/{project_id}/tasks/{task_id}")
    assert response.status_code == 200, response.text
    return response.json()


def test_p5_real_video_builds_ordered_shots_thumbnails_clips_and_formal_artifact(
    client: TestClient,
    tmp_path: Path,
) -> None:
    project = _create_project(client)
    episode = _upload_episode(client, project["id"], _make_cut_video(tmp_path / "cuts.mp4"))

    before = client.get(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/shot-boundary"
    )
    assert before.status_code == 200
    assert before.json()["status"] == "NOT_BUILT"
    assert client.get(f"/api/v3/projects/{project['id']}/tasks").json() == []

    start = client.post(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/commands/shot-boundary",
        headers={"Idempotency-Key": "p5-real-video-1"},
    )
    assert start.status_code == 202, start.text
    task = _task_by_id(client, project["id"], start.json()["id"])
    assert task["status"] == "succeeded", task
    assert task["progress_percent"] == 100

    result = client.get(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/shot-boundary"
    ).json()
    assert result["status"] == "CURRENT"
    assert result["revision"] == 1
    assert result["shot_count"] >= 3
    assert result["shots"][0]["start_us"] == 0
    assert result["shots"][-1]["end_us"] == episode["duration_us"]

    previous_end = 0
    cut_points: list[int] = []
    for shot in result["shots"]:
        assert shot["start_us"] == previous_end
        assert shot["end_us"] > shot["start_us"]
        assert shot["duration_us"] == shot["end_us"] - shot["start_us"]
        previous_end = shot["end_us"]
        cut_points.append(shot["end_us"])
        thumbnail = client.get(shot["thumbnail_url"])
        clip = client.get(shot["reference_clip_url"])
        assert thumbnail.status_code == 200
        assert thumbnail.headers["content-type"].startswith("image/jpeg")
        assert len(thumbnail.content) > 0
        assert clip.status_code == 200
        assert clip.headers["content-type"].startswith("video/mp4")
        assert len(clip.content) > 0

    assert any(abs(cut - 1_000_000) <= 150_000 for cut in cut_points)
    assert any(abs(cut - 2_000_000) <= 150_000 for cut in cut_points)

    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    source = next(node for node in graph["nodes"] if node["artifact_type"] == "SOURCE_VIDEO" and node["is_current"])
    shot_artifact = next(node for node in graph["nodes"] if node["artifact_type"] == "SHOT_ANCHORS" and node["is_current"])
    assert shot_artifact["validity"] == "CURRENT"
    assert shot_artifact["revision"] == 1
    assert any(
        edge["source_node_id"] == source["id"]
        and edge["target_node_id"] == shot_artifact["id"]
        and edge["relation_type"] == "DERIVED_FROM"
        for edge in graph["edges"]
    )


def test_p5_detector_real_video_uses_pyav_without_opencv_fallback(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "pyav-primary.mp4"
    _make_cut_video(video_path)

    def unexpected_opencv(*args, **kwargs):
        raise AssertionError("OpenCV fallback should not be needed for this real video")

    monkeypatch.setattr(detector_module, "VideoStreamCv2", unexpected_opencv)
    progress: list[float] = []
    ranges = detector_module.detect_shot_ranges(
        video_path,
        duration_us=3_250_000,
        on_progress=progress.append,
    )

    assert len(ranges) >= 3
    assert ranges[0].start_us == 0
    assert ranges[-1].end_us == 3_250_000
    assert progress
    assert progress[-1] == 1.0


def test_p5_detector_falls_back_to_opencv_when_pyav_fails(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "opencv-fallback.mp4"
    _make_cut_video(video_path)

    def unavailable_pyav(*args, **kwargs):
        raise RuntimeError("simulated PyAV open failure")

    monkeypatch.setattr(detector_module, "VideoStreamAv", unavailable_pyav)
    ranges = detector_module.detect_shot_ranges(video_path, duration_us=3_250_000)

    assert len(ranges) >= 3
    assert ranges[0].start_us == 0
    assert ranges[-1].end_us == 3_250_000


def test_p5_detector_progress_abort_does_not_start_fallback(tmp_path: Path, monkeypatch) -> None:
    video_path = tmp_path / "cancel.mp4"
    _make_cut_video(video_path)

    def unexpected_opencv(*args, **kwargs):
        raise AssertionError("cancellation must not start a decoder fallback")

    def cancelled(_: float) -> None:
        raise RuntimeError("cancelled-by-task")

    monkeypatch.setattr(detector_module, "VideoStreamCv2", unexpected_opencv)
    with pytest.raises(RuntimeError, match="cancelled-by-task"):
        detector_module.detect_shot_ranges(
            video_path,
            duration_us=3_250_000,
            on_progress=cancelled,
        )


def test_p5_source_video_change_stales_old_boundary_artifact_and_episode_result(
    client: TestClient,
    tmp_path: Path,
) -> None:
    project = _create_project(client)
    episode = _upload_episode(client, project["id"], _make_cut_video(tmp_path / "first.mp4"), "first.mp4")
    started = client.post(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/commands/shot-boundary",
        headers={"Idempotency-Key": "p5-stale-1"},
    )
    assert _task_by_id(client, project["id"], started.json()["id"])["status"] == "succeeded"

    second = subprocess.run(
        [
            get_settings().ffmpeg_binary,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=purple:s=160x90:d=0.4:r=12",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            str(tmp_path / "second.mp4"),
        ],
        check=True,
    )
    assert second.returncode == 0
    _upload_episode(client, project["id"], (tmp_path / "second.mp4").read_bytes(), "second.mp4")

    result = client.get(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/shot-boundary"
    ).json()
    assert result["status"] == "STALE"
    graph = client.get(f"/api/v3/projects/{project['id']}/artifact-graph").json()
    old_shots = [node for node in graph["nodes"] if node["artifact_type"] == "SHOT_ANCHORS"]
    assert len(old_shots) == 1
    assert old_shots[0]["validity"] == "STALE"
    assert old_shots[0]["is_current"] is False


def test_p5_failed_task_can_retry_through_existing_p4_task_command(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = _create_project(client)
    episode = _upload_episode(client, project["id"], _make_cut_video(tmp_path / "retry.mp4"))
    calls = {"count": 0}

    def flaky_detector(path: Path, *, duration_us: int, on_progress=None) -> list[ShotRange]:
        calls["count"] += 1
        if calls["count"] == 1:
            raise AppError("P5_TEST_FAILURE", "模拟镜头检测失败", status_code=422)
        if on_progress is not None:
            on_progress(1.0)
        return [ShotRange(start_us=0, end_us=duration_us)]

    monkeypatch.setattr("app.preprocessing.service.detect_shot_ranges", flaky_detector)
    started = client.post(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/commands/shot-boundary",
        headers={"Idempotency-Key": "p5-retry-1"},
    )
    task_id = started.json()["id"]
    failed = _task_by_id(client, project["id"], task_id)
    assert failed["status"] == "failed"
    assert failed["can_retry"] is True
    assert "P5_TEST_FAILURE" in failed["last_error"]

    retried = client.post(f"/api/v3/projects/{project['id']}/tasks/{task_id}/commands/retry")
    assert retried.status_code == 200, retried.text
    completed = _task_by_id(client, project["id"], task_id)
    assert completed["status"] == "succeeded"
    assert completed["attempt"] == 2
    result = client.get(
        f"/api/v3/projects/{project['id']}/episodes/{episode['id']}/shot-boundary"
    ).json()
    assert result["status"] == "CURRENT"
    assert result["shot_count"] == 1
