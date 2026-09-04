"""Fast grounded production VLM for Episode-context Breakdown.

This provider replaces the expensive/ambiguous production pattern
``window full-shot semantics -> text-only per-Shot E3`` with two visual passes that share one
Qwen3-VL process/model load:

1. low-cost overlapping Episode windows produce Scene/anonymous continuity plus temporal camera motion;
2. exact frozen ShotRevisionItems are visually grounded from 1..3 sampled frames per Shot.

The exact-Shot frames are authoritative for visible people, actions, props, framing and visual
prose. Window context may fill conservative Scene context and camera motion only, because motion is
a temporal fact that static sampled images cannot reliably establish. This prevents a nearby person
from leaking into an insert/close-up while keeping the Episode continuity needed by E4.

The frozen P2 sidecar contract stays unchanged: one exact-Shot ``VLM_OUTPUT`` per frozen
ShotRevisionItem. ``LocalSubject != Character`` and all Final Asset gates remain untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Mapping, Sequence

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_episode_v2 as e2
from engine.app import breakdown_p2_vlm_v1 as legacy

FAST_GROUNDED_SCHEMA = "breakdown-p2-vlm-fast-grounded-v1"
FAST_GROUNDED_PROFILE = "breakdown-p2-vlm-fast-grounded-v1"
WINDOW_CONTEXT_PROFILE = "breakdown-p2-vlm-window-context-fast-v1"
EXACT_SHOT_GROUNDING_PROFILE = "breakdown-p2-vlm-exact-shot-frame-grounding-v1"
VISUAL_TRUTH_POLICY = "exact-shot-frames-over-window-context-v1"

DEFAULT_WINDOW_SECONDS = 24.0
DEFAULT_WINDOW_OVERLAP_RATIO = 0.25
DEFAULT_WINDOW_CONTEXT_FPS = 1.0
DEFAULT_WINDOW_MAX_PIXELS = 262_144
DEFAULT_WINDOW_CONTEXT_MAX_NEW_TOKENS = 1_600
DEFAULT_EXACT_SHOT_MAX_PIXELS = 524_288
DEFAULT_GROUNDING_MAX_NEW_TOKENS = 4_096
DEFAULT_GROUNDING_BATCH_SIZE = 5

_ALLOWED_SCENE_CONTINUITY = frozenset({"SAME", "NEW_SCENE", "UNCERTAIN"})
_ALLOWED_SCENE_BASIS = frozenset({"DIRECT", "CONTEXT", "MIXED", "UNCERTAIN"})
_ALLOWED_HINT_CONFIDENCE = frozenset({"LOW", "MEDIUM", "HIGH"})

UnifiedInferenceRunner = Callable[
    [legacy.VLMRuntimeConfig, Path, Sequence[e2.EpisodeVLMWindow]],
    Sequence[Mapping[str, Any]],
]


@dataclass(frozen=True)
class GroundingFramePlan:
    revision_item_id: str
    ordinal: int
    ratios: tuple[float, ...]


def frame_sample_ratios(duration_us: int) -> tuple[float, ...]:
    """Small deterministic visual sample for one exact Shot.

    Very short inserts only need the middle frame. Medium shots get two separated observations;
    longer shots get three. The goal is visual grounding, not replaying the whole clip through VLM.
    """

    seconds = max(0.0, float(duration_us) / 1_000_000.0)
    if seconds < 1.2:
        return (0.50,)
    if seconds <= 3.0:
        return (0.25, 0.75)
    return (0.15, 0.50, 0.85)


def _clean_text(value: Any, *, max_len: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text[:max_len] if text else None


def _normalize_ordinals(value: Any, *, valid: set[int]) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for raw in value:
        try:
            ordinal = int(raw)
        except (TypeError, ValueError):
            continue
        if ordinal in valid and ordinal not in result:
            result.append(ordinal)
    return result


def _normalize_members(
    value: Any,
    *,
    by_ordinal: Mapping[int, str],
    by_id: Mapping[str, int],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value[:48]:
        if not isinstance(raw, Mapping):
            continue
        item_id = str(raw.get("revision_item_id") or "").strip()
        ordinal_raw = raw.get("ordinal")
        try:
            ordinal = int(ordinal_raw) if ordinal_raw is not None else None
        except (TypeError, ValueError):
            ordinal = None
        if item_id and item_id in by_id:
            ordinal = by_id[item_id]
        elif ordinal is not None and ordinal in by_ordinal:
            item_id = by_ordinal[ordinal]
        else:
            continue
        label = str(raw.get("label") or "").strip()
        if not label:
            continue
        marker = (item_id, label)
        if marker in seen:
            continue
        seen.add(marker)
        result.append({
            "revision_item_id": item_id,
            "ordinal": int(ordinal),
            "label": label,
        })
    return result


def _normalize_subject_hints(raw: Any, window: e2.EpisodeVLMWindow) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    by_ordinal = {int(shot.ordinal): str(shot.revision_item_id) for shot in window.shots}
    by_id = {str(shot.revision_item_id): int(shot.ordinal) for shot in window.shots}
    valid = set(by_ordinal)
    result: list[dict[str, Any]] = []
    for item in raw[:32]:
        if not isinstance(item, Mapping):
            continue
        appearance = _clean_text(item.get("appearance_summary"), max_len=1200)
        continuity = _clean_text(item.get("continuity_summary"), max_len=1200)
        members = _normalize_members(item.get("members"), by_ordinal=by_ordinal, by_id=by_id)
        ordinals = _normalize_ordinals(item.get("shot_ordinals"), valid=valid)
        for member in members:
            ordinal = int(member["ordinal"])
            if ordinal not in ordinals:
                ordinals.append(ordinal)
        if (appearance or continuity) and (len(ordinals) >= 2 or len(members) >= 2):
            result.append({
                "appearance_summary": appearance,
                "continuity_summary": continuity,
                "shot_ordinals": sorted(ordinals),
                "members": members,
            })
    return result


def _normalize_prop_hints(raw: Any, window: e2.EpisodeVLMWindow) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    valid = {int(shot.ordinal) for shot in window.shots}
    result: list[dict[str, Any]] = []
    for item in raw[:32]:
        if not isinstance(item, Mapping):
            continue
        label = _clean_text(item.get("label"), max_len=255)
        continuity = _clean_text(item.get("continuity_summary"), max_len=1200)
        ordinals = _normalize_ordinals(item.get("shot_ordinals"), valid=valid)
        if label and len(ordinals) >= 2:
            result.append({
                "label": label,
                "continuity_summary": continuity,
                "shot_ordinals": sorted(ordinals),
            })
    return result


def _weak_scene_value(value: Any) -> bool:
    key = "".join(ch.lower() for ch in str(value or "").strip() if ch.isalnum())
    return key in {"", "unknown", "未知", "不明", "室内", "室外", "内景", "外景", "房间", "room"}


def _scene_context_merge(
    grounded_semantic: Mapping[str, Any],
    scene_hint: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Inherit only Scene context and temporal camera motion; keep all other visible facts exact-Shot."""

    result = {
        "scene": dict(grounded_semantic.get("scene") or {}),
        "shot": dict(grounded_semantic.get("shot") or {}),
        "subjects": [dict(item) for item in grounded_semantic.get("subjects", []) if isinstance(item, Mapping)],
        "events": [dict(item) for item in grounded_semantic.get("events", []) if isinstance(item, Mapping)],
        "props": [dict(item) for item in grounded_semantic.get("props", []) if isinstance(item, Mapping)],
    }
    if not isinstance(scene_hint, Mapping):
        return result
    context_scene = scene_hint.get("scene") if isinstance(scene_hint.get("scene"), Mapping) else {}
    scene = result["scene"]
    if _weak_scene_value(scene.get("location_hint")) and not _weak_scene_value(context_scene.get("location_hint")):
        scene["location_hint"] = context_scene.get("location_hint")
    current_ie = str(scene.get("interior_exterior") or "UNKNOWN").strip().upper()
    context_ie = str(context_scene.get("interior_exterior") or "UNKNOWN").strip().upper()
    if current_ie not in {"INT", "EXT", "MIXED"} and context_ie in {"INT", "EXT", "MIXED"}:
        scene["interior_exterior"] = context_ie
    if _weak_scene_value(scene.get("time_of_day")) and not _weak_scene_value(context_scene.get("time_of_day")):
        scene["time_of_day"] = context_scene.get("time_of_day")
    if not _clean_text(scene.get("environment_description"), max_len=1200):
        inherited = _clean_text(context_scene.get("environment_description"), max_len=1200)
        if inherited:
            scene["environment_description"] = inherited

    shot = result["shot"]
    current_motion = _clean_text(shot.get("camera_motion_hint"), max_len=64)
    context_motion = _clean_text(scene_hint.get("camera_motion_hint"), max_len=64)
    if (not current_motion or current_motion.upper() == "UNKNOWN") and context_motion:
        shot["camera_motion_hint"] = context_motion
    return result


