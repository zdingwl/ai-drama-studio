#!/usr/bin/env python3
"""Check the current Localized Remake V1 localhost runtime stack.

This script is intentionally read-only. It never installs models, starts workers, edits project
truth, or upgrades real-project acceptance. It only verifies that the services required by the
current end-to-end acceptance chain report READY.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from typing import Any


RUNTIME_ORDER = (
    "backend",
    "h3_fl2va",
    "h3_ref2va",
    "qwen3_vl",
    "qwen3_tts",
    "latentsync",
    "audio_separator",
)

DISPLAY_NAMES = {
    "backend": "Backend",
    "h3_fl2va": "H3 FL2VA",
    "h3_ref2va": "H3 Ref2VA",
    "qwen3_vl": "Qwen3-VL",
    "qwen3_tts": "Qwen3-TTS",
    "latentsync": "LatentSync",
    "audio_separator": "Audio Separator",
}

HINTS = {
    "backend": "Start FastAPI: python -m uvicorn engine.app.main:app --host 127.0.0.1 --port 8000",
    "h3_fl2va": "Start the configured MiniMax H3 FL2VA SGLang service (default http://127.0.0.1:30010).",
    "h3_ref2va": "Start the configured MiniMax H3 Ref2VA SGLang service (default http://127.0.0.1:30011).",
    "qwen3_vl": "Configure AI_DRAMA_VLM_BASE_URL / AI_DRAMA_VLM_MODEL and start the OpenAI-compatible Qwen3-VL service.",
    "qwen3_tts": "Activate the dedicated Qwen3-TTS environment, configure model paths, then run scripts/qwen3_tts_worker_v1.py.",
    "latentsync": "Activate the official LatentSync environment, configure AI_DRAMA_LATENTSYNC_ROOT, then run scripts/latentsync_worker_v1.py.",
    "audio_separator": "Run scripts/setup_audio_separator_runtime.ps1 once, then scripts/start_audio_separator_runtime.ps1.",
}


def _request_json(url: str, *, timeout: float = 5.0, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[-500:]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason or exc)) from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid JSON response") from exc
    if not isinstance(value, dict):
        raise RuntimeError("response is not a JSON object")
    return value


def normalize_backend(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ready": payload.get("status") == "ok",
        "architecture": payload.get("architecture"),
        "app_version": payload.get("app_version"),
        "error": None if payload.get("status") == "ok" else "backend health is not ok",
    }


def normalize_h3(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    def one(key: str) -> dict[str, Any]:
        raw = payload.get(key) or {}
        return {
            "ready": bool(raw.get("ready")),
            "base_url": raw.get("base_url"),
            "probe": raw.get("probe"),
            "error": raw.get("error"),
        }

    return {"h3_fl2va": one("fl2va"), "h3_ref2va": one("ref2va")}


def normalize_worker(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ready": bool(payload.get("ready")),
        "reachable": bool(payload.get("reachable", True)),
        "base_url": payload.get("base_url"),
        "runtime_profile": payload.get("runtime_profile"),
        "error": payload.get("error") or (payload.get("worker") or {}).get("error"),
    }


def normalize_vlm_models(payload: dict[str, Any], *, base_url: str, model: str) -> dict[str, Any]:
    ids = sorted(
        str(item.get("id") or "")
        for item in (payload.get("data") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    )
    configured = bool(base_url.strip() and model.strip())
    # Some OpenAI-compatible local servers expose a canonical model path while accepting a
    # configured alias. Reachability + explicit model configuration is therefore the runtime
    # gate; exact ID matching is diagnostic only.
    return {
        "ready": configured,
        "reachable": True,
        "base_url": base_url.rstrip("/") or None,
        "model": model.strip() or None,
        "available_models": ids,
        "model_list_match": not ids or model.strip() in ids,
        "error": None if configured else "AI_DRAMA_VLM_BASE_URL / AI_DRAMA_VLM_MODEL 未完整配置",
    }


def blockers(results: dict[str, dict[str, Any]]) -> list[str]:
    return [key for key in RUNTIME_ORDER if not bool((results.get(key) or {}).get("ready"))]


def stack_result(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    missing = blockers(results)
    return {
        "status": "READY" if not missing else "BLOCKED",
        "ready": not missing,
        "blockers": missing,
        "runtimes": results,
    }


def _safe_probe(label: str, fn) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:
        return {"ready": False, "reachable": False, "error": str(exc), "probe": label}


def collect_stack(*, backend_base_url: str, vlm_base_url: str, vlm_model: str, timeout: float) -> dict[str, dict[str, Any]]:
    backend = backend_base_url.rstrip("/")
    health = _safe_probe("backend", lambda: normalize_backend(_request_json(f"{backend}/api/health", timeout=timeout)))

    h3_payload = _safe_probe("h3", lambda: _request_json(f"{backend}/api/h3/runtime", timeout=timeout))
    if h3_payload.get("ready") is False and "fl2va" not in h3_payload:
        h3 = {
            "h3_fl2va": {"ready": False, "error": h3_payload.get("error")},
            "h3_ref2va": {"ready": False, "error": h3_payload.get("error")},
        }
    else:
        h3 = normalize_h3(h3_payload)

    tts = _safe_probe(
        "qwen3_tts",
        lambda: normalize_worker(_request_json(f"{backend}/api/tts/runtime-status", timeout=timeout)),
    )
    lip = _safe_probe(
        "latentsync",
        lambda: normalize_worker(_request_json(f"{backend}/api/lip-sync/runtime", timeout=timeout)),
    )
    background = _safe_probe(
        "audio_separator",
        lambda: normalize_worker(_request_json(f"{backend}/api/background-audio/runtime", timeout=timeout)),
    )

    clean_vlm = vlm_base_url.strip().rstrip("/")
    clean_model = vlm_model.strip()
    if not clean_vlm or not clean_model:
        vlm = {
            "ready": False,
            "reachable": False,
            "base_url": clean_vlm or None,
            "model": clean_model or None,
            "error": "AI_DRAMA_VLM_BASE_URL / AI_DRAMA_VLM_MODEL 未完整配置",
        }
    else:
        headers = {"Authorization": f"Bearer {os.getenv('AI_DRAMA_VLM_API_KEY', 'EMPTY').strip() or 'EMPTY'}"}
        vlm = _safe_probe(
            "qwen3_vl",
            lambda: normalize_vlm_models(
                _request_json(f"{clean_vlm}/models", timeout=timeout, headers=headers),
                base_url=clean_vlm,
                model=clean_model,
            ),
        )

    return {
        "backend": health,
        **h3,
        "qwen3_vl": vlm,
        "qwen3_tts": tts,
        "latentsync": lip,
        "audio_separator": background,
    }


def print_report(result: dict[str, Any]) -> None:
    print("AI Drama Studio · Localized Remake Runtime Stack")
    print("")
    for key in RUNTIME_ORDER:
        item = (result.get("runtimes") or {}).get(key) or {}
        state = "READY" if item.get("ready") else "NOT READY"
        print(f"  {DISPLAY_NAMES[key]:<18} {state}")
        if not item.get("ready"):
            if item.get("error"):
                print(f"    error: {item['error']}")
            print(f"    hint:  {HINTS[key]}")
    print("")
    print(f"Result: {result.get('status')}")
    if result.get("ready"):
        print("Runtime stack is ready. Next run the real-project acceptance runner.")
    else:
        print("Fix the NOT READY services above before full local real-project acceptance.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the current Localized Remake V1 runtime stack")
    parser.add_argument("--base-url", default=os.getenv("AI_DRAMA_STUDIO_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--vlm-base-url", default=os.getenv("AI_DRAMA_VLM_BASE_URL", "http://127.0.0.1:8001/v1"))
    parser.add_argument("--vlm-model", default=os.getenv("AI_DRAMA_VLM_MODEL", "Qwen3-VL-4B-Instruct"))
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    results = collect_stack(
        backend_base_url=args.base_url,
        vlm_base_url=args.vlm_base_url,
        vlm_model=args.vlm_model,
        timeout=max(0.5, args.timeout),
    )
    result = stack_result(results)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)
    return 0 if result["ready"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
