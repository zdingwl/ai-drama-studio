from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import breakdown_p2_asr_v1 as asr, breakdown_service_v1, studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun


def make_context(tmp_path: Path, *, with_audio: bool = True) -> asr.p2.P2RunContext:
    audio = tmp_path / "中文 源音频.wav"
    if with_audio:
        audio.write_bytes(b"audio")
    return asr.p2.P2RunContext(
        run_id="BREAKDOWN_RUN_ASR",
        project_id="PROJECT_ASR",
        episode_id="EPISODE_ASR",
        source_language="zh-CN",
        source_shot_revision_id="SHOT_REVISION_ASR",
        audio_path=str(audio) if with_audio else None,
        shots=(
            asr.p2.P2ShotInput(
                revision_item_id="REVISION_ITEM_1",
                original_shot_id="SHOT_1",
                ordinal=1,
                start_us=0,
                end_us=1_000_000,
                duration_us=1_000_000,
                reference_clip_path=str(tmp_path / "shot 1.mp4"),
                thumbnail_path=None,
                keyframes=(),
            ),
            asr.p2.P2ShotInput(
                revision_item_id="REVISION_ITEM_2",
                original_shot_id="SHOT_2",
                ordinal=2,
                start_us=1_000_000,
                end_us=2_000_000,
                duration_us=1_000_000,
                reference_clip_path=str(tmp_path / "shot 2.mp4"),
                thumbnail_path=None,
                keyframes=(),
            ),
        ),
    )


def fake_segment(*, start: float = 0.8, end: float = 1.2, text: str = "跨镜对白"):
    return SimpleNamespace(
        start=start,
        end=end,
        text=text,
        avg_logprob=-0.12,
        no_speech_prob=0.03,
        compression_ratio=1.1,
        temperature=0.0,
        seek=0,
        words=[
            SimpleNamespace(start=0.82, end=0.94, word="跨", probability=0.97),
            SimpleNamespace(start=1.04, end=1.18, word="镜", probability=0.91),
        ],
    )


class FakeWhisperModel:
    def __init__(self, segments, *, calls: list[dict] | None = None, info=None):
        self._segments = segments
        self._calls = calls if calls is not None else []
        self._info = info or SimpleNamespace(language="zh", language_probability=0.99, duration=2.0)

    def transcribe(self, path: str, **kwargs):
        self._calls.append({"path": path, **kwargs})
        return iter(self._segments), self._info


