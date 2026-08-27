"""Breakdown-first Phase P2.3：RapidOCR 匿名 OCR Observation Provider。

职责：
- 消费 P2.1 冻结的 exact ShotRevisionItem / Reference Clip；
- 在每个历史 Reference Clip 内按确定性时间点采样多帧，而不是只扫一张中间缩略图；
- 使用 RapidOCR + PP-OCRv6 生成 shot/frame-grounded ``OCR_OBSERVATION`` raw Evidence；
- 保存文字、置信度、polygon/bbox、帧尺寸和 source integer microseconds；
- 每条 Evidence 强绑定其历史 ``ShotRevisionItem``，不重新从 Current ``v2_shots`` 猜来源；
- 不在 OCR 层把重复字幕合并成 TimelineEvent；跨帧去重/持续时间推断留给 P2.5 Fusion；
- 不创建 Character / Scene / Prop / AssetRevision，也不写任何 Final Binding。

当前正式基线：RapidOCR 3.9.2 + PP-OCRv6 small + ONNX Runtime。
默认 CPU 稳定优先；``AI_DRAMA_P2_OCR_DEVICE=auto/cuda`` 可显式启用 GPU 路径。
真实短剧上的模型量级、采样间隔、CPU/GPU 效果仍由 P2.6 benchmark 决定。
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from engine.app import breakdown_p2_sidecar_v1 as p2

OCR_PROVIDER_NAME = "rapidocr"
DEFAULT_OCR_VERSION = "PP-OCRv6"
DEFAULT_OCR_MODEL_TYPE = "small"
DEFAULT_SAMPLE_INTERVAL_US = 500_000
DEFAULT_MAX_FRAMES_PER_SHOT = 12
DEFAULT_TEXT_SCORE = 0.5
FRAME_EVIDENCE_DURATION_US = 1


@dataclass(frozen=True)
class OCRFrameSample:
    """Reference Clip 中一张已解码采样帧。

    ``requested_relative_us`` 是相对该历史 Shot 起点的确定性采样位置。Provider 用它恢复
    Episode source 绝对时间；``image`` 只在内存里交给 OCR，不写入 sidecar。
    """

    sample_index: int
    requested_relative_us: int
    image: Any
    width: int
    height: int


FrameSampler = Callable[[p2.P2ShotInput, tuple[int, ...]], Sequence[OCRFrameSample]]
EngineFactory = Callable[[Mapping[str, Any]], Any]
CudaAvailable = Callable[[], bool]


class RapidOCROCRProvider:
    """同步本地 RapidOCR Provider，只产出匿名 OCR raw Evidence。"""

    component = "OCR"

    def __init__(
        self,
        *,
        model_type: str | None = None,
        device: str | None = None,
        sample_interval_us: int | None = None,
        max_frames_per_shot: int | None = None,
        text_score: float | None = None,
        model_root_dir: str | None = None,
        engine_factory: EngineFactory | None = None,
        frame_sampler: FrameSampler | None = None,
        cuda_available: CudaAvailable | None = None,
    ) -> None:
        self.model_type = (
            model_type or os.getenv("AI_DRAMA_P2_OCR_MODEL_TYPE") or DEFAULT_OCR_MODEL_TYPE
        ).strip().lower()
        self.requested_device = (
            device or os.getenv("AI_DRAMA_P2_OCR_DEVICE") or "cpu"
        ).strip().lower()
        raw_interval = sample_interval_us
        if raw_interval is None:
            raw_interval = int(os.getenv("AI_DRAMA_P2_OCR_SAMPLE_INTERVAL_US") or DEFAULT_SAMPLE_INTERVAL_US)
        raw_max_frames = max_frames_per_shot
        if raw_max_frames is None:
            raw_max_frames = int(os.getenv("AI_DRAMA_P2_OCR_MAX_FRAMES_PER_SHOT") or DEFAULT_MAX_FRAMES_PER_SHOT)
        raw_text_score = text_score
        if raw_text_score is None:
            raw_text_score = float(os.getenv("AI_DRAMA_P2_OCR_TEXT_SCORE") or DEFAULT_TEXT_SCORE)

        self.sample_interval_us = int(raw_interval)
        self.max_frames_per_shot = int(raw_max_frames)
        self.text_score = float(raw_text_score)
        self.model_root_dir = (
            model_root_dir if model_root_dir is not None else os.getenv("AI_DRAMA_P2_OCR_MODEL_CACHE")
        )
        self._engine_factory = engine_factory
        self._frame_sampler = frame_sampler or self._opencv_frame_sampler
        self._cuda_available = cuda_available
        self._engine: Any | None = None
        self._engine_language: str | None = None
        self._actual_device: str | None = None
        self._load_warnings: tuple[str, ...] = ()

        if self.model_type not in {"small", "medium"}:
            raise ValueError("P2 OCR model_type 当前只允许 small/medium")
        if self.requested_device not in {"cpu", "cuda", "auto"}:
            raise ValueError("P2 OCR device 只允许 cpu/cuda/auto")
        if self.sample_interval_us <= 0:
            raise ValueError("P2 OCR sample_interval_us 必须 > 0")
        if self.max_frames_per_shot < 1:
            raise ValueError("P2 OCR max_frames_per_shot 必须 >= 1")
        if not 0.0 <= self.text_score <= 1.0:
            raise ValueError("P2 OCR text_score 必须在 0..1")

    @property
    def model_name(self) -> str:
        return f"{DEFAULT_OCR_VERSION}-{self.model_type}"

    @staticmethod
    def _finite_float(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        return number

    @classmethod
    def _probability(cls, value: Any) -> float | None:
        number = cls._finite_float(value)
        if number is None or not 0.0 <= number <= 1.0:
            return None
        return number

    @staticmethod
    def _recognition_language(source_language: str) -> str:
        """把项目 BCP-47/语言名压到 RapidOCR PP-OCRv6 recognition profile。"""

        value = (source_language or "").strip().lower().replace("_", "-")
        base = value.split("-", 1)[0] if value else ""
        if value.startswith("zh"):
            if any(token in value for token in ("tw", "hk", "mo", "hant")):
                return "chinese_cht"
            return "ch"
        if base == "yue":
            return "chinese_cht"
        direct = {
            "en": "en",
            "ja": "japan",
            "ko": "korean",
            "ar": "arabic",
            "fa": "arabic",
            "ur": "arabic",
            "th": "th",
            "el": "el",
            "ta": "ta",
            "te": "te",
            "ka": "ka",
        }
        if base in direct:
            return direct[base]
        if base in {"ru", "uk", "be", "bg", "mk", "sr"}:
            return "cyrillic"
        if base in {"hi", "mr", "ne", "sa"}:
            return "devanagari"
        # PP-OCRv6 small 的 latin profile 覆盖项目常见西欧/东南亚拉丁字母语言。
        return "latin"

    def _sample_relative_times(self, duration_us: int) -> tuple[int, ...]:
        """生成覆盖整个 Shot 的确定性采样时间，并严格限制单 Shot 最大帧数。"""

        duration_us = int(duration_us)
        if duration_us <= 1:
            return ()
        edge_margin = min(100_000, max(0, duration_us // 4))
        start = min(duration_us - 1, edge_margin)
        end = max(start, duration_us - edge_margin - 1)
        if end <= start:
            return (max(0, min(duration_us - 1, duration_us // 2)),)

        span = end - start
        desired_count = int(math.ceil(span / self.sample_interval_us)) + 1
        count = max(1, min(self.max_frames_per_shot, desired_count))
        if count == 1:
            return (max(start, min(end, duration_us // 2)),)

        points = tuple(
            start + (span * index) // (count - 1)
            for index in range(count)
        )
        return tuple(sorted(set(max(0, min(duration_us - 1, point)) for point in points)))

    @staticmethod
    def _opencv_frame_sampler(
        shot: p2.P2ShotInput,
        relative_times_us: tuple[int, ...],
    ) -> tuple[OCRFrameSample, ...]:
        """用 OpenCV 从历史 Reference Clip 解码指定相对时间帧；仅运行时懒导入 cv2。"""

        import cv2

        path = Path(shot.reference_clip_path)
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise RuntimeError("Reference Clip 无法打开")
        samples: list[OCRFrameSample] = []
        try:
            for sample_index, relative_us in enumerate(relative_times_us):
                capture.set(cv2.CAP_PROP_POS_MSEC, relative_us / 1000.0)
                ok, frame = capture.read()
                if not ok or frame is None:
                    continue
                if not hasattr(frame, "shape") or len(frame.shape) < 2:
                    continue
                height = int(frame.shape[0])
                width = int(frame.shape[1])
                if width <= 0 or height <= 0:
                    continue
                samples.append(OCRFrameSample(
                    sample_index=sample_index,
                    requested_relative_us=int(relative_us),
                    image=frame,
                    width=width,
                    height=height,
                ))
        finally:
            capture.release()
        return tuple(samples)

    def _get_cuda_available(self) -> bool:
        if self._cuda_available is not None:
            try:
                return bool(self._cuda_available())
            except Exception:
                return False
        try:
            import onnxruntime as ort

            providers = set(ort.get_available_providers())
            return ort.get_device() == "GPU" and "CUDAExecutionProvider" in providers
        except Exception:
            return False

    def _engine_params(self, *, recognition_language: str, use_cuda: bool) -> dict[str, Any]:
        params: dict[str, Any] = {
            "Global.text_score": self.text_score,
            "Global.return_word_box": False,
            "Global.log_level": "critical",
            "Det.engine_type": "onnxruntime",
            "Det.lang_type": "multi",
            "Det.model_type": self.model_type,
            "Det.ocr_version": DEFAULT_OCR_VERSION,
            "Rec.engine_type": "onnxruntime",
            "Rec.lang_type": recognition_language,
            "Rec.model_type": self.model_type,
            "Rec.ocr_version": DEFAULT_OCR_VERSION,
            "EngineConfig.onnxruntime.use_cuda": bool(use_cuda),
        }
        if self.model_root_dir:
            params["Global.model_root_dir"] = self.model_root_dir
        return params

    @staticmethod
    def _production_engine_factory(params: Mapping[str, Any]) -> Any:
        """把稳定的字符串配置转换为 RapidOCR 3.9.x 枚举，避免 SDK 类型泄漏到业务层。"""

        from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR

        converted = dict(params)
        converted["Det.engine_type"] = EngineType.ONNXRUNTIME
        converted["Det.lang_type"] = LangDet.MULTI
        converted["Det.model_type"] = ModelType(str(params["Det.model_type"]))
        converted["Det.ocr_version"] = OCRVersion.PPOCRV6
        converted["Rec.engine_type"] = EngineType.ONNXRUNTIME
        converted["Rec.lang_type"] = LangRec(str(params["Rec.lang_type"]))
        converted["Rec.model_type"] = ModelType(str(params["Rec.model_type"]))
        converted["Rec.ocr_version"] = OCRVersion.PPOCRV6
        return RapidOCR(params=converted)

    def _new_engine(self, *, recognition_language: str, device: str) -> Any:
        params = self._engine_params(
            recognition_language=recognition_language,
            use_cuda=device == "cuda",
        )
        factory = self._engine_factory or self._production_engine_factory
        return factory(params)

    def _load_engine(self, recognition_language: str) -> tuple[Any, str, tuple[str, ...]]:
        if (
            self._engine is not None
            and self._engine_language == recognition_language
            and self._actual_device is not None
        ):
            return self._engine, self._actual_device, self._load_warnings

        cuda_available = self._get_cuda_available()
        if self.requested_device == "cuda" and not cuda_available:
            raise RuntimeError("CUDAExecutionProvider is not available")
        device = self.requested_device
        if device == "auto":
            device = "cuda" if cuda_available else "cpu"

        warnings: list[str] = []
        try:
            engine = self._new_engine(recognition_language=recognition_language, device=device)
        except Exception:
            # 与 ASR 一样，仅 auto-selected CUDA 允许可见降级；显式 cuda 必须 fail closed。
            if self.requested_device != "auto" or device != "cuda":
                raise
            engine = self._new_engine(recognition_language=recognition_language, device="cpu")
            device = "cpu"
            warnings.append("CUDA OCR engine load failed; fell back to CPU")

        self._engine = engine
        self._engine_language = recognition_language
        self._actual_device = device
        self._load_warnings = tuple(warnings)
        return engine, device, self._load_warnings

    @classmethod
    def _polygon_points(cls, raw_box: Any, *, width: int, height: int) -> list[list[float]] | None:
        try:
            raw_points = list(raw_box)
        except TypeError:
            return None
        points: list[list[float]] = []
        for raw_point in raw_points:
            try:
                values = list(raw_point)
            except TypeError:
                return None
            if len(values) < 2:
                return None
            x = cls._finite_float(values[0])
            y = cls._finite_float(values[1])
            if x is None or y is None:
                return None
            x = min(max(x, 0.0), max(0.0, float(width - 1)))
            y = min(max(y, 0.0), max(0.0, float(height - 1)))
            points.append([x, y])
        return points if len(points) >= 4 else None

    @staticmethod
    def _bbox(points: Sequence[Sequence[float]]) -> list[float]:
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        return [min(xs), min(ys), max(xs), max(ys)]

    @staticmethod
    def _normalized_polygon(
        points: Sequence[Sequence[float]],
        *,
        width: int,
        height: int,
    ) -> list[list[float]]:
        width_scale = float(max(1, width - 1))
        height_scale = float(max(1, height - 1))
        return [
            [float(point[0]) / width_scale, float(point[1]) / height_scale]
            for point in points
        ]

    @staticmethod
    def _result_rows(raw_result: Any) -> tuple[tuple[Any, str, Any], ...]:
        boxes = getattr(raw_result, "boxes", None)
        texts = getattr(raw_result, "txts", None)
        scores = getattr(raw_result, "scores", None)
        if boxes is None or texts is None or scores is None:
            return ()
        try:
            return tuple(zip(list(boxes), list(texts), list(scores)))
        except TypeError:
            return ()

    def _base_metadata(
        self,
        *,
        recognition_language: str,
        actual_device: str | None,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "engine": "onnxruntime",
            "ocr_version": DEFAULT_OCR_VERSION,
            "model_type": self.model_type,
            "recognition_language": recognition_language,
            "device_requested": self.requested_device,
            "device": actual_device,
            "sample_interval_us": self.sample_interval_us,
            "max_frames_per_shot": self.max_frames_per_shot,
            "text_score": self.text_score,
        }
        if error_type:
            metadata["error_type"] = error_type
        return metadata

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        recognition_language = self._recognition_language(context.source_language)
        available_shots = [
            shot for shot in context.shots
            if Path(shot.reference_clip_path).is_file()
        ]
        missing_shot_count = len(context.shots) - len(available_shots)
        if not available_shots:
            metadata = self._base_metadata(
                recognition_language=recognition_language,
                actual_device=None,
            )
            metadata.update({
                "shot_count": len(context.shots),
                "missing_reference_clip_count": missing_shot_count,
                "frames_requested": 0,
                "frames_decoded": 0,
                "frames_analyzed": 0,
                "observation_count": 0,
            })
            return p2.P2ProviderResult(
                component="OCR",
                provider=OCR_PROVIDER_NAME,
                model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=metadata,
                warnings=("No historical Reference Clip is available for OCR",),
            )

        try:
            engine, actual_device, load_warnings = self._load_engine(recognition_language)
        except ImportError:
            return p2.P2ProviderResult(
                component="OCR",
                provider=OCR_PROVIDER_NAME,
                model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._base_metadata(
                    recognition_language=recognition_language,
                    actual_device=None,
                    error_type="ImportError",
                ),
                warnings=("RapidOCR runtime is not installed",),
            )
        except Exception as exc:
            return p2.P2ProviderResult(
                component="OCR",
                provider=OCR_PROVIDER_NAME,
                model=self.model_name,
                status="FAILED",
                metadata=self._base_metadata(
                    recognition_language=recognition_language,
                    actual_device=None,
                    error_type=type(exc).__name__,
                ),
                warnings=("OCR engine load failed",),
            )

        evidence: list[p2.P2EvidenceRecord] = []
        warnings = list(load_warnings)
        if missing_shot_count:
            warnings.append(f"{missing_shot_count} historical Reference Clip(s) were missing")

        frames_requested = 0
        frames_decoded = 0
        frames_analyzed = 0
        shot_decode_failures = 0
        frame_ocr_failures = 0
        observation_count = 0

        for shot in available_shots:
            relative_times = self._sample_relative_times(shot.duration_us)
            frames_requested += len(relative_times)
            if not relative_times:
                shot_decode_failures += 1
                continue
            try:
                samples = tuple(self._frame_sampler(shot, relative_times))
            except ImportError:
                metadata = self._base_metadata(
                    recognition_language=recognition_language,
                    actual_device=actual_device,
                    error_type="ImportError",
                )
                metadata.update({
                    "shot_count": len(context.shots),
                    "missing_reference_clip_count": missing_shot_count,
                    "frames_requested": frames_requested,
                    "frames_decoded": frames_decoded,
                    "frames_analyzed": frames_analyzed,
                    "observation_count": observation_count,
                })
                return p2.P2ProviderResult(
                    component="OCR",
                    provider=OCR_PROVIDER_NAME,
                    model=self.model_name,
                    status="NOT_AVAILABLE",
                    metadata=metadata,
                    warnings=tuple(warnings) + ("OpenCV frame decoder is not installed",),
                )
            except Exception:
                shot_decode_failures += 1
                continue

            valid_samples = [
                sample for sample in samples
                if (
                    0 <= int(sample.requested_relative_us) < int(shot.duration_us)
                    and int(sample.width) > 0
                    and int(sample.height) > 0
                )
            ]
            frames_decoded += len(valid_samples)
            if not valid_samples:
                shot_decode_failures += 1
                continue

            for sample in valid_samples:
                try:
                    raw_result = engine(sample.image)
                except Exception:
                    frame_ocr_failures += 1
                    continue
                frames_analyzed += 1
                rows = self._result_rows(raw_result)
                for raw_observation_index, (raw_box, raw_text, raw_score) in enumerate(rows):
                    text = str(raw_text or "").strip()
                    if not text:
                        continue
                    confidence = self._probability(raw_score)
                    if confidence is not None and confidence < self.text_score:
                        continue
                    polygon = self._polygon_points(
                        raw_box,
                        width=int(sample.width),
                        height=int(sample.height),
                    )
                    if polygon is None:
                        continue
                    relative_us = int(sample.requested_relative_us)
                    source_start_us = int(shot.start_us) + relative_us
                    source_end_us = min(source_start_us + FRAME_EVIDENCE_DURATION_US, int(shot.end_us))
                    if source_end_us <= source_start_us:
                        continue

                    source_id = (
                        f"{context.episode_id}:ocr:{shot.revision_item_id}:"
                        f"{sample.sample_index:04d}:{raw_observation_index:04d}"
                    )
                    evidence.append(p2.P2EvidenceRecord(
                        source_type="OCR_OBSERVATION",
                        source_id=source_id,
                        source_start_us=source_start_us,
                        source_end_us=source_end_us,
                        shot_revision_item_id=shot.revision_item_id,
                        text=text,
                        language=context.source_language or None,
                        confidence=confidence,
                        payload={
                            "shot_ordinal": int(shot.ordinal),
                            "frame_sample_index": int(sample.sample_index),
                            "frame_relative_us": relative_us,
                            "image_width": int(sample.width),
                            "image_height": int(sample.height),
                            "polygon_px": polygon,
                            "bbox_px": self._bbox(polygon),
                            "polygon_norm": self._normalized_polygon(
                                polygon,
                                width=int(sample.width),
                                height=int(sample.height),
                            ),
                            "recognition_language": recognition_language,
                        },
                    ))
                    observation_count += 1

        if shot_decode_failures:
            warnings.append(f"{shot_decode_failures} OCR shot sample set(s) could not be decoded")
        if frame_ocr_failures:
            warnings.append(f"{frame_ocr_failures} OCR frame inference call(s) failed")

        metadata = self._base_metadata(
            recognition_language=recognition_language,
            actual_device=actual_device,
        )
        metadata.update({
            "shot_count": len(context.shots),
            "available_reference_clip_count": len(available_shots),
            "missing_reference_clip_count": missing_shot_count,
            "frames_requested": frames_requested,
            "frames_decoded": frames_decoded,
            "frames_analyzed": frames_analyzed,
            "shot_decode_failures": shot_decode_failures,
            "frame_ocr_failures": frame_ocr_failures,
            "observation_count": observation_count,
        })

        if frames_decoded == 0 or frames_analyzed == 0:
            return p2.P2ProviderResult(
                component="OCR",
                provider=OCR_PROVIDER_NAME,
                model=self.model_name,
                status="FAILED",
                metadata=metadata,
                warnings=tuple(warnings) + ("OCR could not analyze any sampled Reference Clip frame",),
            )
        return p2.P2ProviderResult(
            component="OCR",
            provider=OCR_PROVIDER_NAME,
            model=self.model_name,
            status="READY" if evidence else "NO_EVIDENCE",
            evidence=tuple(evidence),
            metadata=metadata,
            warnings=tuple(warnings),
        )


def run_rapidocr_ocr(
    run_id: str,
    *,
    provider: RapidOCROCRProvider | None = None,
) -> p2.P2EvidenceArtifact:
    """P2.3 正式入口：执行 RapidOCR，并复用 P2.1 sidecar 固化 raw OCR provenance。"""

    return p2.run_local_provider(run_id, provider or RapidOCROCRProvider())
