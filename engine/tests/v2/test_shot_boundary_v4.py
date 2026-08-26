from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from engine.app import media_v4, reference_render_v4


def candidate(cut_us: int, peak: float = 0.94) -> media_v4.TransNetCandidate:
    return media_v4.TransNetCandidate(
        proxy_cut_us=cut_us,
        transition_start_us=cut_us - 80_000,
        transition_end_us=cut_us - 40_000,
        peak_score=peak,
    )


def test_source_refiner_can_pull_transnet_candidate_back_to_true_frame_boundary() -> None:
    # 25fps Source。TransNet 候选落在 240ms，但真正最大的相邻帧断裂发生在 160ms。
    pts = tuple(index * 40_000 for index in range(12))
    visual = [0.0, 0.04, 0.05, 0.06, 0.92, 0.08, 0.07, 0.06, 0.04, 0.03, 0.03, 0.02]

    refined = media_v4._refine_candidates(
        [candidate(240_000)],
        pts,
        visual,
        pyscene_cuts=[160_000],
        pyscene_status="READY",
    )

    assert len(refined) == 1
    assert refined[0].cut_us == 160_000
    assert refined[0].pyscenedetect_confirmed is True
    assert refined[0].visual_score == 0.92


def test_pyscenedetect_is_secondary_evidence_not_standalone_union() -> None:
    pts = tuple(index * 40_000 for index in range(20))
    visual = [0.0] + [0.08] * 19
    visual[5] = 0.85
    visual[15] = 0.95

    refined = media_v4._refine_candidates(
        [candidate(200_000)],
        pts,
        visual,
        # 600ms 是一个 PySceneDetect-only Cut，但没有 TransNet candidate，不能直接加入 Final cuts。
        pyscene_cuts=[200_000, 600_000],
        pyscene_status="READY",
    )

    assert [item.cut_us for item in refined] == [200_000]


def test_review_out_frame_is_strictly_before_exclusive_end() -> None:
    pts = (0, 40_000, 80_000, 120_000, 160_000, 200_000)

    in_us, mid_us, out_us = media_v4._review_times(pts, 40_000, 160_000)

    assert in_us == 40_000
    assert 40_000 <= mid_us < 160_000
    assert out_us == 120_000
    assert out_us < 160_000


def test_adjacent_shots_never_share_the_cut_frame() -> None:
    """公共 Cut 帧必须只属于右 Shot；这是 [start,end) 的数据库级帧语义。"""

    pts = (0, 40_000, 80_000, 120_000, 160_000, 200_000, 240_000)
    left_start, left_end = reference_render_v4.frame_span_indices(pts, 0, 160_000)
    right_start, right_end = reference_render_v4.frame_span_indices(pts, 160_000, 240_000)

    assert (left_start, left_end) == (0, 4)
    assert (right_start, right_end) == (4, 6)
    assert left_end == right_start
    assert pts[left_end - 1] == 120_000
    assert pts[right_start] == 160_000


def test_frame_ownership_survives_integer_microsecond_boundary_rounding() -> None:
    """即使业务边界来自取整 PTS，也不再让 FFmpeg 浮点比较决定最后一帧。"""

    pts = (0, 40_000, 80_000, 120_000, 160_000, 200_000)
    start_index, end_index = reference_render_v4.frame_span_indices(pts, 0, 160_000)

    assert list(pts[start_index:end_index]) == [0, 40_000, 80_000, 120_000]
    assert 160_000 not in pts[start_index:end_index]


def test_reference_renderer_trims_by_owned_frame_count_not_float_end(monkeypatch, tmp_path: Path) -> None:
    captured: list[list[str]] = []
    source_pts = (0, 40_000, 80_000, 120_000, 160_000, 200_000, 240_000)

    monkeypatch.setattr(media_v4.v2, "probe_media", lambda _path: {"has_audio": False})
    monkeypatch.setattr(media_v4.v2, "_run", lambda command, **_kwargs: captured.append(command))
    # [80ms, 200ms) 应恰好拥有 80/120/160 三帧；模拟编码后 ffprobe 也返回三帧。
    monkeypatch.setattr(media_v4.v2, "_frame_pts_us", lambda _path: (0, 40_000, 80_000))

    media_v4.render_reference_exact(
        tmp_path / "source.mp4",
        tmp_path / "shot.mp4",
        80_000,
        120_000,
        frame_pts=source_pts,
    )

    assert captured
    command = captured[0]
    # 第一 owned frame=80ms；seek 安全落在上一帧 40ms 与目标帧 80ms 中间。
    assert command[command.index("-ss") + 1] == "0.060000"
    filter_complex = command[command.index("-filter_complex") + 1]
    # trim.end_frame 是排他的 zero-based frame index；0..2 正好是三帧。
    assert "trim=start_frame=0:end_frame=3" in filter_complex
    assert "trim=start=0:end=" not in filter_complex
    assert "setpts=PTS-STARTPTS" in filter_complex
    assert "-t" not in command
    assert "passthrough" in command


def test_reference_renderer_fails_closed_when_encoded_frame_count_is_wrong(monkeypatch, tmp_path: Path) -> None:
    source_pts = (0, 40_000, 80_000, 120_000, 160_000, 200_000, 240_000)

    monkeypatch.setattr(media_v4.v2, "probe_media", lambda _path: {"has_audio": False})
    monkeypatch.setattr(media_v4.v2, "_run", lambda _command, **_kwargs: None)
    # 期望三帧却只返回两帧：新 Run 必须失败，不能切 Current。
    monkeypatch.setattr(media_v4.v2, "_frame_pts_us", lambda _path: (0, 40_000))

    with pytest.raises(media_v4.v2.MediaPipelineError, match="帧数校验失败"):
        media_v4.render_reference_exact(
            tmp_path / "source.mp4",
            tmp_path / "shot.mp4",
            80_000,
            120_000,
            frame_pts=source_pts,
        )


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="real FFmpeg integration check requires ffmpeg + ffprobe",
)
def test_reference_renderer_real_ffmpeg_emits_exact_owned_frame_count(tmp_path: Path) -> None:
    """真实 FFmpeg 必须把三帧 ownership 编码成三帧，而不是 N+1 帧。"""

    source = tmp_path / "source.mp4"
    output = tmp_path / "shot.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x96:rate=25",
            "-frames:v",
            "8",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    source_pts = tuple(index * 40_000 for index in range(8))

    reference_render_v4.render_reference_exact(
        source,
        output,
        80_000,
        120_000,
        frame_pts=source_pts,
    )

    assert len(reference_render_v4.v2._frame_pts_us(output)) == 3


def test_low_confidence_boundary_is_marked_for_review() -> None:
    pts = tuple(index * 40_000 for index in range(12))
    visual = [0.0] + [0.05] * 11

    refined = media_v4._refine_candidates(
        [candidate(200_000, peak=0.52)],
        pts,
        visual,
        pyscene_cuts=[],
        pyscene_status="READY",
    )

    assert len(refined) == 1
    assert refined[0].confidence < media_v4.BOUNDARY_REVIEW_THRESHOLD
    assert "边界置信度偏低" in refined[0].review_reasons
