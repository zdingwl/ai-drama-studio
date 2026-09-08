import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import Settings
from app.core.errors import AppError


@dataclass(frozen=True)
class AsrSegmentResult:
    start_us: int
    end_us: int
    text: str
    language: str | None
    confidence: float | None
    provenance: dict


@dataclass(frozen=True)
class OcrDetectionResult:
    text: str
    confidence: float | None
    bbox: list


class AsrProvider(Protocol):
    profile: dict
    def transcribe(self, source_path: Path, *, language_hint: str | None, duration_us: int, on_progress: Callable[[float], None] | None = None) -> list[AsrSegmentResult]: ...


class OcrProvider(Protocol):
    profile: dict
    def recognize(self, image: object) -> list[OcrDetectionResult]: ...


class FasterWhisperAsrProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.profile = {"provider":"faster-whisper","model":settings.p6_asr_model,"device":settings.p6_asr_device,"compute_type":settings.p6_asr_compute_type,"vad_filter":True,"word_timestamps":True,"continuous_episode_input":True}
        self._model = None

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise AppError("P6_ASR_RUNTIME_MISSING", "ASR 运行依赖未安装，请安装 faster-whisper", status_code=503) from exc
        kwargs = {"device": self.settings.p6_asr_device, "compute_type": self.settings.p6_asr_compute_type}
        if self.settings.p6_asr_download_root:
            kwargs["download_root"] = str(self.settings.p6_asr_download_root)
        try:
            self._model = WhisperModel(self.settings.p6_asr_model, **kwargs)
        except Exception as exc:
            raise AppError("P6_ASR_MODEL_UNAVAILABLE", "ASR 模型不可用，请检查本地模型缓存与运行环境", status_code=503) from exc
        return self._model

    def transcribe(self, source_path: Path, *, language_hint: str | None, duration_us: int, on_progress: Callable[[float], None] | None = None) -> list[AsrSegmentResult]:
        model = self._get_model()
        language = language_hint.split("-", 1)[0].lower() if language_hint else None
        try:
            segments, info = model.transcribe(str(source_path), language=language, vad_filter=True, word_timestamps=True, beam_size=5)
            output: list[AsrSegmentResult] = []
            detected_language = getattr(info, "language", None) or language
            for segment in segments:
                text = str(getattr(segment, "text", "")).strip()
                if not text:
                    continue
                start_us = max(0, int(round(float(segment.start) * 1_000_000)))
                end_us = max(start_us + 1, int(round(float(segment.end) * 1_000_000)))
                avg_logprob = getattr(segment, "avg_logprob", None)
                confidence = max(0.0, min(1.0, math.exp(float(avg_logprob)))) if avg_logprob is not None else None
                output.append(AsrSegmentResult(start_us=start_us,end_us=end_us,text=text,language=detected_language,confidence=confidence,provenance={"provider":"faster-whisper","model":self.settings.p6_asr_model,"segment_id":getattr(segment,"id",None),"seek":getattr(segment,"seek",None),"avg_logprob":avg_logprob,"no_speech_prob":getattr(segment,"no_speech_prob",None)}))
                if on_progress is not None and duration_us > 0:
                    on_progress(min(1.0, end_us / duration_us))
            if on_progress is not None:
                on_progress(1.0)
            return output
        except AppError:
            raise
        except Exception as exc:
            raise AppError("P6_ASR_FAILED", "连续音轨识别失败", status_code=422) from exc


class RapidOcrProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.profile = {"provider":"rapidocr","engine":"onnxruntime","min_confidence":settings.p6_ocr_min_confidence}
        self._engine = None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise AppError("P6_OCR_RUNTIME_MISSING", "OCR 运行依赖未安装，请安装 rapidocr 与 onnxruntime", status_code=503) from exc
        try:
            self._engine = RapidOCR()
        except Exception as exc:
            raise AppError("P6_OCR_MODEL_UNAVAILABLE", "OCR 模型不可用，请检查本地运行环境", status_code=503) from exc
        return self._engine

    def recognize(self, image: object) -> list[OcrDetectionResult]:
        try:
            result = self._get_engine()(image)
        except Exception as exc:
            raise AppError("P6_OCR_FAILED", "画面文字识别失败", status_code=422) from exc
        txts = list(getattr(result, "txts", None) or [])
        scores = list(getattr(result, "scores", None) or [])
        boxes = list(getattr(result, "boxes", None) or [])
        output: list[OcrDetectionResult] = []
        for index, raw_text in enumerate(txts):
            text = str(raw_text).strip()
            if not text:
                continue
            score = float(scores[index]) if index < len(scores) and scores[index] is not None else None
            if score is not None and score < self.settings.p6_ocr_min_confidence:
                continue
            raw_box = boxes[index] if index < len(boxes) else []
            box = raw_box.tolist() if hasattr(raw_box, "tolist") else list(raw_box or [])
            output.append(OcrDetectionResult(text=text, confidence=score, bbox=box))
        return output


@dataclass(frozen=True)
class EvidenceProviders:
    asr: AsrProvider
    ocr: OcrProvider


def build_evidence_providers(settings: Settings) -> EvidenceProviders:
    if settings.p6_asr_provider != "faster-whisper":
        raise AppError("P6_ASR_PROVIDER_INVALID", "当前只支持本地 faster-whisper ASR", status_code=500)
    if settings.p6_ocr_provider != "rapidocr":
        raise AppError("P6_OCR_PROVIDER_INVALID", "当前只支持本地 RapidOCR", status_code=500)
    return EvidenceProviders(asr=FasterWhisperAsrProvider(settings), ocr=RapidOcrProvider(settings))
