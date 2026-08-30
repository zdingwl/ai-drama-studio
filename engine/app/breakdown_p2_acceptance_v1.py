"""Breakdown P2.6 local runtime preflight and real-video acceptance reports.

The acceptance layer measures/records a completed P2 Run. It never mutates Draft rows,
reruns models implicitly, or turns human review into Final asset identity truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence

from sqlalchemy import func, select

from engine.app import studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun
from engine.app.breakdown_p2_asr_v1 import FasterWhisperASRProvider
from engine.app.breakdown_p2_ocr_runtime_v1 import RapidOCROCRProvider
from engine.app.breakdown_p2_vlm_continuity_v1 import Qwen3VLSemanticProvider
from engine.app.shot_revision_v2 import ShotRevisionItem

P2_ACCEPTANCE_SCHEMA = "breakdown-p2-acceptance-v1"
P2_ACCEPTANCE_VERSION = "1"
READY_RUN_STATUSES = {"READY", "READY_WITH_WARNINGS"}
CORE_REVIEW_KEYS = (
    "asr_dialogue",
    "asr_timing",
    "vlm_scene",
    "vlm_subjects",
    "vlm_actions",
    "vlm_props",
    "fusion_completeness",
    "fusion_timing",
    "fusion_conflict_handling",
)
OPTIONAL_REVIEW_KEYS = ("ocr_text",)
ALL_REVIEW_KEYS = CORE_REVIEW_KEYS + OPTIONAL_REVIEW_KEYS
MIN_ACCEPTANCE_SCORE = 4.0


class BreakdownP2AcceptanceError(RuntimeError):
    """P2.6 acceptance input/report is invalid."""


@dataclass(frozen=True)
class StructuralAssessment:
    passed: bool
    checks: tuple[dict[str, Any], ...]


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _command_version(command: str) -> dict[str, Any]:
    path = shutil.which(command)
    if not path:
        return {"available": False, "path": None, "version": None}
    try:
        completed = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        first_line = (completed.stdout or completed.stderr or "").splitlines()
        version = first_line[0].strip() if first_line else None
    except Exception as exc:
        return {"available": True, "path": path, "version": None, "error_type": type(exc).__name__}
    return {"available": True, "path": path, "version": version}


def _nvidia_smi() -> dict[str, Any]:
    path = shutil.which("nvidia-smi")
    if not path:
        return {"available": False, "path": None, "gpus": []}
    try:
        completed = subprocess.run(
            [
                path,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        rows = []
        if completed.returncode == 0:
            for line in completed.stdout.splitlines():
                parts = [item.strip() for item in line.split(",")]
                if len(parts) >= 3:
                    rows.append({
                        "name": parts[0],
                        "memory_total_mib": parts[1],
                        "driver_version": parts[2],
                    })
        return {
            "available": completed.returncode == 0,
            "path": path,
            "gpus": rows,
            "returncode": completed.returncode,
        }
    except Exception as exc:
        return {"available": False, "path": path, "gpus": [], "error_type": type(exc).__name__}


def _probe_vlm_runtime(provider: Qwen3VLSemanticProvider) -> dict[str, Any]:
    result: dict[str, Any] = {
        "python": str(provider.python_executable),
        "python_exists": provider.python_executable.is_file(),
        "runner": str(provider.runner_script),
        "runner_exists": provider.runner_script.is_file(),
        "model_path": str(provider.model_path),
        "model_path_exists": provider.model_path.is_dir(),
        "model": provider.model_name,
        "device_requested": provider.device,
        "production_profile": getattr(provider, "FAST_GROUNDED_PROFILE", None) or "breakdown-p2-vlm-fast-grounded-v1",
        "window_seconds": getattr(provider, "window_duration_seconds", None),
        "window_overlap_ratio": getattr(provider, "window_overlap_ratio", None),
        "window_fps": provider.video_fps,
        "window_max_pixels": provider.max_pixels,
        "window_max_new_tokens": provider.max_new_tokens,
        "exact_shot_max_pixels": getattr(provider, "exact_shot_max_pixels", None),
        "grounding_max_new_tokens": getattr(provider, "grounding_max_new_tokens", None),
        "grounding_batch_size": getattr(provider, "grounding_batch_size", None),
        "model_load_policy": "one-run-one-vlm-process-one-model-load",
    }
    if not provider.python_executable.is_file():
        return result
    probe_code = (
        "import json,sys; out={'python':sys.version.split()[0]}; "
        "\ntry:\n import torch; out['torch']=getattr(torch,'__version__',None); "
        "out['cuda_available']=bool(torch.cuda.is_available()); "
        "out['cuda_device_name']=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None\n"
        "except Exception as e: out['torch_error']=type(e).__name__\n"
        "try:\n import transformers; out['transformers']=getattr(transformers,'__version__',None)\n"
        "except Exception as e: out['transformers_error']=type(e).__name__\n"
        "try:\n import qwen_vl_utils; out['qwen_vl_utils']=True\n"
        "except Exception as e: out['qwen_vl_utils']=False; out['qwen_vl_utils_error']=type(e).__name__\n"
        "print(json.dumps(out))"
    )
    try:
        completed = subprocess.run(
            [str(provider.python_executable), "-c", probe_code],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        result["probe_returncode"] = completed.returncode
        if completed.returncode == 0:
            try:
                payload = json.loads(completed.stdout.strip().splitlines()[-1])
                if isinstance(payload, dict):
                    result["probe"] = payload
            except Exception:
                result["probe_error_type"] = "InvalidJSON"
        else:
            result["probe_error_type"] = "RuntimeProbeFailed"
    except Exception as exc:
        result["probe_error_type"] = type(exc).__name__
    return result


def collect_p2_runtime_preflight() -> dict[str, Any]:
    """Collect non-secret local readiness facts without running inference or downloading models."""

    asr = FasterWhisperASRProvider()
    ocr = RapidOCROCRProvider()
    vlm = Qwen3VLSemanticProvider()
    nvidia = _nvidia_smi()
    vlm_runtime = _probe_vlm_runtime(vlm)

    asr_package = find_spec("faster_whisper") is not None
    ocr_package = find_spec("rapidocr") is not None
    cv2_package = find_spec("cv2") is not None
    ffmpeg = _command_version("ffmpeg")
    ffprobe = _command_version("ffprobe")
    vlm_probe = vlm_runtime.get("probe") if isinstance(vlm_runtime.get("probe"), Mapping) else {}
    vlm_cuda_ok = bool(vlm_probe.get("cuda_available"))
    vlm_device_ok = vlm.device != "cuda" or vlm_cuda_ok

    checks = {
        "main_python": True,
        "faster_whisper_package": asr_package,
        "rapidocr_package": ocr_package,
        "opencv_package": cv2_package,
        "ffmpeg": bool(ffmpeg.get("available")),
        "ffprobe": bool(ffprobe.get("available")),
        "vlm_python": bool(vlm_runtime.get("python_exists")),
        "vlm_runner": bool(vlm_runtime.get("runner_exists")),
        "vlm_model_path": bool(vlm_runtime.get("model_path_exists")),
        "vlm_runtime_probe": vlm_runtime.get("probe_returncode") == 0,
        "vlm_device": vlm_device_ok,
    }
    return {
        "schema_version": P2_ACCEPTANCE_SCHEMA,
        "kind": "runtime_preflight",
        "runtime": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
            "is_windows": os.name == "nt",
        },
        "checks": checks,
        "ready": all(checks.values()),
        "providers": {
            "ASR": {
                "provider": "faster-whisper",
                "model": asr.model_name,
                "device_requested": asr.requested_device,
                "compute_type_requested": asr.requested_compute_type,
                "package_available": asr_package,
                "model_cache": asr.download_root,
            },
            "OCR": {
                "provider": "rapidocr",
                "model": ocr.model_name,
                "device_requested": ocr.requested_device,
                "package_available": ocr_package,
                "opencv_available": cv2_package,
                "sample_interval_us": ocr.sample_interval_us,
                "max_frames_per_shot": ocr.max_frames_per_shot,
            },
            "VLM": vlm_runtime,
        },
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
        "nvidia": nvidia,
        "note": "Preflight checks current Fast Grounded runtime presence only; it is not a real-video quality or performance PASS.",
    }


def _structural_assessment(
    run: BreakdownRun,
    *,
    shot_count: int,
    statuses: Mapping[str, Any],
    counts: Mapping[str, Any],
) -> StructuralAssessment:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    add("run_ready", run.status in READY_RUN_STATUSES, run.status)
    for component in ("ASR", "OCR", "VLM"):
        entry = statuses.get(component)
        valid = isinstance(entry, Mapping)
        add(f"{component.lower()}_sidecar_registered", valid, dict(entry) if valid else None)
        if valid:
            fingerprint = str(entry.get("fingerprint") or "")
            add(f"{component.lower()}_fingerprint", len(fingerprint) == 64, fingerprint)
    vlm = statuses.get("VLM") if isinstance(statuses.get("VLM"), Mapping) else {}
    add("vlm_ready", vlm.get("status") == "READY", vlm.get("status"))
    fusion = statuses.get("FUSION") if isinstance(statuses.get("FUSION"), Mapping) else {}
    add("fusion_ready", fusion.get("status") in {"READY", "READY_WITH_WARNINGS"}, fusion.get("status"))
    draft_shots = counts.get("shot")
    add("full_shot_draft_coverage", draft_shots == shot_count, {"source_shots": shot_count, "draft_shots": draft_shots})
    return StructuralAssessment(
        passed=all(item["passed"] for item in checks),
        checks=tuple(checks),
    )


def normalize_human_review(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    raw_scores = value.get("scores")
    if not isinstance(raw_scores, Mapping):
        raise BreakdownP2AcceptanceError("human review 必须包含 scores object")
    scores: dict[str, float | None] = {}
    for key in ALL_REVIEW_KEYS:
        raw = raw_scores.get(key)
        if raw is None:
            scores[key] = None
            continue
        try:
            score = float(raw)
        except (TypeError, ValueError) as exc:
            raise BreakdownP2AcceptanceError(f"human review score {key} 必须是 0..5") from exc
        if not 0.0 <= score <= 5.0:
            raise BreakdownP2AcceptanceError(f"human review score {key} 必须是 0..5")
        scores[key] = score
    not_applicable_raw = value.get("not_applicable")
    not_applicable = [str(item) for item in not_applicable_raw] if isinstance(not_applicable_raw, list) else []
    invalid_na = [item for item in not_applicable if item not in ALL_REVIEW_KEYS]
    if invalid_na:
        raise BreakdownP2AcceptanceError(f"未知 not_applicable review key: {', '.join(invalid_na)}")
    blocking_raw = value.get("blocking_issues")
    blocking = [str(item).strip() for item in blocking_raw if str(item).strip()] if isinstance(blocking_raw, list) else []
    return {
        "reviewer": str(value.get("reviewer") or "").strip() or None,
        "scores": scores,
        "not_applicable": sorted(set(not_applicable)),
        "blocking_issues": blocking,
        "notes": str(value.get("notes") or "").strip() or None,
    }


def evaluate_acceptance(
    structural: StructuralAssessment,
    human_review: Mapping[str, Any] | None,
) -> dict[str, Any]:
    review = normalize_human_review(human_review)
    if not structural.passed:
        return {
            "status": "STRUCTURAL_FAIL",
            "human_review_complete": False,
            "average_score": None,
            "minimum_score": None,
            "threshold": MIN_ACCEPTANCE_SCORE,
        }
    if review is None:
        return {
            "status": "NEEDS_HUMAN_REVIEW",
            "human_review_complete": False,
            "average_score": None,
            "minimum_score": None,
            "threshold": MIN_ACCEPTANCE_SCORE,
        }

    not_applicable = set(review["not_applicable"])
    required = [key for key in CORE_REVIEW_KEYS if key not in not_applicable]
    if "ocr_text" not in not_applicable:
        required.append("ocr_text")
    score_values = [review["scores"].get(key) for key in required]
    complete = all(score is not None for score in score_values)
    numeric = [float(score) for score in score_values if score is not None]
    average = sum(numeric) / len(numeric) if numeric else None
    minimum = min(numeric) if numeric else None
    if review["blocking_issues"]:
        status = "NEEDS_TUNING"
    elif not complete:
        status = "NEEDS_HUMAN_REVIEW"
    elif minimum is not None and minimum >= MIN_ACCEPTANCE_SCORE:
        status = "PASS"
    else:
        status = "NEEDS_TUNING"
    return {
        "status": status,
        "human_review_complete": complete,
        "average_score": round(average, 4) if average is not None else None,
        "minimum_score": minimum,
        "threshold": MIN_ACCEPTANCE_SCORE,
    }


def build_acceptance_report(
    run_id: str,
    *,
    human_review: Mapping[str, Any] | None = None,
    include_preflight: bool = True,
) -> dict[str, Any]:
    """Build a report from an already completed Run; never rerun Providers implicitly."""

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")
        shot_count = int(session.scalar(
            select(func.count(ShotRevisionItem.id)).where(ShotRevisionItem.revision_id == run.source_shot_revision_id)
        ) or 0)
        statuses = _json_object(run.component_status_json)
        providers = _json_object(run.provider_metadata_json)
        counts = _json_object(run.counts_json)
        warnings = _json_object(run.warning_json)
        structural = _structural_assessment(
            run,
            shot_count=shot_count,
            statuses=statuses,
            counts=counts,
        )
        normalized_review = normalize_human_review(human_review)
        assessment = evaluate_acceptance(structural, normalized_review)
        report = {
            "schema_version": P2_ACCEPTANCE_SCHEMA,
            "version": P2_ACCEPTANCE_VERSION,
            "kind": "real_video_acceptance",
            "generated_at": studio_v2.utcnow().isoformat(),
            "run": {
                "run_id": run.id,
                "project_id": run.project_id,
                "episode_id": run.episode_id,
                "source_shot_revision_id": run.source_shot_revision_id,
                "pipeline_profile": run.pipeline_profile,
                "status": run.status,
                "source_shot_count": shot_count,
                "counts": counts,
                "warnings": warnings,
            },
            "component_status": statuses,
            "provider_metadata": providers,
            "structural": {
                "passed": structural.passed,
                "checks": list(structural.checks),
            },
            "human_review": normalized_review,
            "assessment": assessment,
            "quality_rule": {
                "score_scale": "0..5",
                "minimum_each_required_score": MIN_ACCEPTANCE_SCORE,
                "required_core_scores": list(CORE_REVIEW_KEYS),
                "ocr_may_be_not_applicable": True,
                "blocking_issue_prevents_pass": True,
            },
            "note": "PASS requires structural success plus explicit human review; machine metrics alone never claim model quality.",
        }
    if include_preflight:
        report["runtime_preflight"] = collect_p2_runtime_preflight()
    return report


def default_acceptance_path(report: Mapping[str, Any]) -> Path:
    run = report.get("run")
    if not isinstance(run, Mapping):
        raise BreakdownP2AcceptanceError("acceptance report 缺少 run metadata")
    project_id = str(run.get("project_id") or "")
    episode_id = str(run.get("episode_id") or "")
    run_id = str(run.get("run_id") or "")
    if not project_id or not episode_id or not run_id:
        raise BreakdownP2AcceptanceError("acceptance report run metadata 不完整")
    return (
        studio_v2.episode_dir(project_id, episode_id)
        / "breakdown"
        / run_id
        / "acceptance"
        / f"p2-acceptance-{run_id}.json"
    )


def write_acceptance_report(
    report: Mapping[str, Any],
    *,
    output_path: str | Path | None = None,
) -> Path:
    path = Path(output_path).expanduser() if output_path else default_acceptance_path(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(dict(report), ensure_ascii=False, indent=2, sort_keys=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(serialized, encoding="utf-8")
    os.replace(temp, path)
    return path


def compare_acceptance_reports(reports: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Rank already generated reports; comparison never reruns or republishes Breakdown Runs."""

    rank = {"PASS": 0, "NEEDS_TUNING": 1, "NEEDS_HUMAN_REVIEW": 2, "STRUCTURAL_FAIL": 3}
    summaries: list[dict[str, Any]] = []
    for report in reports:
        run = report.get("run") if isinstance(report.get("run"), Mapping) else {}
        assessment = report.get("assessment") if isinstance(report.get("assessment"), Mapping) else {}
        summaries.append({
            "run_id": run.get("run_id"),
            "episode_id": run.get("episode_id"),
            "pipeline_profile": run.get("pipeline_profile"),
            "status": assessment.get("status"),
            "average_score": assessment.get("average_score"),
            "minimum_score": assessment.get("minimum_score"),
            "providers": report.get("provider_metadata"),
        })
    return sorted(
        summaries,
        key=lambda item: (
            rank.get(str(item.get("status")), 99),
            -(float(item["average_score"]) if item.get("average_score") is not None else -1.0),
            str(item.get("run_id") or ""),
        ),
    )
