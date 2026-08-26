"""Stage the pip-installed cuDNN into an isolated PyTorch Windows runtime.

PyTorch Windows wheels bundle cuDNN DLLs under ``torch/lib``. Installing a newer
``nvidia-cudnn-cu12/cu13`` wheel does not necessarily change what ``import torch``
loads, because the bundled DLL directory wins DLL resolution. TransVLM requires
cuDNN >= 9.16 for its Conv3d hot path, so the isolated TransVLM runtime copies the
pinned NVIDIA wheel DLLs over the bundled copies and verifies the actual runtime.

This script is intentionally Windows-only and must run in the TransVLM venv before
any process imports torch from that environment.
"""
from __future__ import annotations

import argparse
from importlib import metadata
from pathlib import Path
import shutil
import sys
import sysconfig

MIN_CUDNN = 91600


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, choices=("nvidia-cudnn-cu12", "nvidia-cudnn-cu13"))
    return parser


def _copy_runtime(package_name: str) -> tuple[Path, Path, list[str]]:
    if sys.platform != "win32":
        raise RuntimeError("cuDNN DLL staging is only required on Windows")

    package_version = metadata.version(package_name)
    if package_version != "9.16.0.29":
        raise RuntimeError(f"Expected {package_name}==9.16.0.29, installed {package_version}")

    site_packages = Path(sysconfig.get_paths()["purelib"]).resolve()
    source_dir = site_packages / "nvidia" / "cudnn" / "bin"
    torch_lib = site_packages / "torch" / "lib"
    if not source_dir.is_dir():
        raise RuntimeError(f"NVIDIA cuDNN DLL directory not found: {source_dir}")
    if not torch_lib.is_dir():
        raise RuntimeError(f"PyTorch DLL directory not found: {torch_lib}")

    source_dlls = sorted(source_dir.glob("cudnn*.dll"))
    if not source_dlls:
        raise RuntimeError(f"No cuDNN DLLs found in {source_dir}")

    backup_dir = site_packages / "torch" / "_ai_drama_cudnn_bundled_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(torch_lib.glob("cudnn*.dll"))
    for current in existing:
        backup = backup_dir / current.name
        if not backup.exists():
            shutil.copy2(current, backup)
        current.unlink()

    copied: list[str] = []
    for source in source_dlls:
        destination = torch_lib / source.name
        shutil.copy2(source, destination)
        copied.append(source.name)
    return source_dir, torch_lib, copied


def _verify_runtime() -> None:
    # Import only after the DLL overlay is complete.
    import torch

    cudnn = int(torch.backends.cudnn.version() or 0)
    if cudnn < MIN_CUDNN:
        raise RuntimeError(f"PyTorch still loaded cuDNN {cudnn}; expected >= {MIN_CUDNN}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available in the TransVLM PyTorch runtime")

    # TransVLM widens Qwen3-VL's patch embed to six channels and exercises Conv3d.
    layer = torch.nn.Conv3d(6, 8, kernel_size=(2, 4, 4), stride=(2, 4, 4), bias=False).cuda()
    sample = torch.zeros((1, 6, 2, 16, 16), dtype=torch.float32, device="cuda")
    with torch.no_grad():
        output = layer(sample)
    torch.cuda.synchronize()
    if output.numel() <= 0:
        raise RuntimeError("CUDA Conv3d smoke test returned an empty tensor")

    print(
        "[TransVLM] Windows cuDNN overlay verified: "
        f"cudnn={cudnn}, torch={torch.__version__}, cuda={torch.version.cuda}, "
        f"gpu={torch.cuda.get_device_name(0)}, conv3d=OK"
    )


def main() -> int:
    args = _parser().parse_args()
    source_dir, torch_lib, copied = _copy_runtime(args.package)
    print(f"[TransVLM] cuDNN source: {source_dir}")
    print(f"[TransVLM] cuDNN target: {torch_lib}")
    print(f"[TransVLM] Staged {len(copied)} cuDNN DLL(s) from {args.package}==9.16.0.29")
    _verify_runtime()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
