"""03 资产人物 ONNX Runtime 设备策略。

职责：
- 默认优先 CUDAExecutionProvider；
- Windows 下优先预加载虚拟环境中的 NVIDIA CUDA/cuDNN DLL；
- CUDA 不可用或初始化失败时自动回退 CPUExecutionProvider；
- 不把 GPU 降级静默隐藏，向 UI / Task 暴露实际 provider；
- 允许 AI_DRAMA_CHARACTER_DEVICE=cpu 仅用于诊断或兼容。

为什么：``ort.get_available_providers()`` 只表示 wheel 编译了 CUDA EP，不代表
``onnxruntime_providers_cuda.dll`` 的 CUDA/cuDNN 依赖真的可加载。Character 人物模型
必须在创建真实 InferenceSession 前准备动态库搜索路径。
"""
from __future__ import annotations

import os
from pathlib import Path
import site
import sys
from typing import Any

# Python 3.8+ Windows 的 os.add_dll_directory 返回的 handle 必须保持存活；如果被
# GC/close，目录会从 DLL 搜索路径移除。
_DLL_DIRECTORY_HANDLES: list[Any] = []
_REGISTERED_DLL_DIRECTORIES: set[str] = set()


def _device_preference() -> str:
    value = os.getenv("AI_DRAMA_CHARACTER_DEVICE", "auto").strip().lower()
    return value if value in {"auto", "cuda", "cpu"} else "auto"


def _site_package_roots() -> list[Path]:
    values: list[str] = []
    try:
        values.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        values.append(site.getusersitepackages())
    except Exception:
        pass
    values.extend(str(item) for item in sys.path if item)

    result: list[Path] = []
    seen: set[str] = set()
    for raw in values:
        try:
            path = Path(raw).resolve()
        except Exception:
            continue
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _register_packaged_nvidia_dlls() -> list[str]:
    """把 pip/uv 安装的 ``site-packages/nvidia/*/bin`` 注册给 Windows loader。

    ONNX Runtime 1.20 没有 ``preload_dlls``；1.21+ 虽然有，但这里仍注册目录，
    让项目在旧虚拟环境尚未升级时也能找到 CUDA/cuDNN wheel 中的 DLL。
    """

    if os.name != "nt":
        return []

    candidates: list[Path] = []
    for root in _site_package_roots():
        nvidia_root = root / "nvidia"
        if nvidia_root.is_dir():
            candidates.extend(path for path in nvidia_root.glob("*/bin") if path.is_dir())
        # PyTorch CUDA wheel 的 DLL 通常位于 torch/lib；有 CUDA Torch 时继续兼容。
        torch_lib = root / "torch" / "lib"
        if torch_lib.is_dir():
            candidates.append(torch_lib)

    registered: list[str] = []
    for path in candidates:
        raw = str(path.resolve())
        key = os.path.normcase(raw)
        if key not in _REGISTERED_DLL_DIRECTORIES:
            # LoadLibrary 仍可能读取 PATH；同时维护 PATH 和 AddDllDirectory 两条路径。
            current_path = os.environ.get("PATH", "")
            path_parts = {os.path.normcase(item) for item in current_path.split(os.pathsep) if item}
            if key not in path_parts:
                os.environ["PATH"] = raw + os.pathsep + current_path
            try:
                handle = os.add_dll_directory(raw)
            except (AttributeError, FileNotFoundError, OSError):
                handle = None
            if handle is not None:
                _DLL_DIRECTORY_HANDLES.append(handle)
            _REGISTERED_DLL_DIRECTORIES.add(key)
        registered.append(raw)
    return registered


def _prepare_onnxruntime() -> tuple[Any, dict[str, object]]:
    """加载 ORT，并尽最大可能预加载当前 venv 中的 CUDA/cuDNN DLL。"""

    torch_loaded = False
    try:
        import torch  # noqa: F401
        torch_loaded = True
    except Exception:
        pass

    registered = _register_packaged_nvidia_dlls()
    import onnxruntime as ort

    preload_supported = callable(getattr(ort, "preload_dlls", None))
    preload_error: str | None = None
    if preload_supported and os.name == "nt":
        try:
            # ORT 1.21+：空字符串明确要求从 NVIDIA site-packages 搜索。
            ort.preload_dlls(directory="")
        except Exception as exc:
            preload_error = str(exc)

    return ort, {
        "ort_version": str(getattr(ort, "__version__", "unknown")),
        "torch_preloaded": torch_loaded,
        "ort_preload_supported": preload_supported,
        "nvidia_dll_directories": registered,
        "preload_error": preload_error,
    }


def provider_plan(available_providers: list[str], preference: str | None = None) -> list[Any]:
    """生成 ORT provider 优先顺序；GPU 永远优先于 CPU，除非显式要求 CPU。"""

    requested = (preference or _device_preference()).lower()
    has_cuda = "CUDAExecutionProvider" in available_providers
    if requested != "cpu" and has_cuda:
        return [
            ("CUDAExecutionProvider", {"device_id": 0}),
            "CPUExecutionProvider",
        ]
    return ["CPUExecutionProvider"]


def runtime_status() -> dict[str, object]:
    """检查 ORT wheel/provider 和 DLL 预加载状态；真实 GPU 以 create_session 为准。"""

    preference = _device_preference()
    try:
        ort, preload = _prepare_onnxruntime()
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
            "dependency_preload": {},
        }

    available = list(ort.get_available_providers())
    plan = provider_plan(available, preference)
    first = plan[0][0] if isinstance(plan[0], tuple) else plan[0]
    gpu = first == "CUDAExecutionProvider"
    preload_error = preload.get("preload_error")
    return {
        "installed": True,
        "preference": preference,
        "device": "GPU" if gpu else "CPU",
        "provider": first,
        "available_providers": available,
        # 这里表示 CUDA EP 被 wheel 暴露；真正能否加载由 create_session 的 active provider 验证。
        "gpu_available": "CUDAExecutionProvider" in available,
        "fallback": preference != "cpu" and not gpu,
        "detail": (
            f"CUDA provider 已发现，依赖预加载失败：{preload_error}"
            if gpu and preload_error
            else "CUDA provider 已发现；真实 Session 创建时验证"
            if gpu
            else "当前使用 CPU fallback"
        ),
        "dependency_preload": preload,
    }


def create_session(model_path: Path) -> tuple[Any, dict[str, object]]:
    """创建真实 ORT Session；先预加载 CUDA/cuDNN，CUDA 失败后才回退 CPU。"""

    ort, preload = _prepare_onnxruntime()
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
            "dependency_preload": preload,
        }
    except Exception as cuda_exc:
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
            "dependency_preload": preload,
        }
