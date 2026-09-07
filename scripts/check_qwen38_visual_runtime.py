#!/usr/bin/env python3
"""Read-only readiness check for the local Qwen3.8 source-video provider.

This checker deliberately does not load the 27B checkpoint and does not run video inference.
It verifies that the isolated runtime, checkpoint files and production runner are coherent enough
for a real-video acceptance run to be attempted. Real Episode acceptance remains a separate gate.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


PROVIDER = "qwen38-video-understanding"
MODEL_PROFILE = "Qwen/Qwen3.8-27B"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_python() -> Path:
    configured = os.getenv("AI_DRAMA_P2_VLM_PYTHON", "").strip()
    if configured:
        return Path(configured).expanduser()
    base = repo_root() / ".runtime" / "TransVLM" / "inference" / ".venv"
    return base / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def default_model_path() -> Path:
    configured = os.getenv("AI_DRAMA_P2_VLM_MODEL_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return repo_root() / ".runtime" / "TransVLM" / "inference" / "pretrained" / "Qwen3.8-27B"


def default_runner() -> Path:
    configured = os.getenv("AI_DRAMA_P2_VLM_RUNNER", "").strip()
    if configured:
        return Path(configured).expanduser()
    return repo_root() / "scripts" / "run_breakdown_vlm_fast_grounded_qwen38.py"


def _check(name: str, ready: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ready": bool(ready), "detail": detail}


def _run_json(command: list[str], *, timeout: float = 30.0) -> tuple[dict[str, Any] | None, str | None]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip()[-1500:]
        return None, tail or f"process exited {completed.returncode}"
    raw = (completed.stdout or "").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, f"invalid JSON from isolated runtime: {raw[-500:]}"
    return payload if isinstance(payload, dict) else None, None


def collect_readiness(
    *,
    python_exe: Path,
    model_path: Path,
    runner: Path,
    require_cuda: bool = True,
) -> dict[str, Any]:
    python_exe = python_exe.resolve() if python_exe.exists() else python_exe
    model_path = model_path.resolve() if model_path.exists() else model_path
    runner = runner.resolve() if runner.exists() else runner
    checks: list[dict[str, Any]] = []

    python_ok = python_exe.is_file()
    checks.append(_check("python", python_ok, str(python_exe)))

    config_path = model_path / "config.json"
    config: dict[str, Any] = {}
    config_ok = False
    config_detail = str(config_path)
    if config_path.is_file():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config = loaded
                model_type = str(config.get("model_type") or "")
                architectures = [str(value) for value in (config.get("architectures") or [])]
                signature = " ".join([model_type, *architectures]).lower().replace("-", "_")
                config_ok = "qwen3" in signature and ("3_8" in signature or "38" in signature)
                config_detail = f"model_type={model_type or '-'}; architectures={architectures or '-'}"
        except (OSError, json.JSONDecodeError) as exc:
            config_detail = str(exc)
    checks.append(_check("checkpoint_config", config_ok, config_detail))

    weight_files = list(model_path.glob("*.safetensors")) if model_path.is_dir() else []
    weight_index = model_path / "model.safetensors.index.json"
    weights_ok = bool(weight_files) or weight_index.is_file()
    checks.append(
        _check(
            "checkpoint_weights",
            weights_ok,
            f"safetensors={len(weight_files)}; index={weight_index.is_file()}",
        )
    )

    runner_ok = runner.is_file()
    checks.append(_check("runner", runner_ok, str(runner)))

    runtime: dict[str, Any] = {
        "cuda_available": False,
        "gpu": None,
        "torch_version": None,
        "transformers_version": None,
        "qwen_vl_utils": None,
    }
    imports_ok = False
    if python_ok:
        probe_code = (
            "import json, torch, transformers, qwen_vl_utils; "
            "from transformers import AutoModelForMultimodalLM, AutoProcessor; "
            "from qwen_vl_utils import process_vision_info; "
            "print(json.dumps({"
            "'cuda_available': bool(torch.cuda.is_available()),"
            "'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,"
            "'torch_version': str(torch.__version__),"
            "'transformers_version': str(transformers.__version__),"
            "'qwen_vl_utils': getattr(qwen_vl_utils, '__version__', None),"
            "'multimodal_loader': AutoModelForMultimodalLM.__name__,"
            "'processor': AutoProcessor.__name__,"
            "'vision_helper': process_vision_info.__name__"
            "}))"
        )
        payload, error = _run_json([str(python_exe), "-c", probe_code])
        if payload is not None:
            runtime.update(payload)
            imports_ok = True
            detail = (
                f"torch={runtime.get('torch_version')}; "
                f"transformers={runtime.get('transformers_version')}; "
                f"cuda={runtime.get('cuda_available')}"
            )
        else:
            detail = error or "isolated import probe failed"
        checks.append(_check("multimodal_runtime", imports_ok, detail))
    else:
        checks.append(_check("multimodal_runtime", False, "isolated Python is missing"))

    cuda_ok = bool(runtime.get("cuda_available")) if require_cuda else True
    checks.append(
        _check(
            "cuda",
            cuda_ok,
            str(runtime.get("gpu") or ("not required" if not require_cuda else "CUDA unavailable")),
        )
    )

    runner_help_ok = False
    runner_help_detail = "runner or isolated Python is missing"
    if python_ok and runner_ok:
        try:
            completed = subprocess.run(
                [str(python_exe), str(runner), "--help"],
                capture_output=True,
                text=True,
                timeout=30.0,
                check=False,
            )
            runner_help_ok = completed.returncode == 0
            runner_help_detail = "production runner CLI import path is ready" if runner_help_ok else (
                (completed.stderr or completed.stdout or "").strip()[-1500:]
                or f"runner --help exited {completed.returncode}"
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            runner_help_detail = str(exc)
    checks.append(_check("runner_cli", runner_help_ok, runner_help_detail))

    ready = all(bool(item["ready"]) for item in checks)
    return {
        "ready": ready,
        "provider": PROVIDER,
        "model_profile": MODEL_PROFILE,
        "python": str(python_exe),
        "model_path": str(model_path),
        "runner": str(runner),
        "runtime": runtime,
        "checks": checks,
        "acceptance_scope": "RUNTIME_READINESS_ONLY",
        "real_video_acceptance": False,
        "message": (
            "Qwen3.8 visual runtime is ready for a real-video acceptance attempt."
            if ready
            else "Qwen3.8 visual runtime is not ready; fix failed checks before real-video acceptance."
        ),
    }


def print_report(result: dict[str, Any]) -> None:
    print("AI Drama Studio · Qwen3.8 Visual Runtime")
    print("")
    for item in result.get("checks") or []:
        state = "READY" if item.get("ready") else "NOT READY"
        print(f"  {item.get('name', '-'):<20} {state}")
        print(f"    {item.get('detail', '')}")
    print("")
    print(f"Provider: {result.get('provider')}")
    print(f"Model:    {result.get('model_profile')}")
    print(f"Result:   {'READY' if result.get('ready') else 'BLOCKED'}")
    print("Scope:    runtime readiness only; no checkpoint load or real video inference was executed.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local Qwen3.8 visual-provider readiness")
    parser.add_argument("--python", default=str(default_python()))
    parser.add_argument("--model-path", default=str(default_model_path()))
    parser.add_argument("--runner", default=str(default_runner()))
    parser.add_argument("--allow-cpu", action="store_true", help="diagnostic only; production Qwen3.8 acceptance should require CUDA")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    result = collect_readiness(
        python_exe=Path(args.python).expanduser(),
        model_path=Path(args.model_path).expanduser(),
        runner=Path(args.runner).expanduser(),
        require_cuda=not args.allow_cpu,
    )
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)
    return 0 if result["ready"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
