"""G2.3 local Qwen3-VL text-only Adapter.

This adapter reuses the already accepted isolated Qwen3-VL-4B-Instruct runtime/checkpoint. It is
strictly local and synchronous: one subprocess loads the model once and handles all Scene prompts
sequentially. It never opens source video or modifies the frozen G1/G2.1/G2.2 chain.

Environment overrides are G2-specific first, then fall back to the existing P2 VLM runtime paths:
- AI_DRAMA_G2_LLM_PYTHON / AI_DRAMA_P2_VLM_PYTHON
- AI_DRAMA_G2_LLM_MODEL_PATH / AI_DRAMA_P2_VLM_MODEL_PATH
- AI_DRAMA_G2_LLM_DEVICE / AI_DRAMA_P2_VLM_DEVICE
- AI_DRAMA_G2_LLM_MAX_NEW_TOKENS
- AI_DRAMA_G2_LLM_RUNNER
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from typing import Any


SCENE_NARRATIVE_RUNNER_SCHEMA = "scene-narrative-runner-v1"
SCENE_NARRATIVE_QWEN_PROFILE = "breakdown-g2-scene-narrative-qwen3-local-v1"
SCENE_NARRATIVE_TIMEOUT_SECONDS = 60 * 60
DEFAULT_MAX_NEW_TOKENS = 512


@dataclass(frozen=True)
class Qwen3SceneNarrativeRuntimeConfig:
    """一次本地 Scene Narrative batch 的隔离 runtime 配置。"""

    python_executable: Path
    runner_script: Path
    model_path: Path
    device: str
    max_new_tokens: int


BatchInferenceRunner = Callable[
    [Qwen3SceneNarrativeRuntimeConfig, Sequence[Mapping[str, Any]]],
    Mapping[int, str],
]


class SceneNarrativeQwenRuntimeError(RuntimeError):
    """本地 text-only Qwen runtime 缺失或整个 batch 无法执行。"""


class Qwen3VLSceneTextLLM:
    """供 G2.3 Organizer 注入的本地批量文本模型 Adapter。"""

    def __init__(
        self,
        *,
        python_executable: str | None = None,
        runner_script: str | None = None,
        model_path: str | None = None,
        device: str | None = None,
        max_new_tokens: int | None = None,
        inference_runner: BatchInferenceRunner | None = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        inference_root = repo_root / ".runtime" / "TransVLM" / "inference"
        default_python = (
            inference_root / ".venv" / "Scripts" / "python.exe"
            if os.name == "nt"
            else inference_root / ".venv" / "bin" / "python"
        )
        default_model_path = inference_root / "pretrained" / "Qwen3-VL-4B-Instruct"
        default_runner = repo_root / "scripts" / "run_breakdown_scene_narrative_qwen3.py"

        self.python_executable = Path(
            python_executable
            or os.getenv("AI_DRAMA_G2_LLM_PYTHON")
            or os.getenv("AI_DRAMA_P2_VLM_PYTHON")
            or str(default_python)
        ).expanduser()
        self.runner_script = Path(
            runner_script
            or os.getenv("AI_DRAMA_G2_LLM_RUNNER")
            or str(default_runner)
        ).expanduser()
        self.model_path = Path(
            model_path
            or os.getenv("AI_DRAMA_G2_LLM_MODEL_PATH")
            or os.getenv("AI_DRAMA_P2_VLM_MODEL_PATH")
            or str(default_model_path)
        ).expanduser()
        self.device = (
            device
            or os.getenv("AI_DRAMA_G2_LLM_DEVICE")
            or os.getenv("AI_DRAMA_P2_VLM_DEVICE")
            or "cuda"
        ).strip().lower()
        raw_tokens = max_new_tokens
        if raw_tokens is None:
            raw_tokens = int(os.getenv("AI_DRAMA_G2_LLM_MAX_NEW_TOKENS") or DEFAULT_MAX_NEW_TOKENS)
        self.max_new_tokens = int(raw_tokens)
        self._inference_runner = inference_runner or self._run_subprocess
        self._uses_production_runner = inference_runner is None

        if self.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("G2 LLM device 只允许 auto/cpu/cuda")
        if not math.isfinite(float(self.max_new_tokens)) or not 64 <= self.max_new_tokens <= 2048:
            raise ValueError("G2 LLM max_new_tokens 必须在 64..2048")

    def _config(self) -> Qwen3SceneNarrativeRuntimeConfig:
        return Qwen3SceneNarrativeRuntimeConfig(
            python_executable=self.python_executable,
            runner_script=self.runner_script,
            model_path=self.model_path,
            device=self.device,
            max_new_tokens=self.max_new_tokens,
        )

    def runtime_preflight(self) -> dict[str, Any]:
        """只检查本地路径，不下载模型、不启动推理。"""

        config = self._config()
        missing: list[str] = []
        if self._uses_production_runner:
            if not config.python_executable.is_file():
                missing.append("isolated Qwen3-VL Python runtime")
            if not config.runner_script.is_file():
                missing.append("G2 Scene narrative runner")
            if not config.model_path.is_dir():
                missing.append("Qwen3-VL-4B-Instruct checkpoint")
            elif not (config.model_path / "config.json").is_file():
                missing.append("Qwen3-VL checkpoint config.json")
        return {
            "profile": SCENE_NARRATIVE_QWEN_PROFILE,
            "status": "READY" if not missing else "NOT_CONFIGURED",
            "device": config.device,
            "max_new_tokens": config.max_new_tokens,
            "missing": missing,
        }

    @staticmethod
    def _subprocess_env(config: Qwen3SceneNarrativeRuntimeConfig) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("HF_HUB_OFFLINE", "1")
        env.setdefault("TRANSFORMERS_OFFLINE", "1")
        if os.name == "nt":
            # Use parent/parent instead of indexed ``parents`` so even a custom shallow relative
            # executable path cannot raise IndexError while constructing the environment.
            runtime_root = config.python_executable.parent.parent
            torch_lib = runtime_root / "Lib" / "site-packages" / "torch" / "lib"
            if torch_lib.is_dir():
                existing = env.get("PATH", "")
                env["PATH"] = os.pathsep.join([str(torch_lib)] + ([existing] if existing else []))
        return env

    @staticmethod
    def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def _run_subprocess(
        self,
        config: Qwen3SceneNarrativeRuntimeConfig,
        requests: Sequence[Mapping[str, Any]],
    ) -> Mapping[int, str]:
        preflight = self.runtime_preflight()
        if preflight["status"] != "READY":
            raise SceneNarrativeQwenRuntimeError("G2 本地 Qwen3-VL text runtime 未配置完整")

        with tempfile.TemporaryDirectory(prefix="ai-drama-g2-scene-narrative-") as temp_name:
            root = Path(temp_name)
            manifest_path = root / "manifest.json"
            output_path = root / "output.jsonl"
            self._write_json(
                manifest_path,
                {
                    "schema_version": SCENE_NARRATIVE_RUNNER_SCHEMA,
                    "requests": [dict(item) for item in requests],
                },
            )
            command = [
                str(config.python_executable),
                str(config.runner_script),
                "--model-path",
                str(config.model_path),
                "--manifest",
                str(manifest_path),
                "--output",
                str(output_path),
                "--device",
                config.device,
                "--max-new-tokens",
                str(config.max_new_tokens),
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
                    timeout=SCENE_NARRATIVE_TIMEOUT_SECONDS,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise SceneNarrativeQwenRuntimeError(
                    f"G2 本地 Qwen Scene narrative batch 失败：{type(exc).__name__}"
                ) from exc
            if not output_path.is_file():
                raise SceneNarrativeQwenRuntimeError("G2 本地 Qwen Scene narrative runner 未生成输出")

            result: dict[int, str] = {}
            for line in output_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if not isinstance(row, Mapping) or str(row.get("status") or "") != "READY":
                    continue
                candidate = row.get("candidate")
                if not isinstance(candidate, Mapping):
                    continue
                try:
                    ordinal = int(row.get("scene_ordinal") or 0)
                except (TypeError, ValueError):
                    continue
                if ordinal > 0 and ordinal not in result:
                    result[ordinal] = json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))
            return result

    def generate_many(self, requests: Sequence[Mapping[str, Any]]) -> Mapping[int, str]:
        """一次加载模型，按 Scene 顺序返回 READY candidate；单 Scene 失败时该 ordinal 缺席。"""

        normalized: list[dict[str, Any]] = []
        ordinals: set[int] = set()
        for item in requests:
            try:
                ordinal = int(item.get("scene_ordinal") or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError("G2 LLM request scene_ordinal 非法") from exc
            if ordinal < 1 or ordinal in ordinals:
                raise ValueError("G2 LLM request scene_ordinal 缺失或重复")
            ordinals.add(ordinal)
            system_prompt = str(item.get("system_prompt") or "")
            user_prompt = str(item.get("user_prompt") or "")
            if not system_prompt.strip() or not user_prompt.strip():
                raise ValueError("G2 LLM request prompt 不能为空")
            normalized.append({
                "scene_ordinal": ordinal,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            })
        return self._inference_runner(self._config(), tuple(normalized))

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Mapping[str, Any],
    ) -> str:
        """兼容单请求 Protocol；正式 Episode Organizer 会优先走 generate_many。"""

        del response_schema
        result = self.generate_many(({
            "scene_ordinal": 1,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        },))
        raw = result.get(1)
        if raw is None:
            raise SceneNarrativeQwenRuntimeError("G2 本地 Qwen 单 Scene 未返回可用 candidate")
        return raw


__all__ = [
    "DEFAULT_MAX_NEW_TOKENS",
    "Qwen3SceneNarrativeRuntimeConfig",
    "Qwen3VLSceneTextLLM",
    "SCENE_NARRATIVE_QWEN_PROFILE",
    "SceneNarrativeQwenRuntimeError",
]
