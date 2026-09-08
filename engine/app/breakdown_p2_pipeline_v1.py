"""Phase P2 orchestration with whole-Episode understanding before semantic per-Shot breakdown.

Business order:

    ASR -> OCR -> Gemini Episode Intelligence -> Qwen3.8 per-Shot semantics -> deterministic Fusion

Shot boundaries already exist only as frozen time/reference anchors.  They are not treated as prior
semantic understanding.  Gemini first establishes the source script/story, character candidates,
relationships, scenes and props from the complete Episode; the Qwen pass then refines visual and
directing facts for each Shot against that Source Bible.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import time
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence

from engine.app import breakdown_p2_fusion_episode_v6 as fusion
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_service_v1, studio_v2
from engine.app import source_episode_understanding_provider_v1 as episode_understanding
from engine.app.breakdown_models_v1 import BreakdownRun
from engine.app.breakdown_p2_asr_v1 import FasterWhisperASRProvider
from engine.app.breakdown_p2_ocr_runtime_v1 import RapidOCROCRProvider
from engine.app.source_video_understanding_provider_v1 import Qwen38VideoUnderstandingProvider

P2_PIPELINE_PROFILE = "breakdown-p2-whole-episode-first-v2"
P2_PIPELINE_VERSION = "2"
P2_LOCAL_PROVIDER_ORDER = ("ASR", "OCR", "VLM")
P2_EXECUTION_ORDER = ("ASR", "OCR", "EPISODE_INTELLIGENCE", "VLM")
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


@dataclass(frozen=True)
class EpisodeIntelligenceExecution:
    status: str
    provider: str
    model: str
    artifact: episode_understanding.EpisodeIntelligenceArtifact | None
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
    # Construct lazily so importing FastAPI does not load any local model runtime.
    return (
        FasterWhisperASRProvider(),
        RapidOCROCRProvider(),
        Qwen38VideoUnderstandingProvider(),
    )


def _default_episode_provider() -> episode_understanding.SourceEpisodeUnderstandingProvider:
    # External provider object construction does not make a remote request; analyze() does.
    return episode_understanding.Gemini31ProEpisodeUnderstandingProvider()


def _provider_map(
    providers: Sequence[p2.BreakdownP2Provider] | None,
) -> dict[str, p2.BreakdownP2Provider]:
    provided = tuple(providers) if providers is not None else _default_providers()
    result: dict[str, p2.BreakdownP2Provider] = {}
    for provider in provided:
        component = str(provider.component).strip().upper()
        if component not in P2_LOCAL_PROVIDER_ORDER:
            raise BreakdownP2PipelineError(f"P2 pipeline 收到未知 Provider component: {provider.component}")
        if component in result:
            raise BreakdownP2PipelineError(f"P2 pipeline component 重复: {component}")
        result[component] = provider
    missing = [component for component in P2_LOCAL_PROVIDER_ORDER if component not in result]
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
    episode_execution: EpisodeIntelligenceExecution | None = None,
    error_type: str | None = None,
) -> None:
    """Persist non-secret orchestration provenance while the Run is still PROCESSING."""

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None or run.status != "PROCESSING":
            return
        executed_components = [item.component for item in executions]
        if episode_execution is not None:
            # Preserve business execution order in the provenance view.
            insert_at = min(2, len(executed_components))
            executed_components.insert(insert_at, "EPISODE_INTELLIGENCE")
        statuses = _json_object(run.component_status_json)
        statuses["P2_PIPELINE"] = {
            "status": status,
            "profile": P2_PIPELINE_PROFILE,
            "version": P2_PIPELINE_VERSION,
            "stage": stage,
            "provider_order": list(P2_EXECUTION_ORDER),
            "executed_components": executed_components,
            "error_type": error_type,
        }
        providers_meta = _json_object(run.provider_metadata_json)
        timings = {
            item.component: round(item.elapsed_seconds, 6)
            for item in executions
        }
        if episode_execution is not None:
            timings["EPISODE_INTELLIGENCE"] = round(episode_execution.elapsed_seconds, 6)
        providers_meta["p2_pipeline"] = {
            "profile": P2_PIPELINE_PROFILE,
            "version": P2_PIPELINE_VERSION,
            "provider_order": list(P2_EXECUTION_ORDER),
            "timings_seconds": timings,
        }
        run.component_status_json = _json_text(statuses)
        run.provider_metadata_json = _json_text(providers_meta)
        session.commit()


def _safe_fail_processing(
    run_id: str,
    exc: BaseException,
    executions: Sequence[ProviderExecution],
    episode_execution: EpisodeIntelligenceExecution | None,
) -> None:
    try:
        _pipeline_state(
            run_id,
            status="FAILED",
            stage="failed",
            executions=executions,
            episode_execution=episode_execution,
            error_type=type(exc).__name__,
        )
        with studio_v2.get_session() as session:
            run = session.get(BreakdownRun, run_id)
            should_fail = run is not None and run.status == "PROCESSING"
        if should_fail:
            breakdown_service_v1.fail_breakdown_run(
                run_id,
                f"P2 pipeline failed: {type(exc).__name__}",
            )
    except Exception:
        return


def _execute_provider(run_id: str, provider: p2.BreakdownP2Provider) -> ProviderExecution:
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


def _episode_provider_context(context: p2.P2RunContext) -> Any:
    """Add immutable original Episode media anchors without expanding the legacy P2 dataclass."""

    with studio_v2.get_session() as session:
        episode = session.get(studio_v2.Episode, context.episode_id)
        if episode is None:
            raise BreakdownP2PipelineError("Episode 不存在，无法执行整片理解")
        values = dict(vars(context))
        values["source_video_path"] = episode.source_path
        values["source_sha256"] = episode.source_sha256
        return SimpleNamespace(**values)


def _execute_episode_intelligence(
    run_id: str,
    provider: episode_understanding.SourceEpisodeUnderstandingProvider,
    evidence_artifacts: Sequence[p2.P2EvidenceArtifact],
) -> EpisodeIntelligenceExecution:
    base_context = p2.load_p2_run_context(run_id)
    context = _episode_provider_context(base_context)
    started = time.perf_counter()
    result = provider.analyze(context, evidence_artifacts)
    elapsed = max(0.0, time.perf_counter() - started)
    artifact: episode_understanding.EpisodeIntelligenceArtifact | None = None
    if result.status == "READY":
        artifact = episode_understanding.persist_episode_intelligence(context, result)
    return EpisodeIntelligenceExecution(
        status=result.status,
        provider=result.provider,
        model=result.model,
        artifact=artifact,
        elapsed_seconds=elapsed,
        warnings=tuple(result.warnings),
    )


def _provider_failure_detail(warnings: Sequence[str]) -> str:
    for warning in warnings:
        text = " ".join(str(warning).strip().split())
        if text:
            return text[:700]
    return ""


def _assert_component_can_continue(execution: ProviderExecution) -> None:
    status = execution.status
    component = execution.component
    if status in {"FAILED", "NOT_CONFIGURED"}:
        detail = _provider_failure_detail(execution.warnings)
        suffix = f"；{detail}" if detail else ""
        raise BreakdownP2PipelineError(
            f"{component} Provider status={status}，P2 pipeline fail closed{suffix}"
        )
    if component == "VLM" and status != "READY":
        detail = _provider_failure_detail(execution.warnings)
        suffix = f"；{detail}" if detail else ""
        raise BreakdownP2PipelineError(
            f"VLM Provider status={status}；逐镜语义需要 READY visual semantics{suffix}"
        )
    if component in {"ASR", "OCR"} and status not in ({"READY"} | _ALLOWED_DEGRADED):
        detail = _provider_failure_detail(execution.warnings)
        suffix = f"；{detail}" if detail else ""
        raise BreakdownP2PipelineError(
            f"{component} Provider status={status} 不允许继续整片理解{suffix}"
        )


def _assert_episode_can_continue(execution: EpisodeIntelligenceExecution) -> None:
    if execution.status == "READY" and execution.artifact is not None:
        return
    detail = _provider_failure_detail(execution.warnings)
    suffix = f"；{detail}" if detail else ""
    if execution.status == "NOT_CONFIGURED":
        raise BreakdownP2PipelineError(
            "Gemini 整片理解未配置，逐镜拉片不会偷偷降级到小模型"
            f"{suffix}"
        )
    raise BreakdownP2PipelineError(
        f"Gemini Episode Intelligence status={execution.status}，禁止开始逐镜语义拉片{suffix}"
    )


def _bind_episode_intelligence_to_vlm(
    provider: p2.BreakdownP2Provider,
    execution: EpisodeIntelligenceExecution,
) -> None:
    artifact = execution.artifact
    if artifact is None:
        raise BreakdownP2PipelineError("逐镜 VLM 缺少 Episode Intelligence artifact")
    setter = getattr(provider, "set_episode_intelligence_artifact", None)
    if not callable(setter):
        raise BreakdownP2PipelineError(
            "当前 VLM Provider 不支持 Episode Intelligence 上下文，禁止退回旧的无上下文逐镜拉片"
        )
    setter(artifact.path, artifact.fingerprint)


def run_breakdown_p2_run(
    run_id: str,
    *,
    providers: Sequence[p2.BreakdownP2Provider] | None = None,
    episode_provider: episode_understanding.SourceEpisodeUnderstandingProvider | None = None,
    progress: ProgressCallback | None = None,
) -> BreakdownRun:
    """Execute whole-Episode-first P2 for an existing PROCESSING BreakdownRun."""

    provider_by_component = _provider_map(providers)
    episode_provider = episode_provider or _default_episode_provider()
    executions: list[ProviderExecution] = []
    episode_execution: EpisodeIntelligenceExecution | None = None
    initial_context = p2.load_p2_run_context(run_id)
    _pipeline_state(run_id, status="PROCESSING", stage="prepare", executions=executions)
    _report(progress, 0.0, "breakdown_prepare", "准备整片理解与逐镜拉片")

    ranges = {
        "ASR": (5.0, 20.0),
        "OCR": (20.0, 35.0),
        "EPISODE_INTELLIGENCE": (35.0, 60.0),
        "VLM": (60.0, 90.0),
    }
    labels = {
        "ASR": "提取整集原始对白与语音时间证据",
        "OCR": "提取整集字幕与画面文字证据",
        "EPISODE_INTELLIGENCE": "Gemini 分析整集剧本、角色、关系、场景和道具",
        "VLM": "带整集 Source Bible 做逐镜动作、表演与镜头语言拉片",
    }

    try:
        # 1) Evidence owners first. They feed Gemini, but are not themselves semantic Shot analysis.
        for component in ("ASR", "OCR"):
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
            suffix = f"（{execution.status}，保留可用证据继续）" if execution.status in _ALLOWED_DEGRADED else ""
            _report(progress, end_percent, f"breakdown_{component.lower()}", f"{labels[component]}完成{suffix}")

        # 2) Whole Episode must be understood before any semantic per-Shot VLM pass.
        start_percent, end_percent = ranges["EPISODE_INTELLIGENCE"]
        _report(progress, start_percent, "breakdown_episode_intelligence", labels["EPISODE_INTELLIGENCE"])
        episode_execution = _execute_episode_intelligence(
            run_id,
            episode_provider,
            [item.artifact for item in executions if item.component in {"ASR", "OCR"}],
        )
        _pipeline_state(
            run_id,
            status="PROCESSING",
            stage="episode_intelligence",
            executions=executions,
            episode_execution=episode_execution,
        )
        _assert_episode_can_continue(episode_execution)
        _report(progress, end_percent, "breakdown_episode_intelligence", "整集 Source Bible 已建立")

        # 3) Only now may exact per-Shot semantic/directing analysis run.
        _bind_episode_intelligence_to_vlm(provider_by_component["VLM"], episode_execution)
        start_percent, end_percent = ranges["VLM"]
        _report(progress, start_percent, "breakdown_vlm", labels["VLM"])
        vlm_execution = _execute_provider(run_id, provider_by_component["VLM"])
        executions.append(vlm_execution)
        _pipeline_state(
            run_id,
            status="PROCESSING",
            stage="vlm",
            executions=executions,
            episode_execution=episode_execution,
        )
        _assert_component_can_continue(vlm_execution)
        _report(progress, end_percent, "breakdown_vlm", "逐镜语义拉片完成")

        _pipeline_state(
            run_id,
            status="READY_TO_FUSE",
            stage="fusion",
            executions=executions,
            episode_execution=episode_execution,
        )
        _report(progress, 90.0, "breakdown_fusion", "融合整集 Source Bible 与逐镜事实，生成结构化 Source Draft")
        from engine.app import source_presence_audit_v1 as presence_audit
        vlm_artifact = next(item.artifact for item in executions if item.component == "VLM")
        audits = presence_audit.inspect_artifact(initial_context, vlm_artifact)
        published = fusion.fuse_breakdown_run(run_id)
        presence_audit.publish(
            initial_context.project_id,
            initial_context.episode_id,
            run_id,
            initial_context.source_shot_revision_id,
            audits,
        )
        _report(progress, 100.0, "breakdown_ready", "整片理解 + 逐镜拉片完成")
        return published
    except Exception as exc:
        _safe_fail_processing(run_id, exc, executions, episode_execution)
        raise


def run_episode_breakdown_p2(
    episode_id: str,
    *,
    providers: Sequence[p2.BreakdownP2Provider] | None = None,
    episode_provider: episode_understanding.SourceEpisodeUnderstandingProvider | None = None,
    progress: ProgressCallback | None = None,
) -> BreakdownRun:
    """Create a fresh frozen BreakdownRun and execute whole-Episode-first P2."""

    initial_component_status = {
        "P2_PIPELINE": {
            "status": "PROCESSING",
            "profile": P2_PIPELINE_PROFILE,
            "version": P2_PIPELINE_VERSION,
            "stage": "created",
            "provider_order": list(P2_EXECUTION_ORDER),
        }
    }
    initial_provider_metadata = {
        "p2_pipeline": {
            "profile": P2_PIPELINE_PROFILE,
            "version": P2_PIPELINE_VERSION,
            "provider_order": list(P2_EXECUTION_ORDER),
            "fusion_profile": fusion.FUSION_PROFILE,
            "episode_understanding_profile": episode_understanding.EPISODE_INTELLIGENCE_PROFILE,
        }
    }
    run = breakdown_service_v1.create_breakdown_run(
        episode_id,
        pipeline_profile=P2_PIPELINE_PROFILE,
        component_status=initial_component_status,
        provider_metadata=initial_provider_metadata,
    )
    return run_breakdown_p2_run(
        run.id,
        providers=providers,
        episode_provider=episode_provider,
        progress=progress,
    )