class Qwen3VLSemanticProvider(e2.Qwen3VLSemanticProvider):
    """Production visual provider: cheap context windows + exact-Shot frame grounding."""

    def __init__(
        self,
        *args: Any,
        grounding_batch_size: int | None = None,
        exact_shot_max_pixels: int | None = None,
        grounding_max_new_tokens: int | None = None,
        unified_inference_runner: UnifiedInferenceRunner | None = None,
        **kwargs: Any,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        if kwargs.get("runner_script") is None:
            kwargs["runner_script"] = str(repo_root / "scripts" / "run_breakdown_vlm_fast_grounded_qwen3.py")
        if kwargs.get("video_fps") is None and not os.getenv("AI_DRAMA_P2_VLM_FPS"):
            kwargs["video_fps"] = DEFAULT_WINDOW_CONTEXT_FPS
        if kwargs.get("max_pixels") is None and not os.getenv("AI_DRAMA_P2_VLM_MAX_PIXELS"):
            kwargs["max_pixels"] = DEFAULT_WINDOW_MAX_PIXELS
        if kwargs.get("max_new_tokens") is None and not os.getenv("AI_DRAMA_P2_VLM_MAX_NEW_TOKENS"):
            kwargs["max_new_tokens"] = DEFAULT_WINDOW_CONTEXT_MAX_NEW_TOKENS
        if kwargs.get("window_duration_seconds") is None:
            kwargs["window_duration_seconds"] = float(
                os.getenv("AI_DRAMA_P2_VLM_WINDOW_SECONDS") or DEFAULT_WINDOW_SECONDS
            )
        if kwargs.get("window_overlap_ratio") is None:
            kwargs["window_overlap_ratio"] = float(
                os.getenv("AI_DRAMA_P2_VLM_WINDOW_OVERLAP_RATIO") or DEFAULT_WINDOW_OVERLAP_RATIO
            )
        super().__init__(*args, **kwargs)
        self.grounding_batch_size = int(
            grounding_batch_size
            if grounding_batch_size is not None
            else os.getenv("AI_DRAMA_P2_VLM_GROUNDING_BATCH_SIZE") or DEFAULT_GROUNDING_BATCH_SIZE
        )
        self.exact_shot_max_pixels = int(
            exact_shot_max_pixels
            if exact_shot_max_pixels is not None
            else os.getenv("AI_DRAMA_P2_VLM_EXACT_SHOT_MAX_PIXELS") or DEFAULT_EXACT_SHOT_MAX_PIXELS
        )
        self.grounding_max_new_tokens = int(
            grounding_max_new_tokens
            if grounding_max_new_tokens is not None
            else os.getenv("AI_DRAMA_P2_VLM_GROUNDING_MAX_NEW_TOKENS") or DEFAULT_GROUNDING_MAX_NEW_TOKENS
        )
        if not 1 <= self.grounding_batch_size <= 12:
            raise ValueError("P2 fast-grounded batch size 必须在 1..12")
        if self.exact_shot_max_pixels < 16 * 16:
            raise ValueError("P2 exact-Shot max_pixels 太小")
        if self.grounding_max_new_tokens < 256:
            raise ValueError("P2 exact-Shot grounding max_new_tokens 太小")
        self._unified_inference_runner = unified_inference_runner or self._run_unified_subprocess
        self._uses_production_runner = unified_inference_runner is None
        self._fast_subprocess_failure_detail: str | None = None

    def _normalize_window_summary(
        self,
        raw: Mapping[str, Any],
        window: e2.EpisodeVLMWindow,
    ) -> dict[str, Any]:
        normalized = dict(super()._normalize_window_summary(raw, window))
        normalized["subject_continuity_hints"] = _normalize_subject_hints(
            raw.get("subject_continuity_hints"), window
        )
        normalized["prop_continuity_hints"] = _normalize_prop_hints(
            raw.get("prop_continuity_hints"), window
        )
        expected_by_id = {shot.revision_item_id: shot for shot in window.shots}
        expected_by_ordinal = {shot.ordinal: shot for shot in window.shots}
        hints: list[dict[str, Any]] = []
        raw_hints = raw.get("shot_scene_hints")
        if isinstance(raw_hints, list):
            for item in raw_hints[:64]:
                if not isinstance(item, Mapping):
                    continue
                item_id = str(item.get("revision_item_id") or "").strip()
                try:
                    ordinal = int(item.get("ordinal") or 0)
                except (TypeError, ValueError):
                    ordinal = 0
                shot = expected_by_id.get(item_id) if item_id else expected_by_ordinal.get(ordinal)
                if shot is None:
                    continue
                continuity = str(item.get("scene_continuity") or "UNCERTAIN").strip().upper()
                basis = str(item.get("scene_basis") or "UNCERTAIN").strip().upper()
                raw_scene = item.get("scene") if isinstance(item.get("scene"), Mapping) else {}
                hints.append({
                    "revision_item_id": shot.revision_item_id,
                    "ordinal": shot.ordinal,
                    "scene_continuity": continuity if continuity in _ALLOWED_SCENE_CONTINUITY else "UNCERTAIN",
                    "scene_basis": basis if basis in _ALLOWED_SCENE_BASIS else "UNCERTAIN",
                    "context_note": _clean_text(item.get("context_note"), max_len=700),
                    "camera_motion_hint": _clean_text(item.get("camera_motion_hint"), max_len=64) or "UNKNOWN",
                    "scene": {
                        "location_hint": _clean_text(raw_scene.get("location_hint"), max_len=255),
                        "interior_exterior": str(raw_scene.get("interior_exterior") or "UNKNOWN").strip().upper(),
                        "time_of_day": _clean_text(raw_scene.get("time_of_day"), max_len=64),
                        "environment_description": _clean_text(raw_scene.get("environment_description"), max_len=1200),
                    },
                })
        normalized["shot_scene_hints"] = hints
        normalized["window_context_profile"] = WINDOW_CONTEXT_PROFILE
        return normalized

    @staticmethod
    def _unique_shots(windows: Sequence[e2.EpisodeVLMWindow]) -> tuple[p2.P2ShotInput, ...]:
        by_id: dict[str, p2.P2ShotInput] = {}
        for window in windows:
            for shot in window.shots:
                by_id.setdefault(shot.revision_item_id, shot)
        return tuple(sorted(by_id.values(), key=lambda item: item.ordinal))

    def _materialize_grounding_frames(
        self,
        shot: p2.P2ShotInput,
        output_dir: Path,
    ) -> list[dict[str, Any]]:
        ratios = frame_sample_ratios(shot.duration_us)
        clip = Path(shot.reference_clip_path)
        if not clip.is_file():
            thumbnail = Path(shot.thumbnail_path) if shot.thumbnail_path else None
            if thumbnail is not None and thumbnail.is_file():
                return [{"ratio": 0.5, "path": str(thumbnail)}]
            raise FileNotFoundError(f"Shot {shot.ordinal} Reference Clip / thumbnail missing")

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg is required for exact-Shot grounding frames")
        duration_s = max(0.001, shot.duration_us / 1_000_000.0)
        rows: list[dict[str, Any]] = []
        for index, ratio in enumerate(ratios, start=1):
            frame_path = output_dir / f"shot-{shot.ordinal:06d}-frame-{index}.jpg"
            offset = min(max(0.0, duration_s * float(ratio)), max(0.0, duration_s - 0.01))
            command = [
                ffmpeg, "-y", "-ss", f"{offset:.6f}", "-i", str(clip),
                "-frames:v", "1", "-q:v", "2", str(frame_path),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                )
            except subprocess.CalledProcessError as exc:
                detail = self._clean_subprocess_output(exc.stdout or exc.output)
                raise RuntimeError(
                    f"ffmpeg exact-Shot frame failed for Shot {shot.ordinal}"
                    + (f": {detail}" if detail else "")
                ) from exc
            if not frame_path.is_file() or frame_path.stat().st_size <= 0:
                raise RuntimeError(f"Shot {shot.ordinal} grounding frame is empty")
            rows.append({"ratio": float(ratio), "path": str(frame_path)})
        return rows

    def _run_unified_subprocess(
        self,
        config: legacy.VLMRuntimeConfig,
        video_path: Path,
        windows: Sequence[e2.EpisodeVLMWindow],
    ) -> Sequence[Mapping[str, Any]]:
        with tempfile.TemporaryDirectory(prefix="ai-drama-p2-fast-grounded-") as temp_name:
            root = Path(temp_name)
            window_dir = root / "windows"
            frame_dir = root / "frames"
            window_dir.mkdir(parents=True, exist_ok=True)
            frame_dir.mkdir(parents=True, exist_ok=True)
            window_payloads: list[dict[str, Any]] = []
            for window in windows:
                clip = window_dir / f"{window.window_id}.mp4"
                self._materialize_window(video_path, window, clip)
                window_payloads.append(self._window_manifest(window, clip))

            grounding_payloads: list[dict[str, Any]] = []
            for shot in self._unique_shots(windows):
                grounding_payloads.append({
                    "revision_item_id": shot.revision_item_id,
                    "ordinal": shot.ordinal,
                    "source_start_us": shot.start_us,
                    "source_end_us": shot.end_us,
                    "frames": self._materialize_grounding_frames(shot, frame_dir),
                })

            manifest_path = root / "manifest.json"
            output_path = root / "output.jsonl"
            manifest_path.write_text(json.dumps({
                "schema_version": FAST_GROUNDED_SCHEMA,
                "profile": FAST_GROUNDED_PROFILE,
                "model": config.model_name,
                "source_language": config.source_language,
                "windows": window_payloads,
                "grounding_shots": grounding_payloads,
            }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            command = [
                str(config.python_executable), str(config.runner_script),
                "--model-path", str(config.model_path),
                "--manifest", str(manifest_path),
                "--output", str(output_path),
                "--device", config.device,
                "--window-fps", str(config.video_fps),
                "--window-max-pixels", str(config.max_pixels),
                "--window-max-new-tokens", str(config.max_new_tokens),
                "--grounding-max-pixels", str(self.exact_shot_max_pixels),
                "--grounding-max-new-tokens", str(self.grounding_max_new_tokens),
                "--grounding-batch-size", str(self.grounding_batch_size),
            ]
            try:
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
                    timeout=legacy.VLM_TIMEOUT_SECONDS,
                )
            except subprocess.CalledProcessError as exc:
                self._fast_subprocess_failure_detail = self._clean_subprocess_output(exc.stdout or exc.output)
                raise
            if not output_path.is_file():
                raise RuntimeError("fast-grounded VLM runner produced no output")
            rows: list[Mapping[str, Any]] = []
            for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if isinstance(value, Mapping):
                    rows.append(value)
            return tuple(rows)

    @staticmethod
    def _scene_hint_for_shot(
        shot: p2.P2ShotInput,
        windows: Sequence[e2.EpisodeVLMWindow],
        summaries: Mapping[str, Mapping[str, Any]],
    ) -> tuple[e2.EpisodeVLMWindow | None, Mapping[str, Any] | None]:
        candidates = [window for window in windows if any(item.revision_item_id == shot.revision_item_id for item in window.shots)]
        candidates.sort(key=lambda window: e2._candidate_rank(window, shot), reverse=True)
        for window in candidates:
            summary = summaries.get(window.window_id)
            if not isinstance(summary, Mapping):
                continue
            raw_hints = summary.get("shot_scene_hints")
            if not isinstance(raw_hints, list):
                continue
            for hint in raw_hints:
                if not isinstance(hint, Mapping):
                    continue
                if str(hint.get("revision_item_id") or "") == shot.revision_item_id:
                    return window, hint
        return (candidates[0], None) if candidates else (None, None)

    def _metadata(
        self,
        *,
        config: legacy.VLMRuntimeConfig,
        video_kind: str,
        windows: Sequence[e2.EpisodeVLMWindow],
        window_summaries: Sequence[Mapping[str, Any]],
        shot_count: int,
        grounding_count: int,
        failed_window_count: int,
        failed_grounding_count: int,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        result = {
            "semantic_schema": legacy.VLM_SEMANTIC_SCHEMA,
            "fast_grounded_schema": FAST_GROUNDED_SCHEMA,
            "episode_context_profile": WINDOW_CONTEXT_PROFILE,
            "exact_shot_grounding_profile": EXACT_SHOT_GROUNDING_PROFILE,
            "production_vlm_profile": FAST_GROUNDED_PROFILE,
            "visual_truth_policy": VISUAL_TRUTH_POLICY,
            "inference_mode": "single-model-load-window-context-plus-exact-shot-frames",
            "window_target_seconds": self.window_duration_seconds,
            "window_overlap_ratio": self.window_overlap_ratio,
            "window_count": len(windows),
            "window_summaries": [dict(item) for item in window_summaries],
            "window_video_fps": config.video_fps,
            "window_max_pixels": config.max_pixels,
            "window_max_new_tokens": config.max_new_tokens,
            "exact_shot_max_pixels": self.exact_shot_max_pixels,
            "grounding_max_new_tokens": self.grounding_max_new_tokens,
            "grounding_batch_size": self.grounding_batch_size,
            "model_family": "Qwen3-VL",
            "model_load_policy": "one-run-one-vlm-process-one-model-load",
            "episode_video_kind": video_kind,
            "device_requested": config.device,
            "shot_count": shot_count,
            "semantic_output_count": grounding_count,
            "missing_shot_semantic_count": shot_count - grounding_count,
            "failed_window_count": failed_window_count,
            "failed_grounding_count": failed_grounding_count,
            "source_language": config.source_language,
            "runtime_isolated": True,
        }
        if error_type:
            result["error_type"] = error_type
        if self._fast_subprocess_failure_detail:
            result["subprocess_failure_detail"] = self._fast_subprocess_failure_detail
        return result

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        self._fast_subprocess_failure_detail = None
        config = self._runtime_config(context.source_language)
        windows = e2._plan_windows(
            context.shots,
            target_duration_us=int(round(self.window_duration_seconds * 1_000_000)),
            overlap_ratio=self.window_overlap_ratio,
        )
        video_path, video_kind = self._resolve_episode_video(context)
        if video_path is None:
            return p2.P2ProviderResult(
                component="VLM", provider=legacy.VLM_PROVIDER_NAME, model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._metadata(
                    config=config, video_kind=video_kind, windows=windows, window_summaries=(),
                    shot_count=len(context.shots), grounding_count=0,
                    failed_window_count=0, failed_grounding_count=len(context.shots),
                ),
                warnings=("fast-grounded Episode proxy/source video is not available",),
            )
        missing_runtime = self._runtime_missing(config)
        if missing_runtime:
            return p2.P2ProviderResult(
                component="VLM", provider=legacy.VLM_PROVIDER_NAME, model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._metadata(
                    config=config, video_kind=video_kind, windows=windows, window_summaries=(),
                    shot_count=len(context.shots), grounding_count=0,
                    failed_window_count=0, failed_grounding_count=len(context.shots),
                ),
                warnings=("fast-grounded VLM runtime is not available: " + ", ".join(missing_runtime),),
            )
        try:
            records = tuple(self._unified_inference_runner(config, video_path, windows))
        except (ImportError, FileNotFoundError) as exc:
            return p2.P2ProviderResult(
                component="VLM", provider=legacy.VLM_PROVIDER_NAME, model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._metadata(
                    config=config, video_kind=video_kind, windows=windows, window_summaries=(),
                    shot_count=len(context.shots), grounding_count=0,
                    failed_window_count=len(windows), failed_grounding_count=len(context.shots),
                    error_type=type(exc).__name__,
                ),
                warnings=("fast-grounded VLM runtime dependency is not available",),
            )
        except Exception as exc:
            detail = self._fast_subprocess_failure_detail
            warning = "P2 fast-grounded VLM inference failed"
            if detail:
                warning += f": {detail}"
            return p2.P2ProviderResult(
                component="VLM", provider=legacy.VLM_PROVIDER_NAME, model=self.model_name,
                status="FAILED",
                metadata=self._metadata(
                    config=config, video_kind=video_kind, windows=windows, window_summaries=(),
                    shot_count=len(context.shots), grounding_count=0,
                    failed_window_count=len(windows), failed_grounding_count=len(context.shots),
                    error_type=type(exc).__name__,
                ),
                warnings=(warning,),
            )

        window_records: dict[str, Mapping[str, Any]] = {}
        grounding_records: dict[str, Mapping[str, Any]] = {}
        warnings: list[str] = []
        failed_windows = 0
        failed_groundings = 0
        for record in records:
            kind = str(record.get("kind") or "").strip().lower()
            status = str(record.get("status") or "FAILED").strip().upper()
            if kind == "window_context":
                window_id = str(record.get("window_id") or "").strip()
                if window_id and status == "READY" and window_id not in window_records:
                    window_records[window_id] = record
                elif window_id:
                    failed_windows += 1
                    warnings.append(f"{window_id} context failed")
            elif kind == "shot_grounding":
                item_id = str(record.get("revision_item_id") or "").strip()
                if item_id and status == "READY" and item_id not in grounding_records:
                    grounding_records[item_id] = record
                elif item_id:
                    failed_groundings += 1
                    warnings.append(f"exact-Shot grounding failed: {item_id}")

        window_summaries: list[dict[str, Any]] = []
        summaries_by_id: dict[str, Mapping[str, Any]] = {}
        windows_by_id = {window.window_id: window for window in windows}
        for window_id, record in window_records.items():
            window = windows_by_id.get(window_id)
            raw = record.get("semantic") if isinstance(record.get("semantic"), Mapping) else None
            if window is None or raw is None:
                continue
            normalized = self._normalize_window_summary(raw, window)
            window_summaries.append(normalized)
            summaries_by_id[window_id] = normalized

        evidence: list[p2.P2EvidenceRecord] = []
        for shot in context.shots:
            record = grounding_records.get(shot.revision_item_id)
            raw_semantic = record.get("semantic") if isinstance(record, Mapping) and isinstance(record.get("semantic"), Mapping) else None
            semantic = self._normalize_semantic(raw_semantic) if raw_semantic is not None else None
            if semantic is None:
                continue
            selected_window, scene_hint = self._scene_hint_for_shot(
                shot, windows, summaries_by_id
            )
            grounded = _scene_context_merge(semantic, scene_hint)
            frame_ratios = frame_sample_ratios(shot.duration_us)
            episode_window: dict[str, Any] = {
                "profile": WINDOW_CONTEXT_PROFILE,
                "window_id": selected_window.window_id if selected_window else None,
                "window_start_us": selected_window.start_us if selected_window else None,
                "window_end_us": selected_window.end_us if selected_window else None,
                "scene_continuity": str((scene_hint or {}).get("scene_continuity") or "UNCERTAIN"),
                "scene_basis": str((scene_hint or {}).get("scene_basis") or "UNCERTAIN"),
                "context_note": (scene_hint or {}).get("context_note"),
                "camera_motion_hint": (scene_hint or {}).get("camera_motion_hint"),
            }
            evidence.append(p2.P2EvidenceRecord(
                source_type="VLM_OUTPUT",
                source_id=f"{context.episode_id}:vlm-grounded-shot:{shot.ordinal:06d}",
                source_start_us=shot.start_us,
                source_end_us=shot.end_us,
                shot_revision_item_id=shot.revision_item_id,
                text=_clean_text((grounded.get("shot") or {}).get("summary"), max_len=1200),
                language=context.source_language,
                confidence=None,
                payload={
                    "shot_ordinal": shot.ordinal,
                    "semantic": grounded,
                    "exact_shot_semantic": semantic,
                    "episode_window": episode_window,
                    "exact_shot_grounding": {
                        "profile": EXACT_SHOT_GROUNDING_PROFILE,
                        "visual_truth_policy": VISUAL_TRUTH_POLICY,
                        "frame_sample_ratios": list(frame_ratios),
                        "frame_count": len(frame_ratios),
                        "visible_fact_source": "exact_frozen_shot_frames",
                        "window_context_allowed_for": ["scene", "shot.camera_motion_hint"],
                        "window_context_forbidden_for": [
                            "shot.visual_description", "subjects", "events", "props",
                            "shot.shot_type_hint", "shot.camera_angle_hint", "shot.composition_hint",
                            "shot.lighting_hint",
                        ],
                    },
                },
            ))

        missing = len(context.shots) - len(evidence)
        metadata = self._metadata(
            config=config,
            video_kind=video_kind,
            windows=windows,
            window_summaries=window_summaries,
            shot_count=len(context.shots),
            grounding_count=len(evidence),
            failed_window_count=max(failed_windows, len(windows) - len(window_summaries)),
            failed_grounding_count=max(failed_groundings, missing),
        )
        if missing:
            warnings.append(f"exact-Shot grounding coverage incomplete: missing={missing}")
            return p2.P2ProviderResult(
                component="VLM", provider=legacy.VLM_PROVIDER_NAME, model=self.model_name,
                status="FAILED", metadata=metadata,
                warnings=tuple(dict.fromkeys(warnings)),
            )
        if not window_summaries:
            warnings.append("no usable Episode window context was produced")
            return p2.P2ProviderResult(
                component="VLM", provider=legacy.VLM_PROVIDER_NAME, model=self.model_name,
                status="FAILED", metadata=metadata,
                warnings=tuple(dict.fromkeys(warnings)),
            )
        result = p2.P2ProviderResult(
            component="VLM", provider=legacy.VLM_PROVIDER_NAME, model=self.model_name,
            status="READY", evidence=tuple(evidence), metadata=metadata,
            warnings=tuple(dict.fromkeys(warnings)),
        )
        p2.validate_provider_result(context, result)
        return result


def run_qwen3_vl_fast_grounded_semantics(
    run_id: str,
    *,
    provider: Qwen3VLSemanticProvider | None = None,
) -> p2.P2EvidenceArtifact:
    return p2.run_local_provider(run_id, provider or Qwen3VLSemanticProvider())


__all__ = [
    "DEFAULT_EXACT_SHOT_MAX_PIXELS",
    "DEFAULT_GROUNDING_BATCH_SIZE",
    "DEFAULT_GROUNDING_MAX_NEW_TOKENS",
    "DEFAULT_WINDOW_CONTEXT_FPS",
    "DEFAULT_WINDOW_CONTEXT_MAX_NEW_TOKENS",
    "DEFAULT_WINDOW_MAX_PIXELS",
    "DEFAULT_WINDOW_OVERLAP_RATIO",
    "DEFAULT_WINDOW_SECONDS",
    "EXACT_SHOT_GROUNDING_PROFILE",
    "FAST_GROUNDED_PROFILE",
    "FAST_GROUNDED_SCHEMA",
    "GroundingFramePlan",
    "Qwen3VLSemanticProvider",
    "VISUAL_TRUTH_POLICY",
    "WINDOW_CONTEXT_PROFILE",
    "frame_sample_ratios",
    "run_qwen3_vl_fast_grounded_semantics",
]
