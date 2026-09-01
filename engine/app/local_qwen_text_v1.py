"""Small JSON-only client for the already configured local Qwen OpenAI-compatible service."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from engine.app.asset_semantics_v3 import semantic_model_status


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


def request_local_qwen_json(prompt: str, *, timeout_seconds: float = 240.0, temperature: float = 0.1) -> dict[str, Any]:
    status = semantic_model_status()
    if not status.get("ready"):
        raise LocalQwenTextError("local Qwen service is not configured")
    base_url = str(status["base_url"]).rstrip("/")
    model = str(status["model"])
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
        raise LocalQwenTextError(f"local Qwen request failed: {exc}") from exc
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return extract_json_object(str(content))


__all__ = ["LocalQwenTextError", "extract_json_object", "request_local_qwen_json"]
