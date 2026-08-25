"""03 资产人物 V4.1 ONNX Runtime 设备策略。

职责：
- 默认优先 CUDAExecutionProvider；
- CUDA 不可用或初始化失败时自动回退 CPUExecutionProvider；
- 不把 GPU 降级静默隐藏，向 UI / Task 暴露实际 provider；
- 允许 AI_DRAMA_CHARACTER_DEVICE=cpu 仅用于诊断或兼容。

为什么单独存在：PyTorch CUDA 可用并不代表 pip 的 OpenCV DNN 就支持 CUDA。
YOLOX / YoutuReID 使用 ONNX Runtime GPU，可以直接复用本机 NVIDIA CUDA 运行环境，
而 YuNet / SFace 继续保持 OpenCV CPU，避免为了两个轻量模型自编译 OpenCV CUDA。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _device_preference() -> str:
    value = os.getenv("AI_DRAMA_CHARACTER_DEVICE", "auto").strip().lower()
    return value if value in {"auto", "cuda", "cpu"} else "auto"


def provider_plan(available_providers: list[str], preference: str | None = None) -> list[Any]:
    """职责：生成 ORT provider 优先顺序；GPU 永远优先于 CPU，除非显式要求 CPU。"""

    requested = (preference or _device_preference()).lower()
    has_cuda = "CUDAExecutionProvider" in available_providers
    if requested != "cpu" and has_cuda:
        return [
            ("CUDAExecutionProvider", {"device_id": 0}),
            "CPUExecutionProvider",
        ]
    return ["CPUExecutionProvider"]


def runtime_status() -> dict[str, object]:
    """只检查运行时能力，不加载业务模型。"""

    preference = _device_preference()
    try:
        # Windows 下先 import torch，让 PyTorch wheel 已携带的 CUDA/cuDNN DLL 进入进程搜索路径。
        # 失败不阻塞 ORT 自己继续探测 provider。
        try:
            import torch  # noqa: F401
        except Exception:
            pass
        import onnxruntime as ort
    except Exception as exc:
        return {
            "installed": False,
            "preference": preference,
            "device": "CPU",
            "provider": None,
            "available_providers": [],
            "gpu_available": False,
            "fallback": True,
            "detail": f"onnxruntime-gpu 未就绪：{exc}",
        }

    available = list(ort.get_available_providers())
    plan = provider_plan(available, preference)
    first = plan[0][0] if isinstance(plan[0], tuple) else plan[0]
    gpu = first == "CUDAExecutionProvider"
    return {
        "installed": True,
        "preference": preference,
        "device": "GPU" if gpu else "CPU",
        "provider": first,
        "available_providers": available,
        "gpu_available": "CUDAExecutionProvider" in available,
        "fallback": preference != "cpu" and not gpu,
        "detail": "CUDA 优先，CPU 自动回退" if gpu else "当前使用 CPU fallback",
    }


def create_session(model_path: Path) -> tuple[Any, dict[str, object]]:
    """创建 ORT Session；CUDA session 创建失败时自动重试 CPU。

    返回：InferenceSession + 实际运行信息。
    """

    try:
        import torch  # noqa: F401
    except Exception:
        pass
    import onnxruntime as ort

    available = list(ort.get_available_providers())
    preference = _device_preference()
    plan = provider_plan(available, preference)
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    try:
        session = ort.InferenceSession(str(model_path), sess_options=options, providers=plan)
        active = session.get_providers()[0] if session.get_providers() else "CPUExecutionProvider"
        return session, {
            "device": "GPU" if active == "CUDAExecutionProvider" else "CPU",
            "provider": active,
            "gpu_available": "CUDAExecutionProvider" in available,
            "fallback": preference != "cpu" and active != "CUDAExecutionProvider",
            "detail": "CUDA" if active == "CUDAExecutionProvider" else "CPU fallback",
        }
    except Exception as cuda_exc:
        # 如果本来就只计划 CPU，则 CPU 失败必须向上抛出真实错误。
        first = plan[0][0] if isinstance(plan[0], tuple) else plan[0]
        if first == "CPUExecutionProvider":
            raise
        session = ort.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        return session, {
            "device": "CPU",
            "provider": "CPUExecutionProvider",
            "gpu_available": True,
            "fallback": True,
            "detail": f"CUDA 初始化失败，已自动回退 CPU：{cuda_exc}",
        }
