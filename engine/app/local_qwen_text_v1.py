"""Unified JSON-only text adapter for the project's local Qwen3-VL runtime.

Target-side planning used to require a second OpenAI-compatible HTTP service even though the
project already provisions Qwen3-VL-4B-Instruct for Breakdown.  This adapter keeps the HTTP
endpoint as an optional compatibility path, but falls back to the accepted isolated local
Qwen3-VL subprocess/checkpoint.  Callers therefore depend on one provider contract instead of a
particular serving topology.
"""
from __future__ import annotations

import json
import os
from collections.abc import Sequence
from typing import Any

import httpx

from engine.app.asset_semantics_v3 import semantic_model_status
from engine.app.breakdown_scene_narrative_qwen3_v1 import (
    Qwen3VLSceneTextLLM,
    SceneNarrativeQwenRuntimeError,
)


DEFAULT_TARGET_TEXT_MAX_NEW_TOKENS = 1536
LOCAL_TEXT_SYSTEM_PROMPT = (
    "You are a structured planning model for a drama-remake pipeline. "
    "Follow the user's requirements exactly and return one valid JSON object only."
)


class LocalQwenTextError(RuntimeError):
    pass


def extract_json_object(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise LocalQwenTextError("local Qwen did not return a JSON object")
    try:
        payload = json.loads(value[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LocalQwenTextError("local Qwen returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise LocalQwenTextError("local Qwen returned a non-object JSON value")
    return payload


def _target_max_new_tokens() -> int:
    raw = (os.getenv("AI_DRAMA_TARGET_QWEN_MAX_NEW_TOKENS") or "").strip()
    if not raw:
        return DEFAULT_TARGET_TEXT_MAX_NEW_TOKENS
    try:
        value = int(raw)
    except ValueError as exc:
        raise LocalQwenTextError("AI_DRAMA_TARGET_QWEN_MAX_NEW_TOKENS must be an integer") from exc
    if not 64 <= value <= 2048:
        raise LocalQwenTextError("AI_DRAMA_TARGET_QWEN_MAX_NEW_TOKENS must be between 64 and 2048")
    return value


def _local_adapter() -> Qwen3VLSceneTextLLM:
    try:
        return Qwen3VLSceneTextLLM(max_new_tokens=_target_max_new_tokens())
    except (TypeError, ValueError) as exc:
        raise LocalQwenTextError(f"local Qwen runtime configuration is invalid: {exc}") from exc


def local_qwen_text_runtime_status() -> dict[str, Any]:
    """Report one text-planning runtime across HTTP compatibility and local subprocess modes.

    This is intentionally a cheap preflight: it does not load the model.  The local mode checks
    the same isolated Python/checkpoint/runner already used by Breakdown.
    """

    http_status = dict(semantic_model_status() or {})
    http_ready = bool(http_status.get("ready"))
    try:
        local_status = dict(_local_adapter().runtime_preflight() or {})
    except LocalQwenTextError as exc:
        local_status = {
            "status": "NOT_CONFIGURED",
            "missing": [str(exc)],
        }
    local_ready = str(local_status.get("status") or "").upper() == "READY"
    if http_ready:
        provider = "openai-compatible"
    elif local_ready:
        provider = "qwen3-vl-local-subprocess"
    else:
        provider = None
    return {
        "ready": bool(http_ready or local_ready),
        "provider": provider,
        "http_configured": http_ready,
        "http": http_status,
        "local_ready": local_ready,
        "local": local_status,
        "missing": list(local_status.get("missing") or []) if not local_ready else [],
        "purpose": "Qwen3-VL target character / scene / dialogue text planning",
    }


def _request_http_json(
    prompt: str,
    *,
    status: dict[str, Any],
    timeout_seconds: float,
    temperature: float,
) -> dict[str, Any]:
    base_url = str(status.get("base_url") or "").strip().rstrip("/")
    model = str(status.get("model") or "").strip()
    if not base_url or not model:
        raise LocalQwenTextError("local Qwen HTTP service is not configured")
    api_key = os.getenv("AI_DRAMA_VLM_API_KEY", "EMPTY").strip() or "EMPTY"
    body = {
        "model": model,
        "temperature": temperature,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
        content = payload["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise LocalQwenTextError(f"local Qwen HTTP request failed: {exc}") from exc
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return extract_json_object(str(content))


def _request_subprocess_many(prompts: Sequence[str]) -> list[dict[str, Any]]:
    adapter = _local_adapter()
    preflight = adapter.runtime_preflight()
    if str(preflight.get("status") or "").upper() != "READY":
        missing = ", ".join(str(item) for item in preflight.get("missing") or [])
        suffix = f": {missing}" if missing else ""
        raise LocalQwenTextError(f"local Qwen3-VL subprocess runtime is not ready{suffix}")
    requests = tuple(
        {
            "scene_ordinal": index,
            "system_prompt": LOCAL_TEXT_SYSTEM_PROMPT,
            "user_prompt": prompt,
        }
        for index, prompt in enumerate(prompts, start=1)
    )
    try:
        raw_by_ordinal = adapter.generate_many(requests)
    except (SceneNarrativeQwenRuntimeError, OSError, ValueError) as exc:
        raise LocalQwenTextError(f"local Qwen3-VL subprocess request failed: {exc}") from exc

    diagnostics = adapter.last_batch_diagnostics()
    output: list[dict[str, Any]] = []
    for ordinal in range(1, len(prompts) + 1):
        raw = raw_by_ordinal.get(ordinal)
        if raw is None:
            diagnostic = diagnostics.get(ordinal) or {}
            error_type = str(diagnostic.get("error_type") or diagnostic.get("status") or "no candidate")
            raise LocalQwenTextError(
                f"local Qwen3-VL subprocess did not return request {ordinal}: {error_type}"
            )
        output.append(extract_json_object(str(raw)))
    return output


def request_local_qwen_json_many(
    prompts: Sequence[str],
    *,
    timeout_seconds: float = 240.0,
    temperature: float = 0.1,
) -> list[dict[str, Any]]:
    """Generate multiple JSON objects while loading the local checkpoint only once when possible."""

    normalized = [str(prompt or "").strip() for prompt in prompts]
    if any(not prompt for prompt in normalized):
        raise LocalQwenTextError("local Qwen prompt cannot be empty")
    if not normalized:
        return []

    http_status = dict(semantic_model_status() or {})
    http_error: LocalQwenTextError | None = None
    if http_status.get("ready"):
        try:
            return [
                _request_http_json(
                    prompt,
                    status=http_status,
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                )
                for prompt in normalized
            ]
        except LocalQwenTextError as exc:
            # An explicitly configured server may be temporarily down.  Reuse the local accepted
            # checkpoint instead of turning that infrastructure problem into human review work.
            http_error = exc

    try:
        return _request_subprocess_many(normalized)
    except LocalQwenTextError as local_error:
        if http_error is not None:
            raise LocalQwenTextError(
                f"Qwen text runtime unavailable: HTTP failed ({http_error}); local fallback failed ({local_error})"
            ) from local_error
        raise


def request_local_qwen_json(
    prompt: str,
    *,
    timeout_seconds: float = 240.0,
    temperature: float = 0.1,
) -> dict[str, Any]:
    return request_local_qwen_json_many(
        [prompt],
        timeout_seconds=timeout_seconds,
        temperature=temperature,
    )[0]


__all__ = [
    "DEFAULT_TARGET_TEXT_MAX_NEW_TOKENS",
    "LocalQwenTextError",
    "extract_json_object",
    "local_qwen_text_runtime_status",
    "request_local_qwen_json",
    "request_local_qwen_json_many",
]
