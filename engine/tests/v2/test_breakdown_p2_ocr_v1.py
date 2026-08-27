from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import breakdown_p2_ocr_v1 as ocr, breakdown_service_v1, studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun


def make_context(tmp_path: Path, *, with_clips: bool = True) -> ocr.p2.P2RunContext:
    shots = []
    for ordinal, start_us, end_us in [
        (1, 0, 1_000_000),
        (2, 1_000_000, 2_000_000),
    ]:
        clip = tmp_path / f"历史 镜头 {ordinal}.mp4"
        if with_clips:
            clip.write_bytes(b"clip")
        shots.append(ocr.p2.P2ShotInput(
            revision_item_id=f"REVISION_ITEM_{ordinal}",
            original_shot_id=f"SHOT_{ordinal}",
            ordinal=ordinal,
            start_us=start_us,
            end_us=end_us,
            duration_us=end_us - start_us,
            reference_clip_path=str(clip),
            thumbnail_path=None,
            keyframes=(),
        ))
    return ocr.p2.P2RunContext(
        run_id="BREAKDOWN_RUN_OCR",
        project_id="PROJECT_OCR",
        episode_id="EPISODE_OCR",
        source_language="zh-CN",
        source_shot_revision_id="SHOT_REVISION_OCR",
        audio_path=None,
        shots=tuple(shots),
    )


class FakeOCREngine:
    def __init__(self, outputs=None, *, fail: bool = False):
        self.outputs = outputs or {}
        self.fail = fail
        self.calls: list[object] = []

    def __call__(self, image):
        self.calls.append(image)
        if self.fail:
            raise RuntimeError("fixture ocr frame failure")
        return self.outputs.get(
            image,
            SimpleNamespace(boxes=None, txts=None, scores=None),
        )


def sample_for(shot: ocr.p2.P2ShotInput, relative_us: int, token: str) -> ocr.OCRFrameSample:
    return ocr.OCRFrameSample(
        sample_index=0,
        requested_relative_us=relative_us,
        image=token,
        width=200,
        height=100,
    )


