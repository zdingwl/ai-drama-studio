"""Breakdown P2-E3: contextual per-Shot semantic refinement.

Production E2 already lets Qwen see overlapping Episode video windows. E3 is the second,
text-only pass inside the production VLM runtime: it refines each exact frozen Shot with
provisional Scene context, previous/current/next E2 semantics, selected/supporting window
summaries, and overlapping Episode ASR/OCR.

The frozen P2 sidecar contract is unchanged. The final persisted ``VLM_OUTPUT`` keeps the E2
visual semantic verbatim in ``payload.e2_semantic`` and exposes the E3 result in
``payload.semantic`` for Fusion. One immutable VLM sidecar fingerprint therefore protects both
layers. E3 never creates Final Character/Scene/Prop/Binding IDs and never rewrites ASR/OCR text.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Mapping, Sequence

from engine.app import breakdown_p2_fusion_v1 as fusion
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_v1 as vlm
from engine.app import studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun

REFINEMENT_INPUT_SCHEMA = "breakdown-p2-contextual-refinement-input-v1"
REFINEMENT_PROFILE = "breakdown-p2-contextual-shot-refinement-e3-v1"
REFINEMENT_PROMPT_PROFILE = "breakdown-p2-contextual-shot-refinement-zh-v1"
REFINEMENT_PROVIDER_NAME = "qwen3-vl-contextual-refiner"
REFINEMENT_VERSION = "1"
REFINEMENT_DRAFT_TEXT_LANGUAGE = "zh-CN"
DEFAULT_REFINEMENT_MAX_NEW_TOKENS = 1536
REFINEMENT_TIMEOUT_SECONDS = vlm.VLM_TIMEOUT_SECONDS

_GENERIC_LOCATION_HINTS = frozenset({
    "", "unknown", "未知", "不明", "室内", "室外", "内景", "外景", "房间",
    "房间内", "空间", "室内空间", "室外空间", "indoors", "outdoors",
    "interior", "exterior", "room",
})


class BreakdownP2RefinementError(RuntimeError):
    """E3 context/runtime/result cannot be consumed safely."""


@dataclass(frozen=True)
class RefinementRuntimeConfig:
    python_executable: Path
    runner_script: Path
    model_path: Path
    model_name: str
    source_language: str
    device: str
    max_new_tokens: int
    ffmpeg_shared_bin: Path | None


@dataclass(frozen=True)
class ContextualRefinementResult:
    status: str
    provider: str
    model: str
    evidence: tuple[p2.P2EvidenceRecord, ...]
    metadata: Mapping[str, Any]
    warnings: tuple[str, ...] = ()


RefinementInferenceRunner = Callable[
    [RefinementRuntimeConfig, Sequence[Mapping[str, Any]]],
    Sequence[Mapping[str, Any]],
]


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _stable_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _clean_text(value: Any, *, max_len: int = 2000) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text[:max_len] if text else None


def _normalized_location(value: Any) -> str:
    text = _clean_text(value, max_len=255) or ""
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _weak_location(value: Any) -> bool:
    key = _normalized_location(value)
    return not key or key in _GENERIC_LOCATION_HINTS or key.startswith("unknown") or key.startswith("未知")


def _semantic(record: p2.P2EvidenceRecord | None) -> Mapping[str, Any] | None:
    if record is None or not isinstance(record.payload, Mapping):
        return None
    value = record.payload.get("semantic")
    return value if isinstance(value, Mapping) else None


def _episode_window(record: p2.P2EvidenceRecord | None) -> Mapping[str, Any]:
    if record is None or not isinstance(record.payload, Mapping):
        return {}
    value = record.payload.get("episode_window")
    return value if isinstance(value, Mapping) else {}


def _range_overlaps(record: p2.P2EvidenceRecord, start_us: int, end_us: int) -> bool:
    if record.source_start_us is None or record.source_end_us is None:
        return False
    return min(int(record.source_end_us), end_us) > max(int(record.source_start_us), start_us)


def _provisional_scene_contexts(
    shots: Sequence[p2.P2ShotInput],
    vlm_by_shot: Mapping[str, p2.P2EvidenceRecord],
) -> dict[str, dict[str, Any]]:
    """Conservative Scene context for prompting only; Final Scene remains downstream truth."""

    result: dict[str, dict[str, Any]] = {}
    scene_index = 0
    anchor_location: str | None = None
    anchor_ie = "UNKNOWN"
    anchor_time: str | None = None

    for shot in shots:
        record = vlm_by_shot.get(shot.revision_item_id)
        semantic = _semantic(record) or {}
        scene = semantic.get("scene") if isinstance(semantic.get("scene"), Mapping) else {}
        window = _episode_window(record)
        continuity = str(window.get("scene_continuity") or "UNCERTAIN").strip().upper()
        location = _clean_text(scene.get("location_hint"), max_len=255)
        ie = str(scene.get("interior_exterior") or "UNKNOWN").strip().upper()
        time_of_day = _clean_text(scene.get("time_of_day"), max_len=64)

        anchor_key = _normalized_location(anchor_location)
        location_key = _normalized_location(location)
        strong_location_change = (
            bool(anchor_key and location_key)
            and not _weak_location(anchor_location)
            and not _weak_location(location)
            and anchor_key != location_key
            and anchor_key not in location_key
            and location_key not in anchor_key
        )
        strong_ie_change = (
            anchor_ie in {"INT", "EXT"}
            and ie in {"INT", "EXT"}
            and anchor_ie != ie
        )
        if scene_index == 0 or continuity == "NEW_SCENE" or strong_location_change or strong_ie_change:
            scene_index += 1
            anchor_location = location
            anchor_ie = ie if ie in {"INT", "EXT", "MIXED"} else "UNKNOWN"
            anchor_time = time_of_day
        else:
            if _weak_location(anchor_location) and not _weak_location(location):
                anchor_location = location
            elif (
                anchor_key and location_key and anchor_key in location_key
                and len(location_key) > len(anchor_key)
            ):
                anchor_location = location
            if anchor_ie == "UNKNOWN" and ie in {"INT", "EXT", "MIXED"}:
                anchor_ie = ie
            if not anchor_time and time_of_day:
                anchor_time = time_of_day

        result[shot.revision_item_id] = {
            "provisional_scene_index": scene_index,
            "location_hint": anchor_location,
            "interior_exterior": anchor_ie,
            "time_of_day": anchor_time,
            "e2_scene_continuity": continuity,
            "e2_scene_basis": str(window.get("scene_basis") or "UNCERTAIN").strip().upper(),
            "e2_context_note": _clean_text(window.get("context_note"), max_len=700),
        }
    return result


def _window_summaries(bundle: fusion.FusionInputBundle) -> dict[str, Mapping[str, Any]]:
    metadata = bundle.components["VLM"].result.metadata
    raw = metadata.get("window_summaries") if isinstance(metadata, Mapping) else None
    result: dict[str, Mapping[str, Any]] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            window_id = str(item.get("window_id") or "").strip()
            if window_id:
                result[window_id] = item
    return result


def _shot_context_payload(
    shot: p2.P2ShotInput | None,
    record: p2.P2EvidenceRecord | None,
) -> dict[str, Any] | None:
    if shot is None:
        return None
    return {
        "revision_item_id": shot.revision_item_id,
        "ordinal": shot.ordinal,
        "source_start_us": shot.start_us,
        "source_end_us": shot.end_us,
        "semantic": dict(_semantic(record) or {}),
        "episode_window": dict(_episode_window(record)),
        "raw_vlm_source_id": record.source_id if record is not None else None,
    }


def build_refinement_items(bundle: fusion.FusionInputBundle) -> tuple[dict[str, Any], ...]:
    """Build exact-Shot E3 inputs from validated ASR/OCR/E2 records."""

    shots = tuple(bundle.context.shots)
    vlm_by_shot = {
        str(item.shot_revision_item_id): item
        for item in bundle.components["VLM"].result.evidence
        if item.source_type.strip().upper() == "VLM_OUTPUT" and item.shot_revision_item_id
    }
    scene_contexts = _provisional_scene_contexts(shots, vlm_by_shot)
    summaries = _window_summaries(bundle)
    asr_segments = [
        item for item in bundle.components["ASR"].result.evidence
        if item.source_type.strip().upper() == "ASR_SEGMENT"
    ]
    ocr_records = [
        item for item in bundle.components["OCR"].result.evidence
        if item.source_type.strip().upper() == "OCR_OBSERVATION"
    ]

    items: list[dict[str, Any]] = []
    for index, shot in enumerate(shots):
        previous = shots[index - 1] if index > 0 else None
        following = shots[index + 1] if index + 1 < len(shots) else None
        neighborhood_start = previous.start_us if previous is not None else shot.start_us
        neighborhood_end = following.end_us if following is not None else shot.end_us
        current_record = vlm_by_shot.get(shot.revision_item_id)
        current_window = _episode_window(current_record)

        window_ids: list[str] = []
        selected_window = str(current_window.get("window_id") or "").strip()
        if selected_window:
            window_ids.append(selected_window)
        supporting = current_window.get("supporting_window_ids")
        if isinstance(supporting, list):
            for value in supporting[:3]:
                window_id = str(value or "").strip()
                if window_id and window_id not in window_ids:
                    window_ids.append(window_id)

        local_asr = [
            {
                "source_id": record.source_id,
                "source_start_us": record.source_start_us,
                "source_end_us": record.source_end_us,
                "text": record.text,
                "language": record.language,
            }
            for record in asr_segments
            if _range_overlaps(record, neighborhood_start, neighborhood_end)
        ][:12]
        local_ocr = [
            {
                "source_id": record.source_id,
                "source_start_us": record.source_start_us,
                "source_end_us": record.source_end_us,
                "text": record.text,
                "language": record.language,
                "confidence": record.confidence,
                "polygon_norm": (
                    record.payload.get("polygon_norm")
                    if isinstance(record.payload, Mapping)
                    else None
                ),
            }
            for record in ocr_records
            if _range_overlaps(record, neighborhood_start, neighborhood_end)
        ][:24]

        items.append({
            "revision_item_id": shot.revision_item_id,
            "ordinal": shot.ordinal,
            "source_start_us": shot.start_us,
            "source_end_us": shot.end_us,
            "scene_context": scene_contexts.get(shot.revision_item_id, {}),
            "previous_shot": _shot_context_payload(
                previous,
                vlm_by_shot.get(previous.revision_item_id) if previous is not None else None,
            ),
            "current_shot": _shot_context_payload(shot, current_record),
            "next_shot": _shot_context_payload(
                following,
                vlm_by_shot.get(following.revision_item_id) if following is not None else None,
            ),
            "window_context": [dict(summaries[window_id]) for window_id in window_ids if window_id in summaries],
            "asr_context": local_asr,
            "ocr_context": local_ocr,
            "provenance": {
                "raw_vlm_source_id": current_record.source_id if current_record is not None else None,
                "selected_window_id": selected_window or None,
                "supporting_window_ids": window_ids[1:],
                "asr_source_ids": [item["source_id"] for item in local_asr],
                "ocr_source_ids": [item["source_id"] for item in local_ocr],
            },
        })
    return tuple(items)


def _merge_refined_semantic(
    normalizer: vlm.Qwen3VLSemanticProvider,
    base_semantic: Mapping[str, Any],
    candidate: Any,
) -> dict[str, Any] | None:
    """Whitelist E3 output and fill omitted fields from the E2 visual semantic."""

    base = normalizer._normalize_semantic(base_semantic)
    refined = normalizer._normalize_semantic(candidate)
    if base is None:
        return refined
    if refined is None:
        return base

    scene = dict(base.get("scene") or {})
    candidate_scene = refined.get("scene") if isinstance(refined.get("scene"), Mapping) else {}
    for key in ("location_hint", "time_of_day", "environment_description"):
        value = candidate_scene.get(key)
        if value:
            scene[key] = value
    candidate_ie = str(candidate_scene.get("interior_exterior") or "UNKNOWN").strip().upper()
    if candidate_ie != "UNKNOWN":
        scene["interior_exterior"] = candidate_ie

    shot = dict(base.get("shot") or {})
    candidate_shot = refined.get("shot") if isinstance(refined.get("shot"), Mapping) else {}
    for key, value in candidate_shot.items():
        if value:
            shot[key] = value

    base_subjects = {
        str(item.get("label")): dict(item)
        for item in base.get("subjects", [])
        if isinstance(item, Mapping) and item.get("label")
    }
    candidate_subjects = {
        str(item.get("label")): dict(item)
        for item in refined.get("subjects", [])
        if isinstance(item, Mapping) and str(item.get("label")) in base_subjects
    }
    subjects: list[dict[str, Any]] = []
    for label, base_subject in base_subjects.items():
        merged = dict(base_subject)
        for key, value in candidate_subjects.get(label, {}).items():
            if key != "label" and value not in (None, ""):
                merged[key] = value
        subjects.append(merged)

    merged = {
        "scene": scene,
        "shot": shot,
        "subjects": subjects,
        "events": list(refined.get("events") or base.get("events") or []),
        "props": list(refined.get("props") or base.get("props") or []),
    }
    return normalizer._normalize_semantic(merged)


class ContextualShotRefiner:
    """Text-only Qwen3-VL E3 inference over E2 + Scene + ASR/OCR context."""

    def __init__(
        self,
        *,
        model_name: str | None = None,
        model_path: str | None = None,
        python_executable: str | None = None,
        runner_script: str | None = None,
        device: str | None = None,
        max_new_tokens: int | None = None,
        ffmpeg_shared_bin: str | None = None,
        inference_runner: RefinementInferenceRunner | None = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        inference_root = repo_root / ".runtime" / "TransVLM" / "inference"
        default_python = (
            inference_root / ".venv" / "Scripts" / "python.exe"
            if os.name == "nt"
            else inference_root / ".venv" / "bin" / "python"
        )
        self.model_name = (model_name or vlm.DEFAULT_VLM_MODEL).strip()
        self.model_path = Path(
            model_path
            or os.getenv("AI_DRAMA_P2_VLM_MODEL_PATH")
            or (inference_root / "pretrained" / "Qwen3-VL-4B-Instruct")
        ).expanduser()
        self.python_executable = Path(
            python_executable or os.getenv("AI_DRAMA_P2_VLM_PYTHON") or default_python
        ).expanduser()
        self.runner_script = Path(
            runner_script
            or os.getenv("AI_DRAMA_P2_REFINEMENT_RUNNER")
            or (repo_root / "scripts" / "run_breakdown_refinement_qwen3.py")
        ).expanduser()
        self.device = (device or os.getenv("AI_DRAMA_P2_VLM_DEVICE") or "cuda").strip().lower()
        self.max_new_tokens = int(
            max_new_tokens
            if max_new_tokens is not None
            else os.getenv("AI_DRAMA_P2_REFINEMENT_MAX_NEW_TOKENS") or DEFAULT_REFINEMENT_MAX_NEW_TOKENS
        )
        if ffmpeg_shared_bin is not None:
            self.ffmpeg_shared_bin = Path(ffmpeg_shared_bin).expanduser()
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
            raise ValueError("P2-E3 model_name 不能为空")
        if self.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("P2-E3 device 只允许 auto/cpu/cuda")
        if self.max_new_tokens < 128:
            raise ValueError("P2-E3 max_new_tokens 必须 >= 128")

    @classmethod
    def from_vlm_provider(cls, provider: Any) -> "ContextualShotRefiner":
        return cls(
            model_name=str(getattr(provider, "model_name", None) or vlm.DEFAULT_VLM_MODEL),
            model_path=str(getattr(provider, "model_path", "")) or None,
            python_executable=str(getattr(provider, "python_executable", "")) or None,
            device=str(getattr(provider, "device", "cuda") or "cuda"),
            ffmpeg_shared_bin=(
                str(getattr(provider, "ffmpeg_shared_bin"))
                if getattr(provider, "ffmpeg_shared_bin", None)
                else None
            ),
        )

    def _runtime_config(self, source_language: str) -> RefinementRuntimeConfig:
        return RefinementRuntimeConfig(
            python_executable=self.python_executable,
            runner_script=self.runner_script,
            model_path=self.model_path,
            model_name=self.model_name,
            source_language=source_language,
            device=self.device,
            max_new_tokens=self.max_new_tokens,
            ffmpeg_shared_bin=self.ffmpeg_shared_bin,
        )

    def _runtime_missing(self, config: RefinementRuntimeConfig) -> tuple[str, ...]:
        if not self._uses_production_runner:
            return ()
        missing: list[str] = []
        if not config.python_executable.is_file():
            missing.append("isolated Qwen3-VL Python runtime")
        if not config.runner_script.is_file():
            missing.append("P2-E3 refinement runner script")
        if not config.model_path.is_dir():
            missing.append("Qwen3-VL-4B-Instruct checkpoint")
        elif not (config.model_path / "config.json").is_file():
            missing.append("Qwen3-VL checkpoint config.json")
        return tuple(missing)

    @staticmethod
    def _subprocess_env(config: RefinementRuntimeConfig) -> dict[str, str]:
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

    def _run_subprocess(
        self,
        config: RefinementRuntimeConfig,
        items: Sequence[Mapping[str, Any]],
    ) -> Sequence[Mapping[str, Any]]:
        with tempfile.TemporaryDirectory(prefix="ai-drama-p2-refinement-") as temp_name:
            root = Path(temp_name)
            manifest_path = root / "manifest.json"
            output_path = root / "output.jsonl"
            manifest_path.write_text(_stable_json({
                "schema_version": REFINEMENT_INPUT_SCHEMA,
                "profile": REFINEMENT_PROFILE,
                "prompt_profile": REFINEMENT_PROMPT_PROFILE,
                "model": config.model_name,
                "source_language": config.source_language,
                "items": [dict(item) for item in items],
            }), encoding="utf-8")
            subprocess.run(
                [
                    str(config.python_executable), str(config.runner_script),
                    "--model-path", str(config.model_path),
                    "--manifest", str(manifest_path),
                    "--output", str(output_path),
                    "--device", config.device,
                    "--max-new-tokens", str(config.max_new_tokens),
                ],
                check=True,
                cwd=str(config.runner_script.parent),
                env=self._subprocess_env(config),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=REFINEMENT_TIMEOUT_SECONDS,
            )
            if not output_path.is_file():
                raise RuntimeError("P2-E3 refinement runner produced no output")
            records: list[Mapping[str, Any]] = []
            for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if isinstance(value, Mapping):
                    records.append(value)
            return tuple(records)

    def refine(self, bundle: fusion.FusionInputBundle) -> ContextualRefinementResult:
        config = self._runtime_config(bundle.context.source_language)
        missing = self._runtime_missing(config)
        if missing:
            return ContextualRefinementResult(
                status="FAILED", provider=REFINEMENT_PROVIDER_NAME, model=self.model_name,
                evidence=(),
                metadata={"profile": REFINEMENT_PROFILE, "error_type": "RuntimeUnavailable"},
                warnings=("P2-E3 runtime is not available: " + ", ".join(missing),),
            )

        items = build_refinement_items(bundle)
        if not items:
            raise BreakdownP2RefinementError("P2-E3 没有可精修 Shot")
        try:
            records = tuple(self._inference_runner(config, items))
        except Exception as exc:
            return ContextualRefinementResult(
                status="FAILED", provider=REFINEMENT_PROVIDER_NAME, model=self.model_name,
                evidence=(),
                metadata={
                    "profile": REFINEMENT_PROFILE,
                    "prompt_profile": REFINEMENT_PROMPT_PROFILE,
                    "error_type": type(exc).__name__,
                    "shot_count": len(items),
                },
                warnings=("P2-E3 contextual refinement inference failed",),
            )

        by_id: dict[str, Mapping[str, Any]] = {}
        for record in records:
            item_id = str(record.get("revision_item_id") or "").strip()
            if item_id and item_id not in by_id:
                by_id[item_id] = record
        raw_vlm = {
            str(item.shot_revision_item_id): item
            for item in bundle.components["VLM"].result.evidence
            if item.source_type.strip().upper() == "VLM_OUTPUT" and item.shot_revision_item_id
        }
        item_by_id = {str(item["revision_item_id"]): item for item in items}
        normalizer = vlm.Qwen3VLSemanticProvider(inference_runner=lambda _config, _shots: ())
        evidence: list[p2.P2EvidenceRecord] = []
        warnings: list[str] = []
        fallback_count = 0

        for shot in bundle.context.shots:
            base_record = raw_vlm.get(shot.revision_item_id)
            base_semantic = _semantic(base_record)
            if base_record is None or base_semantic is None:
                raise BreakdownP2RefinementError(f"Shot {shot.ordinal} 缺少 E2 VLM semantic")
            record = by_id.get(shot.revision_item_id)
            refined_semantic: dict[str, Any] | None = None
            refinement_status = "READY"
            if record is not None and str(record.get("status") or "READY").strip().upper() == "READY":
                refined_semantic = _merge_refined_semantic(
                    normalizer, base_semantic, record.get("semantic")
                )
            if refined_semantic is None:
                refined_semantic = normalizer._normalize_semantic(base_semantic)
                refinement_status = "FALLBACK_E2"
                fallback_count += 1
                warnings.append(f"Shot {shot.ordinal} E3 refinement fell back to E2 semantic")
            if refined_semantic is None:
                raise BreakdownP2RefinementError(f"Shot {shot.ordinal} 没有可消费 refined semantic")

            input_item = item_by_id[shot.revision_item_id]
            evidence.append(p2.P2EvidenceRecord(
                source_type="VLM_OUTPUT",
                source_id=base_record.source_id,
                source_start_us=shot.start_us,
                source_end_us=shot.end_us,
                shot_revision_item_id=shot.revision_item_id,
                text=_clean_text(refined_semantic.get("shot", {}).get("summary"), max_len=1200),
                language="zh-CN",
                confidence=None,
                payload={
                    "shot_ordinal": shot.ordinal,
                    "semantic": refined_semantic,
                    "e2_semantic": dict(base_semantic),
                    "episode_window": dict(_episode_window(base_record)),
                    "contextual_refinement": {
                        "profile": REFINEMENT_PROFILE,
                        "prompt_profile": REFINEMENT_PROMPT_PROFILE,
                        "status": refinement_status,
                        "refinement_note": _clean_text(
                            record.get("refinement_note") if record is not None else None,
                            max_len=900,
                        ),
                        **dict(input_item.get("provenance") or {}),
                    },
                },
            ))

        synthetic = p2.P2ProviderResult(
            component="VLM",
            provider=REFINEMENT_PROVIDER_NAME,
            model=self.model_name,
            status="READY",
            evidence=tuple(evidence),
            metadata={
                "semantic_schema": vlm.VLM_SEMANTIC_SCHEMA,
                "profile": REFINEMENT_PROFILE,
                "prompt_profile": REFINEMENT_PROMPT_PROFILE,
                "draft_text_language": REFINEMENT_DRAFT_TEXT_LANGUAGE,
                "shot_count": len(bundle.context.shots),
                "refined_shot_count": len(evidence) - fallback_count,
                "fallback_shot_count": fallback_count,
                "input_modalities": ["E2_VLM", "SCENE_CONTEXT", "NEIGHBOR_SHOTS", "ASR", "OCR"],
                "confidence_policy": "provider-output-unscored",
            },
            warnings=tuple(dict.fromkeys(warnings)),
        )
        p2.validate_provider_result(bundle.context, synthetic)
        return ContextualRefinementResult(
            status="READY_WITH_WARNINGS" if warnings else "READY",
            provider=synthetic.provider,
            model=synthetic.model,
            evidence=synthetic.evidence,
            metadata=synthetic.metadata,
            warnings=synthetic.warnings,
        )


def _e2_result_fingerprint(result: p2.P2ProviderResult) -> str:
    payload = {
        "component": result.component,
        "provider": result.provider,
        "model": result.model,
        "status": result.status,
        "metadata": dict(result.metadata),
        "warnings": list(result.warnings),
        "evidence": [
            {
                "source_type": item.source_type,
                "source_id": item.source_id,
                "source_start_us": item.source_start_us,
                "source_end_us": item.source_end_us,
                "shot_revision_item_id": item.shot_revision_item_id,
                "text": item.text,
                "language": item.language,
                "confidence": item.confidence,
                "payload": dict(item.payload),
            }
            for item in result.evidence
        ],
    }
    return sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _load_context_bundle(
    context: p2.P2RunContext,
    e2_result: p2.P2ProviderResult,
) -> fusion.FusionInputBundle:
    """Load already-persisted ASR/OCR sidecars and attach in-memory E2 result for E3."""

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, context.run_id)
        if run is None or run.status != "PROCESSING":
            raise BreakdownP2RefinementError("E3 只能消费 PROCESSING BreakdownRun")
        statuses = _json_object(run.component_status_json)

    components: dict[str, fusion.LoadedComponent] = {}
    warnings: list[dict[str, Any]] = []
    for component in ("ASR", "OCR"):
        entry = statuses.get(component)
        if not isinstance(entry, Mapping):
            raise BreakdownP2RefinementError(f"E3 要求 {component} sidecar 已登记")
        loaded = fusion._load_one_component(context, entry, component)
        components[component] = loaded
        if loaded.result.status in {"NO_EVIDENCE", "NOT_AVAILABLE"}:
            warnings.append({
                "code": f"E3_{component}_DEGRADED_{loaded.result.status}",
                "message": f"E3 {component} context unavailable; refinement will rely on remaining context",
            })
        elif loaded.result.status != "READY":
            raise BreakdownP2RefinementError(f"E3 不允许消费 {component} status={loaded.result.status}")

    e2_fingerprint = _e2_result_fingerprint(e2_result)
    components["VLM"] = fusion.LoadedComponent(
        component="VLM",
        artifact_uri=f"memory://e2/{e2_fingerprint}",
        fingerprint=e2_fingerprint,
        result=e2_result,
    )
    return fusion.FusionInputBundle(
        context=context,
        components=components,
        warnings=tuple(warnings),
    )


def refine_e2_provider_result(
    context: p2.P2RunContext,
    e2_result: p2.P2ProviderResult,
    *,
    refiner: ContextualShotRefiner | None = None,
) -> p2.P2ProviderResult:
    """Production E3 adapter: E2 result + registered ASR/OCR -> final VLM ProviderResult."""

    if e2_result.component.strip().upper() != "VLM" or e2_result.status != "READY":
        return e2_result
    bundle = _load_context_bundle(context, e2_result)
    result = (refiner or ContextualShotRefiner()).refine(bundle)
    if result.status not in {"READY", "READY_WITH_WARNINGS"}:
        metadata = dict(e2_result.metadata)
        metadata.update({
            "contextual_refinement_profile": REFINEMENT_PROFILE,
            "contextual_refinement_status": result.status,
            "contextual_refinement_provider": result.provider,
            "contextual_refinement_metadata": dict(result.metadata),
        })
        failed = p2.P2ProviderResult(
            component="VLM",
            provider=e2_result.provider,
            model=e2_result.model,
            status="FAILED",
            evidence=(),
            metadata=metadata,
            warnings=tuple(e2_result.warnings) + tuple(result.warnings),
        )
        p2.validate_provider_result(context, failed)
        return failed

    raw_by_shot = {
        str(item.shot_revision_item_id): item
        for item in e2_result.evidence
        if item.shot_revision_item_id
    }
    final_evidence: list[p2.P2EvidenceRecord] = []
    for refined in result.evidence:
        raw = raw_by_shot.get(str(refined.shot_revision_item_id or ""))
        if raw is None:
            raise BreakdownP2RefinementError("E3 refined evidence 无法映射回 E2 Shot")
        payload = dict(refined.payload)
        payload.setdefault("e2_semantic", dict(_semantic(raw) or {}))
        payload.setdefault("episode_window", dict(_episode_window(raw)))
        final_evidence.append(p2.P2EvidenceRecord(
            source_type="VLM_OUTPUT",
            source_id=raw.source_id,
            source_start_us=raw.source_start_us,
            source_end_us=raw.source_end_us,
            shot_revision_item_id=raw.shot_revision_item_id,
            text=refined.text,
            language=refined.language or raw.language,
            confidence=None,
            payload=payload,
        ))

    metadata = dict(e2_result.metadata)
    metadata.update({
        "contextual_refinement_profile": REFINEMENT_PROFILE,
        "contextual_refinement_prompt_profile": REFINEMENT_PROMPT_PROFILE,
        "contextual_refinement_status": result.status,
        "contextual_refinement_provider": result.provider,
        "contextual_refinement_version": REFINEMENT_VERSION,
        "contextual_refinement_metadata": dict(result.metadata),
        "e2_semantic_preservation": "VLM_OUTPUT.payload.e2_semantic",
        "fusion_semantic_source": "VLM_OUTPUT.payload.semantic",
    })
    final = p2.P2ProviderResult(
        component="VLM",
        provider=e2_result.provider,
        model=e2_result.model,
        status="READY",
        evidence=tuple(final_evidence),
        metadata=metadata,
        warnings=tuple(dict.fromkeys(tuple(e2_result.warnings) + tuple(result.warnings))),
    )
    p2.validate_provider_result(context, final)
    return final
