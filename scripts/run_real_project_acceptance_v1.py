#!/usr/bin/env python3
"""Local real-project end-to-end acceptance orchestrator.

This is an acceptance runner, not a new production pipeline. It calls the existing public
FastAPI workflow only:

    auto-remake-prepare -> H3 generation/QC/selection -> postproduction/EpisodeOutput

The runner is resumable: it inspects current product truth first and starts only the first
missing production stage. Any genuine ReviewIssue stops the run. It never edits business
truth, never marks review items resolved/ignored, and never upgrades real-project acceptance
by itself.

P1 dialogue acceptance is explicit: the current SourceDramaSnapshot must expose canonical
complete utterances plus Shot projections, and the current TargetDialogue bundle must contain
exactly one row per canonical utterance. Projection count may be greater than utterance count;
it must never inflate TargetDialogue count. FlowState must report that same canonical current
TargetDialogue count, so retained historical rows can never masquerade as current progress.
All current target dialogue audio must be READY before the generation/postproduction chain
can be accepted.

Default mode is read-only. Pass ``--run`` to start missing production tasks sequentially.
The final successful state is only ``READY_FOR_MANUAL_ACCEPTANCE``: a human still has to
watch/listen to the exported episode and accept identity, scene, action/camera, dialogue,
lip-sync, source-language leakage, background audio and subtitle timing.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


TERMINAL_TASKS = {"READY", "READY_WITH_WARNINGS", "FAILED", "CANCELLED"}
EXIT_CODES = {
    "READY_FOR_MANUAL_ACCEPTANCE": 0,
    "NEEDS_REVIEW": 2,
    "RUNTIME_BLOCKED": 3,
    "PIPELINE_FAILED": 4,
    "NOT_READY": 5,
}


class AcceptanceError(RuntimeError):
    pass


@dataclass
class HttpClient:
    base_url: str
    timeout: float = 30.0

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(detail)
                message = str(body.get("detail") or detail) if isinstance(body, dict) else detail
            except json.JSONDecodeError:
                message = detail
            raise AcceptanceError(f"HTTP {exc.code} {method} {path}: {message}") from exc
        except urllib.error.URLError as exc:
            raise AcceptanceError(f"cannot reach {url}: {exc}") from exc
        if not raw.strip():
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AcceptanceError(f"invalid JSON from {method} {path}") from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, payload)


def _probe_openai_vlm(base_url: str, model: str, timeout: float = 5.0) -> dict[str, Any]:
    """Prove the configured OpenAI-compatible VLM endpoint is reachable.

    Model lists are informational only. Some local servers expose a canonical model path while
    accepting the configured alias used by production requests, so an exact `/models` ID mismatch
    must not create a false runtime blocker.
    """

    base = base_url.strip().rstrip("/")
    clean_model = model.strip()
    if not base:
        return {
            "ready": False,
            "reachable": False,
            "base_url": None,
            "model": clean_model or None,
            "error": "AI_DRAMA_VLM_BASE_URL 未配置",
        }
    if not clean_model:
        return {
            "ready": False,
            "reachable": False,
            "base_url": base,
            "model": None,
            "error": "AI_DRAMA_VLM_MODEL 未配置",
        }
    url = f"{base}/models"
    headers = {"Authorization": f"Bearer {os.getenv('AI_DRAMA_VLM_API_KEY', 'EMPTY').strip() or 'EMPTY'}"}
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
        payload = json.loads(raw)
        ids = {
            str(item.get("id") or "")
            for item in (payload.get("data") or [])
            if isinstance(item, dict)
        } if isinstance(payload, dict) else set()
        available = sorted(value for value in ids if value)
        return {
            "ready": True,
            "reachable": True,
            "base_url": base,
            "model": clean_model,
            "available_models": available,
            "model_list_match": not available or clean_model in ids,
            "error": None,
        }
    except Exception as exc:
        return {
            "ready": False,
            "reachable": False,
            "base_url": base,
            "model": clean_model,
            "error": str(exc),
        }


def collect_runtime_status(client: HttpClient, *, vlm_base_url: str, vlm_model: str) -> dict[str, dict[str, Any]]:
    health = client.get("/api/health")
    h3 = client.get("/api/h3/runtime")
    tts = client.get("/api/tts/runtime-status")
    lip = client.get("/api/lip-sync/runtime")
    background = client.get("/api/background-audio/runtime")
    vlm = _probe_openai_vlm(vlm_base_url, vlm_model)
    return {
        "backend": {"ready": bool(isinstance(health, dict) and health.get("status") == "ok"), "raw": health},
        "h3_fl2va": {**(h3.get("fl2va") or {}), "ready": bool((h3.get("fl2va") or {}).get("ready"))},
        "h3_ref2va": {**(h3.get("ref2va") or {}), "ready": bool((h3.get("ref2va") or {}).get("ready"))},
        "qwen3_vl": vlm,
        "qwen3_tts": {**tts, "ready": bool(tts.get("ready"))},
        "latentsync": {**lip, "ready": bool(lip.get("ready"))},
        "audio_separator": {**background, "ready": bool(background.get("ready"))},
    }


def runtime_blockers(runtimes: dict[str, dict[str, Any]]) -> list[str]:
    # Production can safely fall back to target-dialogue-only audio when the separator is down,
    # but this runner intentionally validates the complete desired local runtime stack.
    required = (
        "backend",
        "h3_fl2va",
        "h3_ref2va",
        "qwen3_vl",
        "qwen3_tts",
        "latentsync",
        "audio_separator",
    )
    return [name for name in required if not bool((runtimes.get(name) or {}).get("ready"))]


def _optional_get(client: HttpClient, path: str) -> tuple[Any | None, str | None]:
    try:
        return client.get(path), None
    except AcceptanceError as exc:
        return None, str(exc)


def collect_project_state(client: HttpClient, project_id: str) -> dict[str, Any]:
    project = client.get(f"/api/projects/{project_id}")
    issues = client.get(f"/api/projects/{project_id}/review-issues?status=OPEN")
    source_snapshot, source_snapshot_error = _optional_get(client, f"/api/projects/{project_id}/source-drama-snapshot")
    target_dialogue, target_dialogue_error = _optional_get(client, f"/api/projects/{project_id}/target-dialogue")
    flow_state, flow_state_error = _optional_get(client, f"/api/projects/{project_id}/flow-state")
    segments, segments_error = _optional_get(client, f"/api/projects/{project_id}/generation-segments")
    quality, quality_error = _optional_get(client, f"/api/projects/{project_id}/h3-quality")
    post, post_error = _optional_get(client, f"/api/projects/{project_id}/postproduction")
    outputs, outputs_error = _optional_get(client, f"/api/projects/{project_id}/outputs")
    return {
        "project": project,
        "review_issues": issues if isinstance(issues, list) else [],
        "source_drama_snapshot": source_snapshot,
        "source_drama_snapshot_error": source_snapshot_error,
        "target_dialogue": target_dialogue,
        "target_dialogue_error": target_dialogue_error,
        "flow_state": flow_state,
        "flow_state_error": flow_state_error,
        "generation_segments": segments,
        "generation_segments_error": segments_error,
        "h3_quality": quality,
        "h3_quality_error": quality_error,
        "postproduction": post,
        "postproduction_error": post_error,
        "outputs": outputs,
        "outputs_error": outputs_error,
    }


def _post_audio_modes(post: dict[str, Any] | None) -> dict[str, int]:
    result: dict[str, int] = {}
    for episode in (post or {}).get("episodes") or []:
        for segment in episode.get("segments") or []:
            mode = str(segment.get("audio_mix_mode") or "UNKNOWN")
            result[mode] = result.get(mode, 0) + 1
    return result


def summarize_state(state: dict[str, Any]) -> dict[str, Any]:
    project = state.get("project") or {}
    source = state.get("source_drama_snapshot") or {}
    target_dialogue = state.get("target_dialogue") or {}
    flow_state = state.get("flow_state") or {}
    segments = state.get("generation_segments") or {}
    quality = state.get("h3_quality") or {}
    post = state.get("postproduction") or {}
    outputs = state.get("outputs") or {}
    issues = state.get("review_issues") or []

    source_present = isinstance(state.get("source_drama_snapshot"), dict)
    target_dialogue_present = isinstance(state.get("target_dialogue"), dict)
    flow_state_present = isinstance(state.get("flow_state"), dict)
    source_dialogue_count = int(source.get("source_dialogue_count") or 0)
    source_projection_count = int(source.get("source_dialogue_projection_count") or 0)
    target_dialogue_count = int(target_dialogue.get("dialogue_count") or 0)
    target_audio_ready_count = int(target_dialogue.get("audio_ready_count") or 0)
    flow_target_dialogue_stage = next((
        item
        for item in flow_state.get("stages") or []
        if isinstance(item, dict)
        and str(item.get("stage_key") or item.get("key") or "") == "target_dialogue"
    ), None)
    flow_target_dialogue_metrics = (flow_target_dialogue_stage or {}).get("metrics") or {}
    flow_target_dialogue_count = int(flow_target_dialogue_metrics.get("dialogue_count") or 0)
    dialogue_contract_current = bool(
        source_present
        and target_dialogue_present
        and target_dialogue_count == source_dialogue_count
        and source_projection_count >= source_dialogue_count
    )
    target_dialogue_audio_current = bool(
        target_dialogue_present and target_audio_ready_count == target_dialogue_count
    )
    flow_target_dialogue_count_current = bool(
        flow_state_present
        and isinstance(flow_target_dialogue_stage, dict)
        and str(flow_target_dialogue_stage.get("validity") or "") == "CURRENT"
        and flow_target_dialogue_count == target_dialogue_count
        and flow_target_dialogue_count == source_dialogue_count
    )

    return {
        "project_id": project.get("id"),
        "project_name": project.get("name"),
        "episode_count": len(project.get("episodes") or []),
        "open_review_count": len(issues),
        "review_types": sorted({str(item.get("issue_type") or "UNKNOWN") for item in issues if isinstance(item, dict)}),
        "source_dialogue_count": source_dialogue_count,
        "source_dialogue_projection_count": source_projection_count,
        "target_dialogue_count": target_dialogue_count,
        "target_dialogue_audio_ready_count": target_audio_ready_count,
        "flow_target_dialogue_count": flow_target_dialogue_count,
        "dialogue_contract_current": dialogue_contract_current,
        "flow_target_dialogue_count_current": flow_target_dialogue_count_current,
        "target_dialogue_audio_current": target_dialogue_audio_current,
        "generation_segment_count": int(segments.get("segment_count") or 0),
        "generation_segment_review_count": int(segments.get("review_count") or 0),
        "generation_segment_waiting_audio_count": int(segments.get("waiting_audio_count") or 0),
        "selected_count": int(quality.get("selected_count") or 0),
        "h3_qc_review_count": int(quality.get("review_count") or 0),
        "h3_qc_waiting_model_count": int(quality.get("waiting_model_count") or 0),
        "postproduction_segment_count": int(post.get("segment_count") or 0),
        "postproduction_succeeded_count": int(post.get("succeeded_count") or 0),
        "postproduction_review_count": int(post.get("review_count") or 0),
        "postproduction_waiting_count": int(post.get("waiting_count") or 0),
        "background_audio_modes": _post_audio_modes(post),
        "episode_output_count": int(outputs.get("episode_count") or 0),
        "episode_output_succeeded_count": int(outputs.get("succeeded_count") or 0),
        "episode_output_waiting_count": int(outputs.get("waiting_count") or 0),
    }


def acceptance_result(summary: dict[str, Any]) -> str:
    if int(summary.get("open_review_count") or 0) > 0:
        return "NEEDS_REVIEW"
    if not bool(summary.get("dialogue_contract_current")):
        return "NOT_READY"
    if not bool(summary.get("flow_target_dialogue_count_current")):
        return "NOT_READY"
    if not bool(summary.get("target_dialogue_audio_current")):
        return "NOT_READY"
    segment_count = int(summary.get("generation_segment_count") or 0)
    episode_count = int(summary.get("episode_count") or 0)
    if segment_count <= 0 or episode_count <= 0:
        return "NOT_READY"
    if int(summary.get("selected_count") or 0) != segment_count:
        return "NOT_READY"
    if int(summary.get("postproduction_succeeded_count") or 0) != segment_count:
        return "NOT_READY"
    if int(summary.get("episode_output_succeeded_count") or 0) != episode_count:
        return "NOT_READY"
    if any(int(summary.get(key) or 0) for key in (
        "generation_segment_review_count",
        "generation_segment_waiting_audio_count",
        "h3_qc_review_count",
        "h3_qc_waiting_model_count",
        "postproduction_review_count",
        "postproduction_waiting_count",
        "episode_output_waiting_count",
    )):
        return "NOT_READY"
    return "READY_FOR_MANUAL_ACCEPTANCE"


def wait_task(client: HttpClient, task: dict[str, Any], *, poll_seconds: float, timeout_seconds: float) -> dict[str, Any]:
    task_id = str(task.get("id") or "")
    if not task_id:
        raise AcceptanceError("task response missing id")
    deadline = time.monotonic() + timeout_seconds
    last_message = ""
    while True:
        current = client.get(f"/api/tasks/{task_id}")
        message = str(current.get("message") or "")
        if message and message != last_message:
            print(f"  [{current.get('status')}] {message}")
            last_message = message
        status = str(current.get("status") or "")
        if status in TERMINAL_TASKS:
            return current
        if time.monotonic() >= deadline:
            raise AcceptanceError(f"task timeout: {task_id}")
        time.sleep(max(0.25, poll_seconds))


def _run_task(client: HttpClient, path: str, *, label: str, poll_seconds: float, timeout_seconds: float) -> dict[str, Any]:
    print(f"\n[{label}] start")
    task = client.post(path)
    finished = wait_task(client, task, poll_seconds=poll_seconds, timeout_seconds=timeout_seconds)
    if finished.get("status") not in {"READY", "READY_WITH_WARNINGS"}:
        raise AcceptanceError(f"{label} failed: {finished.get('error_message') or finished.get('message')}")
    return finished


def _needs_prepare(state: dict[str, Any], summary: dict[str, Any]) -> bool:
    if state.get("source_drama_snapshot") is None or state.get("target_dialogue") is None:
        return True
    if not bool(summary.get("dialogue_contract_current")):
        return True
    if not bool(summary.get("target_dialogue_audio_current")):
        return True
    if state.get("generation_segments") is None:
        return True
    if int(summary.get("generation_segment_count") or 0) <= 0:
        return True
    return any(int(summary.get(key) or 0) > 0 for key in (
        "generation_segment_review_count",
        "generation_segment_waiting_audio_count",
    ))


def run_pipeline(client: HttpClient, project_id: str, *, poll_seconds: float, timeout_seconds: float) -> tuple[str, dict[str, Any]]:
    """Resume from the first missing stage instead of rerunning already-current expensive work."""

    state = collect_project_state(client, project_id)
    summary = summarize_state(state)
    if int(summary["open_review_count"]) > 0:
        return "NEEDS_REVIEW", state

    if _needs_prepare(state, summary):
        _run_task(
            client,
            f"/api/projects/{project_id}/tasks/auto-remake-prepare",
            label="自动准备",
            poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
        )
        state = collect_project_state(client, project_id)
        summary = summarize_state(state)
        if int(summary["open_review_count"]) > 0:
            return "NEEDS_REVIEW", state
        if _needs_prepare(state, summary):
            return "NOT_READY", state

    # FlowState is a read-only projection of current business truth. If its current TargetDialogue
    # count disagrees after TargetDialogue itself is current, stop before expensive H3 generation.
    if not bool(summary.get("flow_target_dialogue_count_current")):
        return "NOT_READY", state

    segment_count = int(summary["generation_segment_count"])
    if int(summary["selected_count"]) < segment_count:
        _run_task(
            client,
            f"/api/projects/{project_id}/tasks/h3-generate-ready",
            label="H3 生成 + QC",
            poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
        )
        state = collect_project_state(client, project_id)
        summary = summarize_state(state)
        if int(summary["open_review_count"]) > 0:
            return "NEEDS_REVIEW", state

    if int(summary["selected_count"]) != segment_count:
        return "NOT_READY", state

    if (
        int(summary["postproduction_succeeded_count"]) < segment_count
        or int(summary["episode_output_succeeded_count"]) < int(summary["episode_count"])
    ):
        _run_task(
            client,
            f"/api/projects/{project_id}/tasks/postproduction",
            label="口型 / 背景音 / EpisodeOutput",
            poll_seconds=poll_seconds,
            timeout_seconds=timeout_seconds,
        )
        state = collect_project_state(client, project_id)
        summary = summarize_state(state)
        if int(summary["open_review_count"]) > 0:
            return "NEEDS_REVIEW", state

    return acceptance_result(summary), state


def _runtime_line(name: str, payload: dict[str, Any]) -> str:
    return f"  {name:<16} {'READY' if payload.get('ready') else 'NOT READY'}"


def print_report(*, runtimes: dict[str, dict[str, Any]], summary: dict[str, Any], result: str) -> None:
    print("\nAI Drama Studio 本地真实项目验收")
    print("\nRuntime")
    labels = (
        ("Backend", "backend"),
        ("H3 FL2VA", "h3_fl2va"),
        ("H3 Ref2VA", "h3_ref2va"),
        ("Qwen3-VL", "qwen3_vl"),
        ("Qwen3-TTS", "qwen3_tts"),
        ("LatentSync", "latentsync"),
        ("AudioSeparator", "audio_separator"),
    )
    for label, key in labels:
        print(_runtime_line(label, runtimes.get(key) or {}))

    print(f"\nProject {summary.get('project_name') or summary.get('project_id') or '-'}")
    print(f"  待确认            {summary.get('open_review_count', 0)}")
    if summary.get("review_types"):
        print(f"  待确认类型        {', '.join(summary['review_types'])}")
    print(
        "  SourceDialogue     "
        f"{summary.get('source_dialogue_count', 0)} utterances / "
        f"{summary.get('source_dialogue_projection_count', 0)} projections"
    )
    print(
        "  TargetDialogue     "
        f"{summary.get('target_dialogue_count', 0)} / "
        f"audio {summary.get('target_dialogue_audio_ready_count', 0)} READY"
    )
    print(f"  Dialogue Contract  {'CURRENT' if summary.get('dialogue_contract_current') else 'NOT CURRENT'}")
    print(
        "  FlowState Dialogue "
        f"{summary.get('flow_target_dialogue_count', 0)} / "
        f"{'CURRENT' if summary.get('flow_target_dialogue_count_current') else 'NOT CURRENT'}"
    )
    print(f"  H3 Selected       {summary.get('selected_count', 0)}/{summary.get('generation_segment_count', 0)}")
    print(f"  PostProduction    {summary.get('postproduction_succeeded_count', 0)}/{summary.get('postproduction_segment_count', 0)}")
    print(f"  EpisodeOutput     {summary.get('episode_output_succeeded_count', 0)}/{summary.get('episode_count', 0)}")
    modes = summary.get("background_audio_modes") or {}
    if modes:
        print("  Background         " + ", ".join(f"{key}={value}" for key, value in sorted(modes.items())))
    print(f"\nResult: {result}")
    if result == "READY_FOR_MANUAL_ACCEPTANCE":
        print("下一步只做人工看听验收：人物一致性、原演员泄漏、场景、动作/运镜、目标对白、口型、源语言残留、背景音、字幕与整集节奏。")
    elif result == "NEEDS_REVIEW":
        print("请先在现有“待确认”页面处理真实业务问题，然后重新运行本脚本；不要直接关闭 ReviewIssue。")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run/check the current real-project localized-remake acceptance chain")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--vlm-base-url", default=os.getenv("AI_DRAMA_VLM_BASE_URL", "http://127.0.0.1:8001/v1"))
    parser.add_argument("--vlm-model", default=os.getenv("AI_DRAMA_VLM_MODEL", "Qwen3-VL-4B-Instruct"))
    parser.add_argument("--run", action="store_true", help="resume missing existing production tasks; default is read-only")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--timeout-seconds", type=float, default=6 * 60 * 60)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    client = HttpClient(args.base_url)
    try:
        runtimes = collect_runtime_status(client, vlm_base_url=args.vlm_base_url, vlm_model=args.vlm_model)
        blockers = runtime_blockers(runtimes)
        initial_state = collect_project_state(client, args.project_id)
        if blockers:
            result = "RUNTIME_BLOCKED"
            state = initial_state
        elif args.run:
            result, state = run_pipeline(
                client,
                args.project_id,
                poll_seconds=args.poll_seconds,
                timeout_seconds=args.timeout_seconds,
            )
        else:
            state = initial_state
            result = acceptance_result(summarize_state(state))
        summary = summarize_state(state)
        if args.json_output:
            print(json.dumps({"result": result, "runtimes": runtimes, "summary": summary}, ensure_ascii=False, indent=2))
        else:
            print_report(runtimes=runtimes, summary=summary, result=result)
        return EXIT_CODES[result]
    except AcceptanceError as exc:
        payload = {"result": "PIPELINE_FAILED", "error": str(exc)}
        if args.json_output:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"\nResult: PIPELINE_FAILED\n{exc}")
        return EXIT_CODES["PIPELINE_FAILED"]


if __name__ == "__main__":
    raise SystemExit(main())