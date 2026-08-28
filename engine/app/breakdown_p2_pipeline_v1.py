"""Breakdown-first Phase P2 production orchestration.

Runs the frozen P2 chain in one place:
PROCESSING BreakdownRun -> ASR -> OCR -> VLM -> deterministic Fusion -> P1 validator/publish.

This module owns execution order and failure closure only. Providers keep their own Evidence
contracts, Fusion keeps semantic Draft construction, and no P2 stage may create Final assets.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Mapping, Sequence

from engine.app import breakdown_p2_fusion_v1 as fusion
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_service_v1, studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun
from engine.app.breakdown_p2_asr_v1 import FasterWhisperASRProvider
from engine.app.breakdown_p2_ocr_v1 import RapidOCROCRProvider
from engine.app.breakdown_p2_vlm_v1 import Qwen3VLSemanticProvider

P2_PIPELINE_PROFILE = "breakdown-p2-full-v1"
P2_PIPELINE_VERSION = "1"
P2_PROVIDER_ORDER = ("ASR", "OCR", "VLM")
_ALLOWED_DEGRADED = {"NO_EVIDENCE", "NOT_AVAILABLE"}

ProgressCallback = Callable[[float, str, str], None]


class BreakdownP2PipelineError(RuntimeError):
    """P2 full-pipeline execution cannot safely continue."""


@dataclass(frozen=True)
class ProviderExecution:
    component: str
    status: str
    provider: str
    model: str
    artifact: p2.P2EvidenceArtifact
    elapsed_seconds: float
    warnings: tuple[str, ...]


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _default_providers() -> tuple[p2.BreakdownP2Provider, ...]:
    # Construct lazily so importing FastAPI does not load any model runtime.
    return (
        FasterWhisperASRProvider(),
        RapidOCROCRProvider(),
        Qwen3VLSemanticProvider(),
    )


def _provider_map(
    providers: Sequence[p2.BreakdownP2Provider] | None,
) -> dict[str, p2.BreakdownP2Provider]:
    provided = tuple(providers) if providers is not None else _default_providers()
    result: dict[str, p2.BreakdownP2Provider] = {}
    for provider in provided:
        component = str(provider.component).strip().upper()
        if component not in P2_PROVIDER_ORDER:
            raise BreakdownP2PipelineError(f"P2 pipeline 收到未知 Provider component: {provider.component}")
        if component in result:
            raise BreakdownP2PipelineError(f"P2 pipeline component 重复: {component}")
        result[component] = provider
    missing = [component for component in P2_PROVIDER_ORDER if component not in result]
    if missing:
        raise BreakdownP2PipelineError(f"P2 pipeline 缺少 Provider: {', '.join(missing)}")
    return result


def _report(progress: ProgressCallback | None, percent: float, stage: str, message: str) -> None:
    if progress is not None:
        progress(max(0.0, min(100.0, float(percent))), stage, message)


def _pipeline_state(
    run_id: str,
    *,
    status: str,
    stage: str,
    executions: Sequence[ProviderExecution],
    error_type: str | None = None,
) -> None:
    """Persist non-secret orchestration provenance while the Run is still PROCESSING."""

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None or run.status != "PROCESSING":
            return
        statuses = _json_object(run.component_status_json)
        statuses["P2_PIPELINE"] = {
            "status": status,
            "profile": P2_PIPELINE_PROFILE,
            "version": P2_PIPELINE_VERSION,
            "stage": stage,
            "provider_order": list(P2_PROVIDER_ORDER),
            "executed_components": [item.component for item in executions],
            "error_type": error_type,
        }
        providers_meta = _json_object(run.provider_metadata_json)
        providers_meta["p2_pipeline"] = {
            "profile": P2_PIPELINE_PROFILE,
            "version": P2_PIPELINE_VERSION,
            "provider_order": list(P2_PROVIDER_ORDER),
            "timings_seconds": {
                item.component: round(item.elapsed_seconds, 6)
                for item in executions
            },
        }
        run.component_status_json = _json_text(statuses)
        run.provider_metadata_json = _json_text(providers_meta)
        session.commit()


def _safe_fail_processing(run_id: str, exc: BaseException, executions: Sequence[ProviderExecution]) -> None:
    """Fail only a still-PROCESSING Run; preserve STALE/validator/fusion terminal truth."""

    try:
        _pipeline_state(
            run_id,
            status="FAILED",
            stage="failed",
            executions=executions,
            error_type=type(exc).__name__,
        )
        with studio_v2.get_session() as session:
            run = session.get(BreakdownRun, run_id)
            should_fail = run is not None and run.status == "PROCESSING"
        if should_fail:
            breakdown_service_v1.fail_breakdown_run(
                run_id,
                f"P2 pipeline failed: {type(exc).__name__}: {exc}",
            )
    except Exception:
        return


def _execute_provider(run_id: str, provider: p2.BreakdownP2Provider) -> ProviderExecution:
    """Execute one Provider through the P2.1 persistence/provenance boundary and keep its Result."""

    context = p2.load_p2_run_context(run_id)
    expected_component = str(provider.component).strip().upper()
    started = time.perf_counter()
    result = provider.analyze(context)
    elapsed = max(0.0, time.perf_counter() - started)
    if result.component.strip().upper() != expected_component:
        raise BreakdownP2PipelineError("Provider.component 与 ProviderResult.component 不一致")
    p2.validate_provider_result(context, result)
    artifact = p2.persist_provider_result(context, result)
    p2.record_component_artifact(context, result, artifact)
    return ProviderExecution(
        component=expected_component,
        status=result.status,
        provider=result.provider,
        model=result.model,
        artifact=artifact,
        elapsed_seconds=elapsed,
        warnings=tuple(result.warnings),
    )


def _assert_component_can_continue(execution: ProviderExecution) -> None:
    status = execution.status
    component = execution.component
    if status in {"FAILED", "NOT_CONFIGURED"}:
        raise BreakdownP2PipelineError(f"{component} Provider status={status}，P2 pipeline fail closed")
    if component == "VLM" and status != "READY":
        raise BreakdownP2PipelineError(f"VLM Provider status={status}；完整匿名 Draft 要求 READY VLM semantics")
    if component in {"ASR", "OCR"} and status not in ({"READY"} | _ALLOWED_DEGRADED):
        raise BreakdownP2PipelineError(f"{component} Provider status={status} 不允许继续 Fusion")


def run_breakdown_p2_run(
    run_id: str,
    *,
    providers: Sequence[p2.BreakdownP2Provider] | None = None,
    progress: ProgressCallback | None = None,
) -> BreakdownRun:
    """Execute ASR -> OCR -> VLM -> Fusion for an existing PROCESSING BreakdownRun."""

    provider_by_component = _provider_map(providers)
    executions: list[ProviderExecution] = []
    # Loading the context here is also the initial current-Revision/status gate.
    p2.load_p2_run_context(run_id)
    _pipeline_state(run_id, status="PROCESSING", stage="prepare", executions=executions)
    _report(progress, 0.0, "breakdown_prepare", "准备匿名 AI 拉片")

    ranges = {
        "ASR": (5.0, 25.0),
        "OCR": (25.0, 45.0),
        "VLM": (45.0, 90.0),
    }
    labels = {
        "ASR": "识别对白与语音时间",
        "OCR": "识别字幕与画面文字",
        "VLM": "理解场景、人物、动作与关键道具",
    }

    try:
        for component in P2_PROVIDER_ORDER:
            start_percent, end_percent = ranges[component]
            _report(progress, start_percent, f"breakdown_{component.lower()}", labels[component])
            execution = _execute_provider(run_id, provider_by_component[component])
            executions.append(execution)
            _pipeline_state(
                run_id,
                status="PROCESSING",
                stage=component.lower(),
                executions=executions,
            )
            _assert_component_can_continue(execution)
            suffix = ""
            if execution.status in _ALLOWED_DEGRADED:
                suffix = f"（{execution.status}，继续保守 Fusion）"
            _report(
                progress,
                end_percent,
                f"breakdown_{component.lower()}",
                f"{labels[component]}完成{suffix}",
            )

        _pipeline_state(
            run_id,
            status="READY_TO_FUSE",
            stage="fusion",
            executions=executions,
        )
        _report(progress, 90.0, "breakdown_fusion", "融合 ASR / OCR / VLM，生成结构化匿名 Draft")
        published = fusion.fuse_breakdown_run(run_id)
        _report(progress, 100.0, "breakdown_ready", "匿名结构化拉片完成")
        return published
    except Exception as exc:
        _safe_fail_processing(run_id, exc, executions)
        raise


def run_episode_breakdown_p2(
    episode_id: str,
    *,
    providers: Sequence[p2.BreakdownP2Provider] | None = None,
    progress: ProgressCallback | None = None,
) -> BreakdownRun:
    """Create a fresh frozen BreakdownRun for the Episode and execute the complete P2 chain."""

    initial_component_status = {
        "P2_PIPELINE": {
            "status": "PROCESSING",
            "profile": P2_PIPELINE_PROFILE,
            "version": P2_PIPELINE_VERSION,
            "stage": "created",
            "provider_order": list(P2_PROVIDER_ORDER),
        }
    }
    initial_provider_metadata = {
        "p2_pipeline": {
            "profile": P2_PIPELINE_PROFILE,
            "version": P2_PIPELINE_VERSION,
            "provider_order": list(P2_PROVIDER_ORDER),
        }
    }
    run = breakdown_service_v1.create_breakdown_run(
        episode_id,
        pipeline_profile=P2_PIPELINE_PROFILE,
        component_status=initial_component_status,
        provider_metadata=initial_provider_metadata,
    )
    return run_breakdown_p2_run(run.id, providers=providers, progress=progress)
