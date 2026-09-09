from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.core.config import Settings, get_settings
from app.evidence.providers import FasterWhisperAsrProvider, RapidOcrProvider


def test_faster_whisper_provider_uses_v2_quality_and_segmentation_profile(monkeypatch) -> None:
    settings = Settings(_env_file=None, p6_asr_model="large-v3-turbo")
    provider = FasterWhisperAsrProvider(settings)
    calls: list[dict] = []

    class FakeModel:
        def transcribe(self, source_path: str, **kwargs):
            calls.append({"source_path": source_path, **kwargs})
            return (
                [
                    SimpleNamespace(
                        id=1,
                        seek=0,
                        start=0.10,
                        end=0.55,
                        text="测试。",
                        avg_logprob=-0.1,
                        no_speech_prob=0.0,
                    )
                ],
                SimpleNamespace(language="zh"),
            )

    monkeypatch.setattr(provider, "_get_model", lambda: FakeModel())
    result = provider.transcribe(
        Path("episode.mp4"),
        language_hint="zh-CN",
        duration_us=1_000_000,
    )

    assert provider.profile["model"] == "large-v3-turbo"
    assert provider.profile["continuous_episode_input"] is True
    assert provider.profile["vad_min_silence_duration_ms"] == 500
    assert calls == [
        {
            "source_path": "episode.mp4",
            "language": "zh",
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 500},
            "word_timestamps": True,
            "beam_size": 5,
            "condition_on_previous_text": True,
        }
    ]
    assert len(result) == 1
    assert result[0].text == "测试。"
    assert result[0].start_us == 100_000
    assert result[0].end_us == 550_000
    assert result[0].provenance["vad_min_silence_duration_ms"] == 500


def test_rapidocr_provider_accepts_numpy_box_arrays(monkeypatch) -> None:
    provider = RapidOcrProvider(get_settings())
    rapid_output = SimpleNamespace(
        txts=("画面字幕",),
        scores=(0.99,),
        boxes=np.array(
            [[[10.0, 10.0], [100.0, 10.0], [100.0, 40.0], [10.0, 40.0]]],
            dtype=np.float32,
        ),
    )

    monkeypatch.setattr(provider, "_get_engine", lambda: lambda image: rapid_output)

    detections = provider.recognize(np.zeros((64, 128, 3), dtype=np.uint8))

    assert len(detections) == 1
    assert detections[0].text == "画面字幕"
    assert detections[0].confidence == 0.99
    assert detections[0].bbox == [
        [10.0, 10.0],
        [100.0, 10.0],
        [100.0, 40.0],
        [10.0, 40.0],
    ]
