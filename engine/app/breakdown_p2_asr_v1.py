"""Breakdown-first Phase P2.2：faster-whisper 匿名 ASR Evidence Provider。

职责：
- 消费 P2.1 ``P2RunContext.audio_path``；
- 使用 faster-whisper 做本地 ASR，并强制开启 segment + word timestamps；
- 只输出 ``ASR_SEGMENT`` / ``ASR_WORD`` 原始 Evidence；
- 时间统一转换为 Episode source integer microseconds；
- 不提前把跨 Shot 对白硬绑定到某个 ShotRevisionItem；P2.5 Fusion 再按时间切分；
- 不写 Dialogue、Character、Scene、Prop 或任何 Final Binding。

默认质量档：``large-v3``。可通过 ``AI_DRAMA_P2_ASR_*`` 环境变量调整模型、设备和计算类型。
旧 ``content_analysis_v2._run_asr`` 保留兼容，但不再是 Breakdown P2 正式入口。
"""
from __future__ import annotations

from pathlib import Path
import os
from typing import Any, Callable

from engine.app import breakdown_p2_sidecar_v1 as p2

ASR_PROVIDER_NAME = "faster-whisper"
DEFAULT_ASR_MODEL = "large-v3"
DEFAULT_BEAM_SIZE = 5


class FasterWhisperASRProvider:
    """同步本地 faster-whisper Provider。

    ``model_factory`` 仅用于测试/可替换加载器；正式运行时懒加载 ``faster_whisper.WhisperModel``。
    Provider 实例会缓存已经加载的模型，顺序处理多个 Run 时无需重复载入权重。
    """

    component = "ASR"

    def __init__(
        self,
        *,
        model_name: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        beam_size: int = DEFAULT_BEAM_SIZE,
        vad_filter: bool = True,
        download_root: str | None = None,
        model_factory: Callable[..., Any] | None = None,
        cuda_device_count: Callable[[], int] | None = None,
    ) -> None:
        self.model_name = (model_name or os.getenv("AI_DRAMA_P2_ASR_MODEL") or DEFAULT_ASR_MODEL).strip()
        self.requested_device = (device or os.getenv("AI_DRAMA_P2_ASR_DEVICE") or "auto").strip().lower()
        self.requested_compute_type = (
            compute_type if compute_type is not None else os.getenv("AI_DRAMA_P2_ASR_COMPUTE_TYPE")
        )
        if self.requested_compute_type is not None:
            self.requested_compute_type = self.requested_compute_type.strip()
        self.beam_size = int(beam_size)
        self.vad_filter = bool(vad_filter)
        self.download_root = (
            download_root if download_root is not None else os.getenv("AI_DRAMA_P2_ASR_MODEL_CACHE")
        )
        self._model_factory = model_factory
        self._cuda_device_count = cuda_device_count
        self._model: Any | None = None
        self._actual_device: str | None = None
        self._actual_compute_type: str | None = None
        self._load_warnings: tuple[str, ...] = ()

        if not self.model_name:
            raise ValueError("P2 ASR model_name 不能为空")
        if self.requested_device not in {"auto", "cpu", "cuda"}:
            raise ValueError("P2 ASR device 只允许 auto/cpu/cuda")
        if self.beam_size < 1:
            raise ValueError("P2 ASR beam_size 必须 >= 1")

    @staticmethod
    def _language_code(source_language: str) -> str | None:
        value = (source_language or "").strip().lower().replace("_", "-")
        if not value or value in {"auto", "und", "unknown"}:
            return None
        aliases = {
            "zh-cn": "zh",
            "zh-sg": "zh",
            "zh-hans": "zh",
            "zh-tw": "zh",
            "zh-hk": "zh",
            "zh-mo": "zh",
            "zh-hant": "zh",
            "yue": "zh",
            "yue-hk": "zh",
            "en-us": "en",
            "en-gb": "en",
            "ja-jp": "ja",
            "ko-kr": "ko",
            "es-es": "es",
            "pt-br": "pt",
        }
        return aliases.get(value, value.split("-", 1)[0])

    @staticmethod
    def _seconds_to_us(value: Any) -> int | None:
        if value is None:
            return None
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return None
        if seconds < 0:
            return None
        return int(round(seconds * 1_000_000))

    @staticmethod
    def _finite_float(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != number or number in {float("inf"), float("-inf")}:
            return None
        return number

    @staticmethod
    def _probability(value: Any) -> float | None:
        number = FasterWhisperASRProvider._finite_float(value)
        if number is None or not 0.0 <= number <= 1.0:
            return None
        return number

    def _get_cuda_device_count(self) -> int:
        if self._cuda_device_count is not None:
            try:
                return max(0, int(self._cuda_device_count()))
            except Exception:
                return 0
        try:
            import ctranslate2

            return max(0, int(ctranslate2.get_cuda_device_count()))
        except Exception:
            return 0

    def _resolve_device(self) -> str:
        if self.requested_device != "auto":
            return self.requested_device
        return "cuda" if self._get_cuda_device_count() > 0 else "cpu"

    def _default_compute_type(self, device: str) -> str:
        if self.requested_compute_type:
            return self.requested_compute_type
        return "float16" if device == "cuda" else "int8"

    def _new_model(self, *, device: str, compute_type: str) -> Any:
        kwargs: dict[str, Any] = {
            "device": device,
            "compute_type": compute_type,
        }
        if self.download_root:
            kwargs["download_root"] = self.download_root
        if self._model_factory is not None:
            return self._model_factory(self.model_name, **kwargs)
        from faster_whisper import WhisperModel

        return WhisperModel(self.model_name, **kwargs)

    def _load_model(self) -> tuple[Any, str, str, tuple[str, ...]]:
        if self._model is not None and self._actual_device and self._actual_compute_type:
            return self._model, self._actual_device, self._actual_compute_type, self._load_warnings

        device = self._resolve_device()
        compute_type = self._default_compute_type(device)
        warnings: list[str] = []
        try:
            model = self._new_model(device=device, compute_type=compute_type)
        except Exception:
            # auto 才允许自动降级。用户显式指定 cuda 时失败必须暴露，不能静默改成 CPU。
            if self.requested_device != "auto" or device != "cuda":
                raise
            fallback_compute = self.requested_compute_type or "int8"
            model = self._new_model(device="cpu", compute_type=fallback_compute)
            device = "cpu"
            compute_type = fallback_compute
            warnings.append("CUDA ASR model load failed; fell back to CPU")

        self._model = model
        self._actual_device = device
        self._actual_compute_type = compute_type
        self._load_warnings = tuple(warnings)
        return model, device, compute_type, self._load_warnings

    def _result_metadata(
        self,
        *,
        actual_device: str | None,
        actual_compute_type: str | None,
        requested_language: str | None,
        info: Any | None = None,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "device_requested": self.requested_device,
            "device": actual_device,
            "compute_type": actual_compute_type,
            "beam_size": self.beam_size,
            "vad_filter": self.vad_filter,
            "word_timestamps": True,
            "language_requested": requested_language,
        }
        if info is not None:
            detected = getattr(info, "language", None)
            probability = self._probability(getattr(info, "language_probability", None))
            if detected:
                metadata["language_detected"] = str(detected)
            if probability is not None:
                metadata["language_probability"] = probability
            duration = self._finite_float(getattr(info, "duration", None))
            if duration is not None and duration >= 0:
                metadata["audio_duration_us"] = int(round(duration * 1_000_000))
        if error_type:
            metadata["error_type"] = error_type
        return metadata

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        requested_language = self._language_code(context.source_language)
        audio_path = Path(context.audio_path) if context.audio_path else None
        if audio_path is None or not audio_path.is_file():
            return p2.P2ProviderResult(
                component="ASR",
                provider=ASR_PROVIDER_NAME,
                model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._result_metadata(
                    actual_device=None,
                    actual_compute_type=None,
                    requested_language=requested_language,
                ),
                warnings=("Episode preprocess audio is not available",),
            )

        try:
            model, actual_device, actual_compute_type, load_warnings = self._load_model()
        except ImportError:
            return p2.P2ProviderResult(
                component="ASR",
                provider=ASR_PROVIDER_NAME,
                model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._result_metadata(
                    actual_device=None,
                    actual_compute_type=None,
                    requested_language=requested_language,
                    error_type="ImportError",
                ),
                warnings=("faster-whisper is not installed",),
            )
        except Exception as exc:
            return p2.P2ProviderResult(
                component="ASR",
                provider=ASR_PROVIDER_NAME,
                model=self.model_name,
                status="FAILED",
                metadata=self._result_metadata(
                    actual_device=None,
                    actual_compute_type=None,
                    requested_language=requested_language,
                    error_type=type(exc).__name__,
                ),
                warnings=("ASR model load failed",),
            )

        try:
            segments, info = model.transcribe(
                str(audio_path),
                language=requested_language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
                word_timestamps=True,
            )
            evidence: list[p2.P2EvidenceRecord] = []
            segment_count = 0
            word_count = 0
            missing_word_segments = 0
            detected_language = str(getattr(info, "language", None) or requested_language or "") or None

            for raw_segment_index, segment in enumerate(segments):
                text = str(getattr(segment, "text", "") or "").strip()
                start_us = self._seconds_to_us(getattr(segment, "start", None))
                end_us = self._seconds_to_us(getattr(segment, "end", None))
                if not text or start_us is None or end_us is None or end_us <= start_us:
                    continue

                segment_id = f"{context.episode_id}:asr-segment:{raw_segment_index:06d}"
                words = tuple(getattr(segment, "words", None) or ())
                segment_payload: dict[str, Any] = {
                    "segment_index": raw_segment_index,
                    "word_count": len(words),
                }
                for name in ("avg_logprob", "no_speech_prob", "compression_ratio", "temperature"):
                    value = self._finite_float(getattr(segment, name, None))
                    if value is not None:
                        segment_payload[name] = value
                seek = getattr(segment, "seek", None)
                if isinstance(seek, int):
                    segment_payload["seek"] = seek

                evidence.append(p2.P2EvidenceRecord(
                    source_type="ASR_SEGMENT",
                    source_id=segment_id,
                    source_start_us=start_us,
                    source_end_us=end_us,
                    shot_revision_item_id=None,
                    text=text,
                    language=detected_language,
                    confidence=None,
                    payload=segment_payload,
                ))
                segment_count += 1

                emitted_words = 0
                for raw_word_index, word in enumerate(words):
                    word_text_raw = str(getattr(word, "word", "") or "")
                    word_text = word_text_raw.strip()
                    word_start_us = self._seconds_to_us(getattr(word, "start", None))
                    word_end_us = self._seconds_to_us(getattr(word, "end", None))
                    if not word_text or word_start_us is None or word_end_us is None or word_end_us <= word_start_us:
                        continue
                    probability = self._probability(getattr(word, "probability", None))
                    word_id = f"{segment_id}:word:{raw_word_index:04d}"
                    evidence.append(p2.P2EvidenceRecord(
                        source_type="ASR_WORD",
                        source_id=word_id,
                        source_start_us=word_start_us,
                        source_end_us=word_end_us,
                        shot_revision_item_id=None,
                        text=word_text,
                        language=detected_language,
                        confidence=probability,
                        payload={
                            "segment_id": segment_id,
                            "segment_index": raw_segment_index,
                            "word_index": raw_word_index,
                            "raw_word": word_text_raw,
                        },
                    ))
                    emitted_words += 1
                    word_count += 1
                if emitted_words == 0:
                    missing_word_segments += 1

            warnings = list(load_warnings)
            if segment_count and word_count == 0:
                warnings.append("ASR produced segments but no usable word timestamps")
            elif missing_word_segments:
                warnings.append(f"{missing_word_segments} ASR segment(s) had no usable word timestamps")

            metadata = self._result_metadata(
                actual_device=actual_device,
                actual_compute_type=actual_compute_type,
                requested_language=requested_language,
                info=info,
            )
            metadata["segment_count"] = segment_count
            metadata["word_count"] = word_count
            return p2.P2ProviderResult(
                component="ASR",
                provider=ASR_PROVIDER_NAME,
                model=self.model_name,
                status="READY" if evidence else "NO_EVIDENCE",
                evidence=tuple(evidence),
                metadata=metadata,
                warnings=tuple(warnings),
            )
        except Exception as exc:
            return p2.P2ProviderResult(
                component="ASR",
                provider=ASR_PROVIDER_NAME,
                model=self.model_name,
                status="FAILED",
                metadata=self._result_metadata(
                    actual_device=actual_device,
                    actual_compute_type=actual_compute_type,
                    requested_language=requested_language,
                    error_type=type(exc).__name__,
                ),
                warnings=tuple(load_warnings) + ("ASR transcription failed",),
            )


def run_faster_whisper_asr(
    run_id: str,
    *,
    provider: FasterWhisperASRProvider | None = None,
) -> p2.P2EvidenceArtifact:
    """P2.2 正式入口：执行 faster-whisper，并交给 P2.1 sidecar 固化 provenance。"""

    return p2.run_local_provider(run_id, provider or FasterWhisperASRProvider())
