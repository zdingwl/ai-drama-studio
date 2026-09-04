"""Breakdown-first Phase P2.4：Qwen3-VL 匿名 Shot 语义 Evidence Provider。

职责：
- 消费 P2.1 冻结的 exact ShotRevisionItem / Reference Clip；
- 使用独立 Qwen3-VL 内容理解模型逐 Shot 提取匿名视觉语义；
- 只输出白名单化 ``VLM_OUTPUT`` raw Evidence；
- 每条 Evidence 强绑定历史 ShotRevisionItem，并使用 Episode source integer microseconds；
- 不生成 P1 Draft rows；SceneSegment/LocalSubject/TimelineEvent/PropHint 由 P2.5 Fusion 负责；
- 不创建 Character / Scene / Prop / AssetRevision，不写任何 Final Binding；
- 不把字幕/OCR 或对白/ASR 能力重复塞进 VLM，不允许模型文案冒充身份真值。

正式基线使用独立 ``Qwen/Qwen3-VL-4B-Instruct`` checkpoint。为了避免把新版
Transformers/Torch 依赖塞进主工程 Python 3.11 venv，生产默认复用已经验证过的
TransVLM 隔离 Python 3.12 runtime *环境*，但绝不复用其转场微调 checkpoint。
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Mapping, Sequence

from engine.app import breakdown_p2_sidecar_v1 as p2

VLM_PROVIDER_NAME = "qwen3-vl"
DEFAULT_VLM_MODEL = "Qwen/Qwen3-VL-4B-Instruct"
VLM_SEMANTIC_SCHEMA = "breakdown-p2-vlm-shot-semantics-v1"
DEFAULT_VIDEO_FPS = 2.0
DEFAULT_MAX_NEW_TOKENS = 1536
DEFAULT_MAX_PIXELS = 524_288
VLM_TIMEOUT_SECONDS = 4 * 60 * 60

_ALLOWED_INTERIOR_EXTERIOR = frozenset({"INT", "EXT", "MIXED", "UNKNOWN"})
_ALLOWED_VISIBILITY = frozenset({"FULL", "PARTIAL", "OCCLUDED", "UNKNOWN"})
_ALLOWED_SPEAKING_STATE = frozenset({"LIKELY_SPEAKING", "NOT_SPEAKING", "UNKNOWN"})
_ALLOWED_EVENT_TYPES = frozenset({"VISUAL", "ACTION"})
_ALLOWED_PROP_IMPORTANCE = frozenset({"LOW", "MEDIUM", "HIGH"})

InferenceRunner = Callable[["VLMRuntimeConfig", Sequence[p2.P2ShotInput]], Sequence[Mapping[str, Any]]]


@dataclass(frozen=True)
class VLMRuntimeConfig:
    """一次 Qwen3-VL 语义推理的隔离 runtime 配置。"""

    python_executable: Path
    runner_script: Path
    model_path: Path
    model_name: str
    source_language: str
    device: str
    video_fps: float
    max_new_tokens: int
    max_pixels: int
    ffmpeg_shared_bin: Path | None


class Qwen3VLSemanticProvider:
    """同步本地 Qwen3-VL Provider，只产生匿名视觉 Shot 语义 raw Evidence。"""

    component = "VLM"

    def __init__(
        self,
        *,
        model_name: str | None = None,
        model_path: str | None = None,
        python_executable: str | None = None,
        runner_script: str | None = None,
        device: str | None = None,
        video_fps: float | None = None,
        max_new_tokens: int | None = None,
        max_pixels: int | None = None,
        ffmpeg_shared_bin: str | None = None,
        inference_runner: InferenceRunner | None = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        inference_root = repo_root / ".runtime" / "TransVLM" / "inference"
        default_python = (
            inference_root / ".venv" / "Scripts" / "python.exe"
            if os.name == "nt"
            else inference_root / ".venv" / "bin" / "python"
        )
        default_model_path = inference_root / "pretrained" / "Qwen3-VL-4B-Instruct"
        default_runner = repo_root / "scripts" / "run_breakdown_vlm_qwen3.py"

        self.model_name = (
            model_name or os.getenv("AI_DRAMA_P2_VLM_MODEL") or DEFAULT_VLM_MODEL
        ).strip()
        self.model_path = Path(
            model_path or os.getenv("AI_DRAMA_P2_VLM_MODEL_PATH") or str(default_model_path)
        ).expanduser()
        self.python_executable = Path(
            python_executable or os.getenv("AI_DRAMA_P2_VLM_PYTHON") or str(default_python)
        ).expanduser()
        self.runner_script = Path(
            runner_script or os.getenv("AI_DRAMA_P2_VLM_RUNNER") or str(default_runner)
        ).expanduser()
        self.device = (device or os.getenv("AI_DRAMA_P2_VLM_DEVICE") or "cuda").strip().lower()
        raw_fps = video_fps
        if raw_fps is None:
            raw_fps = float(os.getenv("AI_DRAMA_P2_VLM_FPS") or DEFAULT_VIDEO_FPS)
        raw_tokens = max_new_tokens
        if raw_tokens is None:
            raw_tokens = int(os.getenv("AI_DRAMA_P2_VLM_MAX_NEW_TOKENS") or DEFAULT_MAX_NEW_TOKENS)
        raw_pixels = max_pixels
        if raw_pixels is None:
            raw_pixels = int(os.getenv("AI_DRAMA_P2_VLM_MAX_PIXELS") or DEFAULT_MAX_PIXELS)
        self.video_fps = float(raw_fps)
        self.max_new_tokens = int(raw_tokens)
        self.max_pixels = int(raw_pixels)

        configured_ffmpeg = ffmpeg_shared_bin or os.getenv("AI_DRAMA_P2_VLM_FFMPEG_BIN")
        if configured_ffmpeg:
            self.ffmpeg_shared_bin = Path(configured_ffmpeg).expanduser()
        else:
            marker = inference_root.parent / "ffmpeg_shared_bin.txt"
            try:
                value = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
            except OSError:
                value = ""
            self.ffmpeg_shared_bin = Path(value).expanduser() if value else None

        self._inference_runner = inference_runner or self._run_subprocess
        self._uses_production_runner = inference_runner is None

        if not self.model_name:
            raise ValueError("P2 VLM model_name 不能为空")
        if self.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("P2 VLM device 只允许 auto/cpu/cuda")
        if not math.isfinite(self.video_fps) or self.video_fps <= 0:
            raise ValueError("P2 VLM fps 必须 > 0")
        if self.max_new_tokens < 64:
            raise ValueError("P2 VLM max_new_tokens 必须 >= 64")
        if self.max_pixels < 16 * 16:
            raise ValueError("P2 VLM max_pixels 太小")

    @staticmethod
    def _clean_text(value: Any, *, max_len: int = 2000) -> str | None:
        if value is None:
            return None
        text = " ".join(str(value).strip().split())
        if not text:
            return None
        return text[:max_len]

    @staticmethod
    def _ratio(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        return min(1.0, max(0.0, number))

    @staticmethod
    def _enum(value: Any, allowed: frozenset[str], default: str | None = None) -> str | None:
        normalized = str(value or "").strip().upper()
        if normalized in allowed:
            return normalized
        return default

    @staticmethod
    def _subject_label(value: Any) -> str | None:
        label = str(value or "").strip()
        if not label or len(label) > 64:
            return None
        if not label.lower().startswith("subject_"):
            return None
        if not all(ch.isalnum() or ch == "_" for ch in label):
            return None
        return label

    def _runtime_config(self, source_language: str) -> VLMRuntimeConfig:
        return VLMRuntimeConfig(
            python_executable=self.python_executable,
            runner_script=self.runner_script,
            model_path=self.model_path,
            model_name=self.model_name,
            source_language=source_language,
            device=self.device,
            video_fps=self.video_fps,
            max_new_tokens=self.max_new_tokens,
            max_pixels=self.max_pixels,
            ffmpeg_shared_bin=self.ffmpeg_shared_bin,
        )

    def _runtime_missing(self, config: VLMRuntimeConfig) -> tuple[str, ...]:
        if not self._uses_production_runner:
            return ()
        missing: list[str] = []
        if not config.python_executable.is_file():
            missing.append("isolated Qwen3-VL Python runtime")
        if not config.runner_script.is_file():
            missing.append("P2.4 Qwen3-VL runner script")
        if not config.model_path.is_dir():
            missing.append("Qwen3-VL-4B-Instruct checkpoint")
        elif not (config.model_path / "config.json").is_file():
            missing.append("Qwen3-VL checkpoint config.json")
        return tuple(missing)

    @staticmethod
    def _subprocess_env(config: VLMRuntimeConfig) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("HF_HUB_OFFLINE", "1")
        env.setdefault("TRANSFORMERS_OFFLINE", "1")
        if os.name == "nt" and config.ffmpeg_shared_bin and config.ffmpeg_shared_bin.is_dir():
            existing = env.get("PATH", "")
            prefixes = [str(config.ffmpeg_shared_bin)]
            torch_lib = config.python_executable.parents[1] / "Lib" / "site-packages" / "torch" / "lib"
            if torch_lib.is_dir():
                prefixes.append(str(torch_lib))
            env["PATH"] = os.pathsep.join(prefixes + ([existing] if existing else []))
        return env

    @staticmethod
    def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def _run_subprocess(
        self,
        config: VLMRuntimeConfig,
        shots: Sequence[p2.P2ShotInput],
    ) -> Sequence[Mapping[str, Any]]:
        """在隔离 Python 3.12 runtime 中一次加载模型并按 Shot 顺序完成推理。"""

        with tempfile.TemporaryDirectory(prefix="ai-drama-p2-vlm-") as temp_name:
            temp_dir = Path(temp_name)
            manifest_path = temp_dir / "manifest.json"
            output_path = temp_dir / "output.jsonl"
            self._write_json(
                manifest_path,
                {
                    "schema_version": VLM_SEMANTIC_SCHEMA,
                    "model": config.model_name,
                    "source_language": config.source_language,
                    "shots": [
                        {
                            "revision_item_id": shot.revision_item_id,
                            "ordinal": shot.ordinal,
                            "reference_clip_path": shot.reference_clip_path,
                            "duration_us": shot.duration_us,
                        }
                        for shot in shots
                    ],
                },
            )
            command = [
                str(config.python_executable),
                str(config.runner_script),
                "--model-path", str(config.model_path),
                "--manifest", str(manifest_path),
                "--output", str(output_path),
                "--device", config.device,
                "--fps", str(config.video_fps),
                "--max-new-tokens", str(config.max_new_tokens),
                "--max-pixels", str(config.max_pixels),
            ]
            subprocess.run(
                command,
                check=True,
                cwd=str(config.runner_script.parent),
                env=self._subprocess_env(config),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=VLM_TIMEOUT_SECONDS,
            )
            if not output_path.is_file():
                raise RuntimeError("P2 VLM runner produced no output")
            records: list[Mapping[str, Any]] = []
            for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if isinstance(value, Mapping):
                    records.append(value)
            return tuple(records)

    def _normalize_scene(self, value: Any) -> dict[str, Any]:
        source = value if isinstance(value, Mapping) else {}
        result: dict[str, Any] = {}
        for key in ("location_hint", "time_of_day", "environment_description"):
            text = self._clean_text(source.get(key), max_len=1200)
            if text:
                result[key] = text
        result["interior_exterior"] = self._enum(
            source.get("interior_exterior"), _ALLOWED_INTERIOR_EXTERIOR, "UNKNOWN"
        )
        return result

    def _normalize_shot(self, value: Any) -> dict[str, Any]:
        source = value if isinstance(value, Mapping) else {}
        result: dict[str, Any] = {}
        for key in (
            "summary",
            "visual_description",
            "shot_type_hint",
            "camera_angle_hint",
            "camera_motion_hint",
            "lighting_hint",
            "continuity_hint",
            "narrative_function_hint",
            "composition_hint",
        ):
            text = self._clean_text(source.get(key), max_len=1800)
            if text:
                result[key] = text
        return result

    def _normalize_subjects(self, value: Any) -> tuple[dict[str, Any], ...]:
        if not isinstance(value, list):
            return ()
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in value[:12]:
            if not isinstance(raw, Mapping):
                continue
            label = self._subject_label(raw.get("label"))
            if not label or label in seen:
                continue
            seen.add(label)
            item: dict[str, Any] = {"label": label}
            for key in (
                "appearance_summary",
                "activity_summary",
                "expression_summary",
                "posture_summary",
                "gaze_summary",
                "interaction_summary",
                "screen_position",
            ):
                text = self._clean_text(raw.get(key), max_len=1000)
                if text:
                    item[key] = text
            item["visibility"] = self._enum(raw.get("visibility"), _ALLOWED_VISIBILITY, "UNKNOWN")
            item["speaking_state"] = self._enum(
                raw.get("speaking_state"), _ALLOWED_SPEAKING_STATE, "UNKNOWN"
            )
            normalized.append(item)
        return tuple(normalized)

    def _normalize_events(self, value: Any, subject_labels: frozenset[str]) -> tuple[dict[str, Any], ...]:
        if not isinstance(value, list):
            return ()
        normalized: list[dict[str, Any]] = []
        for raw in value[:24]:
            if not isinstance(raw, Mapping):
                continue
            content = self._clean_text(raw.get("content"), max_len=1400)
            event_type = self._enum(raw.get("event_type"), _ALLOWED_EVENT_TYPES)
            if not content or not event_type:
                continue
            start = self._ratio(raw.get("start_ratio"))
            end = self._ratio(raw.get("end_ratio"))
            if start is None or end is None:
                start, end = 0.0, 1.0
            if end < start:
                start, end = end, start
            labels: list[str] = []
            raw_labels = raw.get("subject_labels")
            if isinstance(raw_labels, list):
                for candidate in raw_labels:
                    label = self._subject_label(candidate)
                    if label and label in subject_labels and label not in labels:
                        labels.append(label)
            normalized.append({
                "event_type": event_type,
                "start_ratio": start,
                "end_ratio": end,
                "content": content,
                "subject_labels": labels,
            })
        return tuple(normalized)

    def _normalize_props(self, value: Any, subject_labels: frozenset[str]) -> tuple[dict[str, Any], ...]:
        if not isinstance(value, list):
            return ()
        normalized: list[dict[str, Any]] = []
        for raw in value[:16]:
            if not isinstance(raw, Mapping):
                continue
            label = self._clean_text(raw.get("label"), max_len=160)
            if not label:
                continue
            item: dict[str, Any] = {
                "label": label,
                "importance": self._enum(raw.get("importance"), _ALLOWED_PROP_IMPORTANCE, "MEDIUM"),
            }
            reason = self._clean_text(raw.get("narrative_reason"), max_len=1000)
            if reason:
                item["narrative_reason"] = reason
            labels: list[str] = []
            raw_labels = raw.get("subject_labels")
            if isinstance(raw_labels, list):
                for candidate in raw_labels:
                    subject = self._subject_label(candidate)
                    if subject and subject in subject_labels and subject not in labels:
                        labels.append(subject)
            item["subject_labels"] = labels
            normalized.append(item)
        return tuple(normalized)

    def _normalize_semantic(self, raw: Any) -> dict[str, Any] | None:
        """把模型任意 JSON 压到匿名白名单，未知键（含 Final business IDs）全部丢弃。"""

        if not isinstance(raw, Mapping):
            return None
        source = raw.get("semantic") if isinstance(raw.get("semantic"), Mapping) else raw
        if not isinstance(source, Mapping):
            return None
        subjects = self._normalize_subjects(source.get("subjects"))
        labels = frozenset(item["label"] for item in subjects)
        normalized = {
            "schema_version": VLM_SEMANTIC_SCHEMA,
            "scene": self._normalize_scene(source.get("scene")),
            "shot": self._normalize_shot(source.get("shot")),
            "subjects": list(subjects),
            "events": list(self._normalize_events(source.get("events"), labels)),
            "props": list(self._normalize_props(source.get("props"), labels)),
        }
        # 至少必须有可消费的视觉语义，不能因为只返回空壳 JSON 就标 READY。
        if not any((
            normalized["shot"],
            normalized["subjects"],
            normalized["events"],
            normalized["props"],
            any(value for key, value in normalized["scene"].items() if key != "interior_exterior"),
            normalized["scene"].get("interior_exterior") != "UNKNOWN",
        )):
            return None
        return normalized

    def _metadata(
        self,
        *,
        config: VLMRuntimeConfig,
        shot_count: int,
        available_count: int,
        analyzed_count: int,
        semantic_count: int,
        failed_count: int,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "semantic_schema": VLM_SEMANTIC_SCHEMA,
            "model_family": "Qwen3-VL",
            "device_requested": config.device,
            "video_fps": config.video_fps,
            "max_new_tokens": config.max_new_tokens,
            "max_pixels": config.max_pixels,
            "shot_count": shot_count,
            "available_reference_clip_count": available_count,
            "missing_reference_clip_count": shot_count - available_count,
            "shots_analyzed": analyzed_count,
            "semantic_output_count": semantic_count,
            "shot_failure_count": failed_count,
            "confidence_policy": "provider-output-unscored",
            "source_language": config.source_language,
            "runtime_isolated": True,
        }
        if error_type:
            metadata["error_type"] = error_type
        return metadata

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        config = self._runtime_config(context.source_language)
        available_shots = tuple(
            shot for shot in context.shots if Path(shot.reference_clip_path).is_file()
        )
        if not available_shots:
            return p2.P2ProviderResult(
                component="VLM",
                provider=VLM_PROVIDER_NAME,
                model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._metadata(
                    config=config,
                    shot_count=len(context.shots),
                    available_count=0,
                    analyzed_count=0,
                    semantic_count=0,
                    failed_count=0,
                ),
                warnings=("No historical Reference Clip is available for VLM semantics",),
            )

        missing_runtime = self._runtime_missing(config)
        if missing_runtime:
            return p2.P2ProviderResult(
                component="VLM",
                provider=VLM_PROVIDER_NAME,
                model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._metadata(
                    config=config,
                    shot_count=len(context.shots),
                    available_count=len(available_shots),
                    analyzed_count=0,
                    semantic_count=0,
                    failed_count=0,
                ),
                warnings=("P2 VLM runtime is not available: " + ", ".join(missing_runtime),),
            )

        try:
            records = tuple(self._inference_runner(config, available_shots))
        except (ImportError, FileNotFoundError) as exc:
            return p2.P2ProviderResult(
                component="VLM",
                provider=VLM_PROVIDER_NAME,
                model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._metadata(
                    config=config,
                    shot_count=len(context.shots),
                    available_count=len(available_shots),
                    analyzed_count=0,
                    semantic_count=0,
                    failed_count=0,
                    error_type=type(exc).__name__,
                ),
                warnings=("P2 VLM runtime dependency is not available",),
            )
        except Exception as exc:
            return p2.P2ProviderResult(
                component="VLM",
                provider=VLM_PROVIDER_NAME,
                model=self.model_name,
                status="FAILED",
                metadata=self._metadata(
                    config=config,
                    shot_count=len(context.shots),
                    available_count=len(available_shots),
                    analyzed_count=0,
                    semantic_count=0,
                    failed_count=len(available_shots),
                    error_type=type(exc).__name__,
                ),
                warnings=("P2 VLM inference failed",),
            )

        by_revision_item: dict[str, Mapping[str, Any]] = {}
        for record in records:
            revision_item_id = str(record.get("revision_item_id") or "").strip()
            if revision_item_id and revision_item_id not in by_revision_item:
                by_revision_item[revision_item_id] = record

        evidence: list[p2.P2EvidenceRecord] = []
        warnings: list[str] = []
        analyzed_count = 0
        failed_count = 0
        semantic_count = 0

        for shot in available_shots:
            record = by_revision_item.get(shot.revision_item_id)
            if record is None:
                failed_count += 1
                warnings.append(f"Shot {shot.ordinal} VLM output missing")
                continue
            analyzed_count += 1
            if str(record.get("status") or "READY").strip().upper() != "READY":
                failed_count += 1
                warnings.append(f"Shot {shot.ordinal} VLM inference failed")
                continue
            semantic = self._normalize_semantic(record)
            if semantic is None:
                failed_count += 1
                warnings.append(f"Shot {shot.ordinal} VLM semantic JSON is unusable")
                continue
            semantic_count += 1
            summary = self._clean_text(semantic.get("shot", {}).get("summary"), max_len=1200)
            evidence.append(p2.P2EvidenceRecord(
                source_type="VLM_OUTPUT",
                source_id=f"{context.episode_id}:vlm-shot:{shot.ordinal:06d}",
                source_start_us=shot.start_us,
                source_end_us=shot.end_us,
                shot_revision_item_id=shot.revision_item_id,
                text=summary,
                language=context.source_language,
                confidence=None,
                payload={
                    "shot_ordinal": shot.ordinal,
                    "semantic": semantic,
                },
            ))

        if len(available_shots) < len(context.shots):
            warnings.append(
                f"{len(context.shots) - len(available_shots)} historical Reference Clip(s) are missing"
            )

        metadata = self._metadata(
            config=config,
            shot_count=len(context.shots),
            available_count=len(available_shots),
            analyzed_count=analyzed_count,
            semantic_count=semantic_count,
            failed_count=failed_count,
        )
        if evidence:
            return p2.P2ProviderResult(
                component="VLM",
                provider=VLM_PROVIDER_NAME,
                model=self.model_name,
                status="READY",
                evidence=tuple(evidence),
                metadata=metadata,
                warnings=tuple(warnings),
            )
        return p2.P2ProviderResult(
            component="VLM",
            provider=VLM_PROVIDER_NAME,
            model=self.model_name,
            status="FAILED",
            metadata=metadata,
            warnings=tuple(warnings) or ("P2 VLM produced no usable Shot semantics",),
        )


def run_qwen3_vl_semantics(
    run_id: str,
    *,
    provider: Qwen3VLSemanticProvider | None = None,
) -> p2.P2EvidenceArtifact:
    """P2.4 正式入口：执行 Qwen3-VL Shot 语义并交给 P2.1 sidecar 固化 provenance。"""

    return p2.run_local_provider(run_id, provider or Qwen3VLSemanticProvider())