def test_rapidocr_provider_emits_shot_bound_polygon_evidence_in_source_microseconds(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    factory_calls: list[dict] = []
    engine = FakeOCREngine({
        "frame-1": SimpleNamespace(
            boxes=[[[10, 20], [110, 20], [110, 50], [10, 50]]],
            txts=["医院"],
            scores=[0.93],
        ),
        "frame-2": SimpleNamespace(
            boxes=[[[20, 30], [180, 30], [180, 60], [20, 60]]],
            txts=["急诊入口"],
            scores=[0.88],
        ),
    })

    def engine_factory(params):
        factory_calls.append(dict(params))
        return engine

    def frame_sampler(shot, relative_times):
        assert relative_times
        if shot.ordinal == 1:
            return (sample_for(shot, 100_000, "frame-1"),)
        return (sample_for(shot, 200_000, "frame-2"),)

    provider = ocr.RapidOCROCRProvider(
        device="cpu",
        engine_factory=engine_factory,
        frame_sampler=frame_sampler,
    )
    result = provider.analyze(context)

    assert result.status == "READY"
    assert result.provider == "rapidocr"
    assert result.model == "PP-OCRv6-small"
    assert result.metadata["recognition_language"] == "ch"
    assert result.metadata["device"] == "cpu"
    assert result.metadata["observation_count"] == 2
    assert factory_calls[0]["Det.ocr_version"] == "PP-OCRv6"
    assert factory_calls[0]["Rec.ocr_version"] == "PP-OCRv6"
    assert factory_calls[0]["Rec.lang_type"] == "ch"
    assert factory_calls[0]["EngineConfig.onnxruntime.use_cuda"] is False

    first, second = result.evidence
    assert first.source_type == "OCR_OBSERVATION"
    assert first.source_start_us == 100_000
    assert first.source_end_us == 100_001
    assert first.shot_revision_item_id == "REVISION_ITEM_1"
    assert first.text == "医院"
    assert first.confidence == pytest.approx(0.93)
    assert first.payload["polygon_px"] == [[10.0, 20.0], [110.0, 20.0], [110.0, 50.0], [10.0, 50.0]]
    assert first.payload["bbox_px"] == [10.0, 20.0, 110.0, 50.0]
    assert first.payload["polygon_norm"][0] == pytest.approx([10 / 199, 20 / 99])

    # 第二个 Shot 的相对 200ms 必须恢复成 Episode source 1.2s，并绑定历史 RevisionItem。
    assert second.source_start_us == 1_200_000
    assert second.source_end_us == 1_200_001
    assert second.shot_revision_item_id == "REVISION_ITEM_2"
    assert second.text == "急诊入口"


def test_sampling_schedule_covers_whole_shot_and_respects_max_frame_cap() -> None:
    provider = ocr.RapidOCROCRProvider(
        sample_interval_us=500_000,
        max_frames_per_shot=6,
        engine_factory=lambda _params: None,
        frame_sampler=lambda _shot, _times: (),
    )

    points = provider._sample_relative_times(10_000_000)

    assert len(points) == 6
    assert points == tuple(sorted(points))
    assert points[0] <= 100_000
    assert points[-1] >= 9_800_000
    assert all(0 <= value < 10_000_000 for value in points)


def test_missing_reference_clips_returns_not_available_without_loading_engine(tmp_path: Path) -> None:
    context = make_context(tmp_path, with_clips=False)
    loaded = False

    def factory(_params):
        nonlocal loaded
        loaded = True
        raise AssertionError("missing clips must fail before OCR engine load")

    result = ocr.RapidOCROCRProvider(engine_factory=factory).analyze(context)

    assert result.status == "NOT_AVAILABLE"
    assert result.evidence == ()
    assert loaded is False
    assert result.metadata["missing_reference_clip_count"] == 2


def test_successful_frames_without_text_return_no_evidence(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    engine = FakeOCREngine()

    def frame_sampler(shot, _times):
        return (sample_for(shot, 250_000, f"blank-{shot.ordinal}"),)

    result = ocr.RapidOCROCRProvider(
        device="cpu",
        engine_factory=lambda _params: engine,
        frame_sampler=frame_sampler,
    ).analyze(context)

    assert result.status == "NO_EVIDENCE"
    assert result.evidence == ()
    assert result.metadata["frames_analyzed"] == 2
    assert result.metadata["observation_count"] == 0


def test_auto_cuda_engine_load_failure_visibly_falls_back_to_cpu(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    attempts: list[bool] = []
    cpu_engine = FakeOCREngine({
        "frame": SimpleNamespace(
            boxes=[[[0, 0], [50, 0], [50, 20], [0, 20]]],
            txts=["字幕"],
            scores=[0.9],
        )
    })

    def factory(params):
        use_cuda = bool(params["EngineConfig.onnxruntime.use_cuda"])
        attempts.append(use_cuda)
        if use_cuda:
            raise RuntimeError("fixture cuda init failure")
        return cpu_engine

    def frame_sampler(shot, _times):
        return (sample_for(shot, 100_000, "frame"),)

    result = ocr.RapidOCROCRProvider(
        device="auto",
        engine_factory=factory,
        frame_sampler=frame_sampler,
        cuda_available=lambda: True,
    ).analyze(context)

    assert result.status == "READY"
    assert attempts == [True, False]
    assert result.metadata["device"] == "cpu"
    assert any("fell back to CPU" in warning for warning in result.warnings)


def test_explicit_cuda_unavailable_is_failed_without_silent_cpu_fallback(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    factory_called = False

    def factory(_params):
        nonlocal factory_called
        factory_called = True
        raise AssertionError("explicit unavailable CUDA must not try CPU")

    result = ocr.RapidOCROCRProvider(
        device="cuda",
        engine_factory=factory,
        frame_sampler=lambda _shot, _times: (),
        cuda_available=lambda: False,
    ).analyze(context)

    assert result.status == "FAILED"
    assert result.evidence == ()
    assert factory_called is False
    assert result.metadata["error_type"] == "RuntimeError"
    assert "CUDAExecutionProvider is not available" not in json.dumps(result.metadata)


def setup_real_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    home = tmp_path / "P2 OCR 工作 空间"
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(home))
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'p2 ocr.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)

    source = tmp_path / "原视频.mp4"
    source.write_bytes(b"video")
    with factory() as session:
        session.add(studio_v2.Project(
            id="PROJECT_P2_OCR",
            name="P2 OCR",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        ))
        session.add(studio_v2.Episode(
            id="EPISODE_P2_OCR",
            project_id="PROJECT_P2_OCR",
            title="EP01",
            original_filename="ep01.mp4",
            source_path=str(source),
            source_sha256="b" * 64,
            sort_order=1,
            status="SHOTS_READY",
            duration_us=2_000_000,
        ))
        session.flush()
        for ordinal, start_us, end_us in [(1, 0, 1_000_000), (2, 1_000_000, 2_000_000)]:
            clip = tmp_path / f"OCR 参考 镜头 {ordinal}.mp4"
            clip.write_bytes(b"clip")
            session.add(studio_v2.Shot(
                id=f"SHOT_P2_OCR_{ordinal}",
                episode_id="EPISODE_P2_OCR",
                ordinal=ordinal,
                start_us=start_us,
                end_us=end_us,
                duration_us=end_us - start_us,
                reference_clip_path=str(clip),
                thumbnail_path=None,
                keyframes_json="[]",
                status="READY",
            ))
        session.commit()

    run = breakdown_service_v1.create_breakdown_run(
        "EPISODE_P2_OCR",
        pipeline_profile="breakdown-p2-ocr-v1",
        component_status={"ASR": "PENDING", "OCR": "PENDING", "VLM": "PENDING"},
    )
    return factory, run


def test_ocr_entry_persists_historical_shot_bound_evidence_without_final_assets(monkeypatch, tmp_path: Path) -> None:
    factory, run = setup_real_run(monkeypatch, tmp_path)
    engine = FakeOCREngine({
        "shot-1": SimpleNamespace(
            boxes=[[[5, 5], [100, 5], [100, 30], [5, 30]]],
            txts=["第一行字幕"],
            scores=[0.96],
        ),
        "shot-2": SimpleNamespace(
            boxes=[[[10, 10], [150, 10], [150, 35], [10, 35]]],
            txts=["第二行字幕"],
            scores=[0.94],
        ),
    })

    def frame_sampler(shot, _times):
        return (sample_for(shot, 125_000, f"shot-{shot.ordinal}"),)

    provider = ocr.RapidOCROCRProvider(
        device="cpu",
        engine_factory=lambda _params: engine,
        frame_sampler=frame_sampler,
    )
    artifact = ocr.run_rapidocr_ocr(run.id, provider=provider)

    payload = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
    assert payload["component"] == "OCR"
    assert payload["provider"] == "rapidocr"
    assert payload["model"] == "PP-OCRv6-small"
    assert payload["status"] == "READY"
    assert [item["source_type"] for item in payload["evidence"]] == ["OCR_OBSERVATION", "OCR_OBSERVATION"]
    assert payload["evidence"][0]["source_start_us"] == 125_000
    assert payload["evidence"][1]["source_start_us"] == 1_125_000
    assert payload["evidence"][0]["shot_revision_item_id"] != payload["evidence"][1]["shot_revision_item_id"]
    assert payload["evidence"][0]["payload"]["polygon_px"]

    with factory() as session:
        row = session.get(BreakdownRun, run.id)
        assert row is not None and row.status == "PROCESSING"
        status = json.loads(row.component_status_json)["OCR"]
        assert status["status"] == "READY"
        assert status["evidence_count"] == 2
        # P2.3 仍然只能写 raw anonymous Evidence，不能物化 Final Asset。
        assert session.scalars(select(studio_v2.Character)).all() == []
        assert session.scalars(select(studio_v2.Scene)).all() == []
        assert session.scalars(select(studio_v2.Prop)).all() == []
