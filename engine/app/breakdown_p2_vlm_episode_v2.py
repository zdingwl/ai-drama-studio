"""Breakdown P2-E2: overlapping Episode-window Qwen3-VL provider.

E2 changes the visual context boundary without changing the frozen P2 sidecar contract:
Episode proxy/source -> shot-aligned overlapping windows -> shot-aware Qwen semantics ->
existing exact-shot ``VLM_OUTPUT`` records -> Episode-context E1 Fusion.

Window summaries and continuity hints are provenance/context only. They never create Final
Character/Scene/Prop IDs and historical BreakdownRuns remain immutable.
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

from sqlalchemy import select

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_v1 as legacy
from engine.app import studio_v2

VLM_PROVIDER_NAME = legacy.VLM_PROVIDER_NAME
VLM_SEMANTIC_SCHEMA = legacy.VLM_SEMANTIC_SCHEMA
VLM_WINDOW_SCHEMA = "breakdown-p2-vlm-episode-window-v1"
VLM_EPISODE_WINDOW_PROFILE = "breakdown-p2-vlm-episode-window-e2-v1"
VLM_PROMPT_PROFILE = "breakdown-p2-vlm-episode-window-zh-v1"
VLM_DRAFT_TEXT_LANGUAGE = "zh-CN"
DEFAULT_WINDOW_SECONDS = 24.0
DEFAULT_WINDOW_OVERLAP_RATIO = 0.25
DEFAULT_WINDOW_MAX_NEW_TOKENS = 4096
MIN_WINDOW_SECONDS = 20.0
MAX_WINDOW_SECONDS = 40.0
MIN_WINDOW_OVERLAP_RATIO = 0.10
MAX_WINDOW_OVERLAP_RATIO = 0.50
VLM_TIMEOUT_SECONDS = legacy.VLM_TIMEOUT_SECONDS

_ALLOWED_SCENE_CONTINUITY = frozenset({"SAME", "NEW_SCENE", "UNCERTAIN"})
_ALLOWED_SCENE_BASIS = frozenset({"DIRECT", "CONTEXT", "MIXED", "UNCERTAIN"})
_ALLOWED_HINT_CONFIDENCE = frozenset({"LOW", "MEDIUM", "HIGH"})


@dataclass(frozen=True)
class EpisodeVLMWindow:
    ordinal: int
    start_us: int
    end_us: int
    shots: tuple[p2.P2ShotInput, ...]

    @property
    def window_id(self) -> str:
        return f"window-{self.ordinal:04d}"

    @property
    def duration_us(self) -> int:
        return self.end_us - self.start_us


WindowInferenceRunner = Callable[
    [legacy.VLMRuntimeConfig, Path, Sequence[EpisodeVLMWindow]],
    Sequence[Mapping[str, Any]],
]
EpisodeVideoResolver = Callable[[p2.P2RunContext], tuple[Path | None, str]]


def _plan_windows(
    shots: Sequence[p2.P2ShotInput],
    *,
    target_duration_us: int,
    overlap_ratio: float,
) -> tuple[EpisodeVLMWindow, ...]:
    """Plan ordered, shot-aligned windows while keeping every Shot whole."""

    ordered = tuple(sorted(shots, key=lambda item: (item.start_us, item.ordinal)))
    if not ordered:
        return ()
    target = max(1, int(target_duration_us))
    desired_overlap = int(round(target * float(overlap_ratio)))
    windows: list[EpisodeVLMWindow] = []
    start_index = 0
    while start_index < len(ordered):
        end_index = start_index
        start_us = ordered[start_index].start_us
        while end_index + 1 < len(ordered):
            candidate_end = ordered[end_index + 1].end_us
            if candidate_end - start_us > target and end_index >= start_index:
                break
            end_index += 1
        # A single long Shot is still one valid window even if it exceeds the nominal target.
        selected = ordered[start_index:end_index + 1]
        windows.append(EpisodeVLMWindow(
            ordinal=len(windows) + 1,
            start_us=selected[0].start_us,
            end_us=selected[-1].end_us,
            shots=selected,
        ))
        if end_index >= len(ordered) - 1:
            break
        next_index = end_index + 1
        if desired_overlap > 0:
            threshold = selected[-1].end_us - desired_overlap
            overlap_index = end_index
            while overlap_index > start_index and ordered[overlap_index].start_us > threshold:
                overlap_index -= 1
            if ordered[overlap_index].end_us > threshold:
                next_index = overlap_index
        if next_index <= start_index:
            next_index = start_index + 1
        start_index = next_index
    return tuple(windows)


def _candidate_rank(window: EpisodeVLMWindow, shot: p2.P2ShotInput) -> tuple[int, int, int]:
    left = max(0, shot.start_us - window.start_us)
    right = max(0, window.end_us - shot.end_us)
    margin = min(left, right)
    shot_center = (shot.start_us + shot.end_us) // 2
    window_center = (window.start_us + window.end_us) // 2
    center_distance = abs(shot_center - window_center)
    return margin, -center_distance, -window.ordinal


class Qwen3VLSemanticProvider(legacy.Qwen3VLSemanticProvider):
    """Production E2 provider; emits the legacy per-Shot VLM_OUTPUT contract."""

    def __init__(
        self,
        *args: Any,
        window_duration_seconds: float | None = None,
        window_overlap_ratio: float | None = None,
        window_inference_runner: WindowInferenceRunner | None = None,
        episode_video_resolver: EpisodeVideoResolver | None = None,
        **kwargs: Any,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        if kwargs.get("runner_script") is None:
            kwargs["runner_script"] = str(
                repo_root / "scripts" / "run_breakdown_vlm_qwen3_episode_windows.py"
            )
        if kwargs.get("max_new_tokens") is None and not os.getenv("AI_DRAMA_P2_VLM_MAX_NEW_TOKENS"):
            kwargs["max_new_tokens"] = DEFAULT_WINDOW_MAX_NEW_TOKENS
        super().__init__(*args, **kwargs)

        raw_seconds = window_duration_seconds
        if raw_seconds is None:
            raw_seconds = float(os.getenv("AI_DRAMA_P2_VLM_WINDOW_SECONDS") or DEFAULT_WINDOW_SECONDS)
        raw_overlap = window_overlap_ratio
        if raw_overlap is None:
            raw_overlap = float(
                os.getenv("AI_DRAMA_P2_VLM_WINDOW_OVERLAP_RATIO")
                or DEFAULT_WINDOW_OVERLAP_RATIO
            )
        self.window_duration_seconds = float(raw_seconds)
        self.window_overlap_ratio = float(raw_overlap)
        if not MIN_WINDOW_SECONDS <= self.window_duration_seconds <= MAX_WINDOW_SECONDS:
            raise ValueError("P2-E2 VLM window duration 必须在 20..40 秒")
        if not MIN_WINDOW_OVERLAP_RATIO <= self.window_overlap_ratio <= MAX_WINDOW_OVERLAP_RATIO:
            raise ValueError("P2-E2 VLM window overlap 必须在 0.10..0.50")

        self._window_inference_runner = window_inference_runner or self._run_window_subprocess
        self._episode_video_resolver = episode_video_resolver or self._resolve_episode_video_from_db
        # Inherited runtime checks should be skipped for injected unit-test runners only.
        self._uses_production_runner = window_inference_runner is None
        self._runtime_failure_details: tuple[str, ...] = ()
        self._subprocess_failure_detail: str | None = None

    @staticmethod
    def _clean_failure_detail(record: Mapping[str, Any], *, max_len: int = 900) -> str | None:
        error_type = " ".join(str(record.get("error_type") or "").strip().split())
        detail = " ".join(str(record.get("error_detail") or "").strip().split())
        text = detail or error_type
        if detail and error_type and not detail.startswith(error_type):
            text = f"{error_type}: {detail}"
        return text[:max_len] if text else None

    @staticmethod
    def _clean_subprocess_output(value: Any, *, max_len: int = 1200) -> str | None:
        lines = [
            " ".join(line.strip().split())
            for line in str(value or "").splitlines()
            if line.strip()
        ]
        return " | ".join(lines[-4:])[:max_len] if lines else None

    @staticmethod
    def _resolve_episode_video_from_db(context: p2.P2RunContext) -> tuple[Path | None, str]:
        """Read-only media lookup; frozen P2RunContext remains unchanged."""

        with studio_v2.get_session() as session:
            episode = session.get(studio_v2.Episode, context.episode_id)
            preprocess = session.scalar(
                select(studio_v2.Preprocess).where(
                    studio_v2.Preprocess.episode_id == context.episode_id
                )
            )
            if preprocess is not None and preprocess.status == "READY" and preprocess.proxy_path:
                proxy = Path(preprocess.proxy_path)
                if proxy.is_file():
                    return proxy, "preprocess_proxy"
            if episode is not None and episode.source_path:
                source = Path(episode.source_path)
                if source.is_file():
                    return source, "episode_source"
        return None, "missing"

    def _resolve_episode_video(self, context: p2.P2RunContext) -> tuple[Path | None, str]:
        return self._episode_video_resolver(context)

    @staticmethod
    def _subprocess_env(config: legacy.VLMRuntimeConfig) -> dict[str, str]:
        env = legacy.Qwen3VLSemanticProvider._subprocess_env(config)
        configured = (
            env.get("AI_DRAMA_P2_VLM_VIDEO_READER")
            or env.get("FORCE_QWENVL_VIDEO_READER")
            or ("decord" if os.name == "nt" else "")
        ).strip().lower()
        if configured:
            if configured not in {"decord", "torchcodec", "torchvision"}:
                raise ValueError("P2 VLM video reader 只允许 decord/torchcodec/torchvision")
            env["FORCE_QWENVL_VIDEO_READER"] = configured
        return env

    @staticmethod
    def _window_manifest(window: EpisodeVLMWindow, clip: Path) -> dict[str, Any]:
        return {
            "window_id": window.window_id,
            "ordinal": window.ordinal,
            "source_start_us": window.start_us,
            "source_end_us": window.end_us,
            "video_path": str(clip),
            "shots": [
                {
                    "revision_item_id": shot.revision_item_id,
                    "ordinal": shot.ordinal,
                    "source_start_us": shot.start_us,
                    "source_end_us": shot.end_us,
                    "window_start_seconds": (shot.start_us - window.start_us) / 1_000_000,
                    "window_end_seconds": (shot.end_us - window.start_us) / 1_000_000,
                }
                for shot in window.shots
            ],
        }

    def _materialize_window(
        self,
        video_path: Path,
        window: EpisodeVLMWindow,
        output_path: Path,
    ) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg is required for P2-E2 Episode windows")
        command = [
            ffmpeg, "-y",
            "-ss", f"{window.start_us / 1_000_000:.6f}",
            "-i", str(video_path),
            "-t", f"{window.duration_us / 1_000_000:.6f}",
            "-map", "0:v:0", "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(output_path),
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
                timeout=max(600, int(window.duration_us / 1_000_000) * 30),
            )
        except subprocess.CalledProcessError as exc:
            detail = self._clean_subprocess_output(exc.stdout or exc.output)
            raise RuntimeError(
                f"ffmpeg could not materialize {window.window_id}"
                + (f": {detail}" if detail else "")
            ) from exc
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise RuntimeError(f"ffmpeg produced no usable clip for {window.window_id}")

    def _run_window_subprocess(
        self,
        config: legacy.VLMRuntimeConfig,
        video_path: Path,
        windows: Sequence[EpisodeVLMWindow],
    ) -> Sequence[Mapping[str, Any]]:
        with tempfile.TemporaryDirectory(prefix="ai-drama-p2-vlm-e2-") as temp_name:
            root = Path(temp_name)
            manifest_path = root / "manifest.json"
            output_path = root / "output.jsonl"
            window_payloads: list[dict[str, Any]] = []
            for window in windows:
                clip = root / f"{window.window_id}.mp4"
                self._materialize_window(video_path, window, clip)
                window_payloads.append(self._window_manifest(window, clip))
            manifest_path.write_text(json.dumps({
                "schema_version": VLM_WINDOW_SCHEMA,
                "profile": VLM_EPISODE_WINDOW_PROFILE,
                "model": config.model_name,
                "source_language": config.source_language,
                "windows": window_payloads,
            }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            command = [
                str(config.python_executable), str(config.runner_script),
                "--model-path", str(config.model_path),
                "--manifest", str(manifest_path),
                "--output", str(output_path),
                "--device", config.device,
                "--fps", str(config.video_fps),
                "--max-new-tokens", str(config.max_new_tokens),
                "--max-pixels", str(config.max_pixels),
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
                    timeout=VLM_TIMEOUT_SECONDS,
                )
            except subprocess.CalledProcessError as exc:
                self._subprocess_failure_detail = self._clean_subprocess_output(
                    exc.stdout or exc.output
                )
                raise
            if not output_path.is_file():
                raise RuntimeError("P2-E2 VLM runner produced no output")
            rows: list[Mapping[str, Any]] = []
            for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if isinstance(value, Mapping):
                    rows.append(value)
            return tuple(rows)

    def _normalize_window_summary(
        self,
        raw: Mapping[str, Any],
        window: EpisodeVLMWindow,
    ) -> dict[str, Any]:
        changes: list[dict[str, Any]] = []
        raw_changes = raw.get("scene_change_candidates")
        if isinstance(raw_changes, list):
            for item in raw_changes[:12]:
                if not isinstance(item, Mapping):
                    continue
                try:
                    seconds = float(item.get("at_seconds"))
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(seconds):
                    continue
                seconds = min(window.duration_us / 1_000_000, max(0.0, seconds))
                confidence = str(item.get("confidence") or "LOW").strip().upper()
                changes.append({
                    "source_us": window.start_us + int(round(seconds * 1_000_000)),
                    "confidence": confidence if confidence in _ALLOWED_HINT_CONFIDENCE else "LOW",
                    "description": self._clean_text(item.get("description"), max_len=700),
                })
        return {
            "window_id": window.window_id,
            "source_start_us": window.start_us,
            "source_end_us": window.end_us,
            "shot_ordinals": [shot.ordinal for shot in window.shots],
            "window_summary": self._clean_text(raw.get("window_summary"), max_len=2000),
            "scene_change_candidates": changes,
        }

    def _normalize_shot_context(self, value: Mapping[str, Any]) -> dict[str, Any]:
        continuity = str(value.get("scene_continuity") or "").strip().upper()
        basis = str(value.get("scene_basis") or "").strip().upper()
        return {
            "scene_continuity": continuity if continuity in _ALLOWED_SCENE_CONTINUITY else "UNCERTAIN",
            "scene_basis": basis if basis in _ALLOWED_SCENE_BASIS else "UNCERTAIN",
            "context_note": self._clean_text(value.get("context_note"), max_len=700),
        }

    def _metadata(
        self,
        *,
        config: legacy.VLMRuntimeConfig,
        video_kind: str,
        windows: Sequence[EpisodeVLMWindow],
        window_summaries: Sequence[Mapping[str, Any]],
        shot_count: int,
        semantic_count: int,
        failed_window_count: int,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "semantic_schema": VLM_SEMANTIC_SCHEMA,
            "window_schema": VLM_WINDOW_SCHEMA,
            "episode_context_profile": VLM_EPISODE_WINDOW_PROFILE,
            "prompt_profile": VLM_PROMPT_PROFILE,
            "draft_text_language": VLM_DRAFT_TEXT_LANGUAGE,
            "inference_mode": "shot-aligned-overlapping-episode-windows",
            "window_target_seconds": self.window_duration_seconds,
            "window_overlap_ratio": self.window_overlap_ratio,
            "window_count": len(windows),
            "window_summaries": [dict(item) for item in window_summaries],
            "episode_video_kind": video_kind,
            "model_family": "Qwen3-VL",
            "device_requested": config.device,
            "video_fps": config.video_fps,
            "max_new_tokens": config.max_new_tokens,
            "max_pixels": config.max_pixels,
            "shot_count": shot_count,
            "semantic_output_count": semantic_count,
            "missing_shot_semantic_count": shot_count - semantic_count,
            "failed_window_count": failed_window_count,
            "confidence_policy": "provider-output-unscored",
            "source_language": config.source_language,
            "runtime_isolated": True,
            "shot_selection_policy": "max-surrounding-context-margin-v1",
        }
        if error_type:
            result["error_type"] = error_type
        if self._subprocess_failure_detail:
            result["subprocess_failure_detail"] = self._subprocess_failure_detail
        if self._runtime_failure_details:
            result["window_failure_details"] = list(self._runtime_failure_details)
        return result

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        self._runtime_failure_details = ()
        self._subprocess_failure_detail = None
        config = self._runtime_config(context.source_language)
        windows = _plan_windows(
            context.shots,
            target_duration_us=int(round(self.window_duration_seconds * 1_000_000)),
            overlap_ratio=self.window_overlap_ratio,
        )
        video_path, video_kind = self._resolve_episode_video(context)
        if video_path is None:
            return p2.P2ProviderResult(
                component="VLM", provider=VLM_PROVIDER_NAME, model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._metadata(
                    config=config, video_kind=video_kind, windows=windows,
                    window_summaries=(), shot_count=len(context.shots),
                    semantic_count=0, failed_window_count=0,
                ),
                warnings=("P2-E2 Episode proxy/source video is not available",),
            )

        missing_runtime = self._runtime_missing(config)
        if missing_runtime:
            return p2.P2ProviderResult(
                component="VLM", provider=VLM_PROVIDER_NAME, model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._metadata(
                    config=config, video_kind=video_kind, windows=windows,
                    window_summaries=(), shot_count=len(context.shots),
                    semantic_count=0, failed_window_count=0,
                ),
                warnings=("P2-E2 VLM runtime is not available: " + ", ".join(missing_runtime),),
            )

        try:
            records = tuple(self._window_inference_runner(config, video_path, windows))
        except (ImportError, FileNotFoundError) as exc:
            return p2.P2ProviderResult(
                component="VLM", provider=VLM_PROVIDER_NAME, model=self.model_name,
                status="NOT_AVAILABLE",
                metadata=self._metadata(
                    config=config, video_kind=video_kind, windows=windows,
                    window_summaries=(), shot_count=len(context.shots), semantic_count=0,
                    failed_window_count=len(windows), error_type=type(exc).__name__,
                ),
                warnings=("P2-E2 VLM runtime dependency is not available",),
            )
        except Exception as exc:
            return p2.P2ProviderResult(
                component="VLM", provider=VLM_PROVIDER_NAME, model=self.model_name,
                status="FAILED",
                metadata=self._metadata(
                    config=config, video_kind=video_kind, windows=windows,
                    window_summaries=(), shot_count=len(context.shots), semantic_count=0,
                    failed_window_count=len(windows), error_type=type(exc).__name__,
                ),
                warnings=("P2-E2 VLM inference failed",),
            )

        by_window: dict[str, Mapping[str, Any]] = {}
        for record in records:
            window_id = str(record.get("window_id") or "").strip()
            if window_id and window_id not in by_window:
                by_window[window_id] = record

        candidates: dict[str, list[tuple[tuple[int, int, int], EpisodeVLMWindow, dict[str, Any], dict[str, Any]]]] = {}
        window_summaries: list[dict[str, Any]] = []
        warnings: list[str] = []
        failure_details: list[str] = []
        failed_windows = 0
        for window in windows:
            record = by_window.get(window.window_id)
            if record is None:
                failed_windows += 1
                warnings.append(f"{window.window_id} VLM output missing")
                continue
            if str(record.get("status") or "READY").strip().upper() != "READY":
                failed_windows += 1
                detail = self._clean_failure_detail(record)
                warnings.append(
                    f"{window.window_id} VLM inference failed" + (f": {detail}" if detail else "")
                )
                if detail:
                    failure_details.append(f"{window.window_id} {detail}")
                continue
            raw_window = record.get("semantic") if isinstance(record.get("semantic"), Mapping) else record
            if not isinstance(raw_window, Mapping):
                failed_windows += 1
                continue
            window_summaries.append(self._normalize_window_summary(raw_window, window))
            raw_shots = raw_window.get("shots")
            if not isinstance(raw_shots, list):
                warnings.append(f"{window.window_id} has no shot-aware semantics")
                continue
            expected = {shot.revision_item_id: shot for shot in window.shots}
            seen: set[str] = set()
            for raw_shot in raw_shots:
                if not isinstance(raw_shot, Mapping):
                    continue
                item_id = str(raw_shot.get("revision_item_id") or "").strip()
                shot = expected.get(item_id)
                if shot is None or item_id in seen:
                    continue
                seen.add(item_id)
                semantic = self._normalize_semantic(raw_shot.get("semantic"))
                if semantic is None:
                    continue
                candidates.setdefault(item_id, []).append((
                    _candidate_rank(window, shot),
                    window,
                    semantic,
                    self._normalize_shot_context(raw_shot),
                ))
        self._runtime_failure_details = tuple(failure_details[:12])

        evidence: list[p2.P2EvidenceRecord] = []
        for shot in context.shots:
            options = candidates.get(shot.revision_item_id, [])
            if not options:
                warnings.append(f"Shot {shot.ordinal} has no usable E2 window semantic")
                continue
            options.sort(key=lambda item: item[0], reverse=True)
            _rank, window, semantic, context_meta = options[0]
            evidence.append(p2.P2EvidenceRecord(
                source_type="VLM_OUTPUT",
                source_id=f"{context.episode_id}:vlm-e2-shot:{shot.ordinal:06d}",
                source_start_us=shot.start_us,
                source_end_us=shot.end_us,
                shot_revision_item_id=shot.revision_item_id,
                text=self._clean_text(semantic.get("shot", {}).get("summary"), max_len=1200),
                language=context.source_language,
                confidence=None,
                payload={
                    "shot_ordinal": shot.ordinal,
                    "semantic": semantic,
                    "episode_window": {
                        "profile": VLM_EPISODE_WINDOW_PROFILE,
                        "window_id": window.window_id,
                        "window_start_us": window.start_us,
                        "window_end_us": window.end_us,
                        "supporting_window_ids": [item[1].window_id for item in options[1:4]],
                        "selection_policy": "max-surrounding-context-margin-v1",
                        **context_meta,
                    },
                },
            ))

        metadata = self._metadata(
            config=config,
            video_kind=video_kind,
            windows=windows,
            window_summaries=window_summaries,
            shot_count=len(context.shots),
            semantic_count=len(evidence),
            failed_window_count=failed_windows,
        )
        if evidence:
            return p2.P2ProviderResult(
                component="VLM", provider=VLM_PROVIDER_NAME, model=self.model_name,
                status="READY", evidence=tuple(evidence), metadata=metadata,
                warnings=tuple(dict.fromkeys(warnings)),
            )
        return p2.P2ProviderResult(
            component="VLM", provider=VLM_PROVIDER_NAME, model=self.model_name,
            status="FAILED", metadata=metadata,
            warnings=tuple(dict.fromkeys(warnings)) or ("P2-E2 VLM produced no usable Shot semantics",),
        )


def run_qwen3_vl_episode_window_semantics(
    run_id: str,
    *,
    provider: Qwen3VLSemanticProvider | None = None,
) -> p2.P2EvidenceArtifact:
    """Run E2 and persist through the existing immutable VLM sidecar boundary."""

    return p2.run_local_provider(run_id, provider or Qwen3VLSemanticProvider())