def test_faster_whisper_provider_emits_segment_and_word_timing_without_shot_binding(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    calls: list[dict] = []
    factory_calls: list[dict] = []

    def factory(model_name: str, **kwargs):
        factory_calls.append({"model_name": model_name, **kwargs})
        return FakeWhisperModel([fake_segment()], calls=calls)

    provider = asr.FasterWhisperASRProvider(
        model_name="large-v3",
        device="cpu",
        compute_type="int8",
        model_factory=factory,
    )
    result = provider.analyze(context)

    assert result.status == "READY"
    assert result.provider == "faster-whisper"
    assert result.model == "large-v3"
    assert result.metadata["device"] == "cpu"
    assert result.metadata["compute_type"] == "int8"
    assert result.metadata["word_timestamps"] is True
    assert result.metadata["segment_count"] == 1
    assert result.metadata["word_count"] == 2
    assert result.metadata["language_detected"] == "zh"
    assert result.metadata["language_probability"] == pytest.approx(0.99)
    assert factory_calls == [{"model_name": "large-v3", "device": "cpu", "compute_type": "int8"}]
    assert calls[0]["language"] == "zh"
    assert calls[0]["beam_size"] == 5
    assert calls[0]["vad_filter"] is True
    assert calls[0]["word_timestamps"] is True

    assert [item.source_type for item in result.evidence] == ["ASR_SEGMENT", "ASR_WORD", "ASR_WORD"]
    segment, first_word, second_word = result.evidence
    assert segment.source_start_us == 800_000
    assert segment.source_end_us == 1_200_000
    assert segment.text == "跨镜对白"
    assert segment.shot_revision_item_id is None
    assert first_word.source_start_us == 820_000
    assert first_word.source_end_us == 940_000
    assert first_word.confidence == pytest.approx(0.97)
    assert first_word.payload["segment_id"] == segment.source_id
    assert second_word.source_start_us == 1_040_000
    assert second_word.source_end_us == 1_180_000
    # 跨 Shot 的对白在 P2.2 必须保持 Episode 绝对时间，不提前猜 Shot。
    assert first_word.shot_revision_item_id is None
    assert second_word.shot_revision_item_id is None


def test_missing_audio_returns_not_available_without_loading_model(tmp_path: Path) -> None:
    context = make_context(tmp_path, with_audio=False)
    loaded = False

    def factory(*_args, **_kwargs):
        nonlocal loaded
        loaded = True
        raise AssertionError("missing audio must fail before loading model")

    result = asr.FasterWhisperASRProvider(model_factory=factory).analyze(context)

    assert result.status == "NOT_AVAILABLE"
    assert result.evidence == ()
    assert loaded is False
    assert "audio" in result.warnings[0].lower()


def test_no_speech_returns_no_evidence_with_detected_language_metadata(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    provider = asr.FasterWhisperASRProvider(
        device="cpu",
        model_factory=lambda *_args, **_kwargs: FakeWhisperModel([]),
    )

    result = provider.analyze(context)

    assert result.status == "NO_EVIDENCE"
    assert result.evidence == ()
    assert result.metadata["segment_count"] == 0
    assert result.metadata["word_count"] == 0
    assert result.metadata["language_detected"] == "zh"


def test_auto_device_can_fall_back_from_cuda_to_cpu_without_hiding_it(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    attempts: list[tuple[str, str]] = []

    def factory(_model_name: str, **kwargs):
        attempts.append((kwargs["device"], kwargs["compute_type"]))
        if kwargs["device"] == "cuda":
            raise RuntimeError("fixture cuda load failure")
        return FakeWhisperModel([fake_segment(start=0.1, end=0.5, text="你好")])

    provider = asr.FasterWhisperASRProvider(
        device="auto",
        model_factory=factory,
        cuda_device_count=lambda: 1,
    )
    result = provider.analyze(context)

    assert result.status == "READY"
    assert attempts == [("cuda", "float16"), ("cpu", "int8")]
    assert result.metadata["device"] == "cpu"
    assert result.metadata["compute_type"] == "int8"
    assert any("fell back to CPU" in warning for warning in result.warnings)


def test_explicit_cuda_load_failure_is_failed_not_silent_cpu_fallback(tmp_path: Path) -> None:
    context = make_context(tmp_path)
    attempts: list[str] = []

    def factory(_model_name: str, **kwargs):
        attempts.append(kwargs["device"])
        raise RuntimeError("fixture explicit cuda failure")

    result = asr.FasterWhisperASRProvider(
        device="cuda",
        model_factory=factory,
    ).analyze(context)

    assert attempts == ["cuda"]
    assert result.status == "FAILED"
    assert result.evidence == ()
    assert result.metadata["error_type"] == "RuntimeError"
    assert "fixture explicit cuda failure" not in json.dumps(result.metadata)


def setup_real_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    home = tmp_path / "P2 ASR 工作 空间"
    monkeypatch.setenv("AI_DRAMA_STUDIO_HOME", str(home))
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'p2 asr.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)

    source = tmp_path / "原视频.mp4"
    audio = tmp_path / "源音频.wav"
    source.write_bytes(b"video")
    audio.write_bytes(b"audio")
    with factory() as session:
        session.add(studio_v2.Project(
            id="PROJECT_P2_ASR",
            name="P2 ASR",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        ))
        session.add(studio_v2.Episode(
            id="EPISODE_P2_ASR",
            project_id="PROJECT_P2_ASR",
            title="EP01",
            original_filename="ep01.mp4",
            source_path=str(source),
            source_sha256="a" * 64,
            sort_order=1,
            status="SHOTS_READY",
            duration_us=2_000_000,
        ))
        session.flush()
        session.add(studio_v2.Preprocess(
            id="PREPROCESS_P2_ASR",
            episode_id="EPISODE_P2_ASR",
            status="READY",
            proxy_path=str(tmp_path / "proxy.mp4"),
            audio_path=str(audio),
        ))
        for ordinal, start_us, end_us in [(1, 0, 1_000_000), (2, 1_000_000, 2_000_000)]:
            clip = tmp_path / f"参考 镜头 {ordinal}.mp4"
            clip.write_bytes(b"clip")
            session.add(studio_v2.Shot(
                id=f"SHOT_P2_ASR_{ordinal}",
                episode_id="EPISODE_P2_ASR",
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
        "EPISODE_P2_ASR",
        pipeline_profile="breakdown-p2-asr-v1",
        component_status={"ASR": "PENDING", "OCR": "PENDING", "VLM": "PENDING"},
    )
    return factory, run


def test_asr_entry_persists_cross_shot_word_evidence_without_final_assets(monkeypatch, tmp_path: Path) -> None:
    factory, run = setup_real_run(monkeypatch, tmp_path)
    provider = asr.FasterWhisperASRProvider(
        model_name="fixture-large-v3",
        device="cpu",
        compute_type="int8",
        model_factory=lambda *_args, **_kwargs: FakeWhisperModel([fake_segment()]),
    )

    artifact = asr.run_faster_whisper_asr(run.id, provider=provider)

    payload = json.loads(Path(artifact.path).read_text(encoding="utf-8"))
    assert payload["component"] == "ASR"
    assert payload["provider"] == "faster-whisper"
    assert payload["status"] == "READY"
    assert [item["source_type"] for item in payload["evidence"]] == ["ASR_SEGMENT", "ASR_WORD", "ASR_WORD"]
    assert all(item["shot_revision_item_id"] is None for item in payload["evidence"])
    assert payload["evidence"][0]["source_start_us"] == 800_000
    assert payload["evidence"][0]["source_end_us"] == 1_200_000

    with factory() as session:
        row = session.get(BreakdownRun, run.id)
        assert row is not None and row.status == "PROCESSING"
        status = json.loads(row.component_status_json)["ASR"]
        assert status["status"] == "READY"
        assert status["evidence_count"] == 3
        # P2.2 仍然不能物化任何 Final Asset。
        assert session.scalars(select(studio_v2.Character)).all() == []
        assert session.scalars(select(studio_v2.Scene)).all() == []
        assert session.scalars(select(studio_v2.Prop)).all() == []
