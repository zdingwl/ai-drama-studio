from __future__ import annotations

from pathlib import Path

from engine.app import media_v4


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


def test_reference_renderer_uses_accurate_seek_plus_exclusive_trim(monkeypatch, tmp_path: Path) -> None:
    captured: list[list[str]] = []

    monkeypatch.setattr(media_v4.v2, "probe_media", lambda _path: {"has_audio": False})
    monkeypatch.setattr(media_v4.v2, "_run", lambda command, **_kwargs: captured.append(command))

    media_v4.render_reference_exact(
        tmp_path / "source.mp4",
        tmp_path / "shot.mp4",
        1_000_000,
        2_000_000,
    )

    assert captured
    command = captured[0]
    assert command[command.index("-ss") + 1] == "1.000000"
    filter_complex = command[command.index("-filter_complex") + 1]
    assert "trim=start=0:end=2.000000" in filter_complex
    assert "setpts=PTS-STARTPTS" in filter_complex
    assert "-t" not in command


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
