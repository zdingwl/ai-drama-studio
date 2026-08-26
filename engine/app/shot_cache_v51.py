"""Stage 02 Shot V5.1 Episode 级缓存基础设施。

目标：
- 缓存只存在于 Episode ``cache/shot_v51``，与 source / shots / revision 成品严格隔离；
- source、TransVLM Runtime 或关键参数变化时自动整体失效；
- 支持按依赖层级清除：preprocess -> flow -> transvlm -> transitions；
- 当前第一阶段正式复用的是 TransVLM transition segments；后续 RGB / Flow / Window cache
  直接挂到同一依赖图，不再重新发明缓存规则；
- 所有写入使用临时文件 + replace，避免任务中断留下半个 manifest。
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

CACHE_SCHEMA_VERSION = "shot-v5.1-cache-1"
CACHE_DIR_NAME = "shot_v51"
VALID_RECOMPUTE_SCOPES = ("auto", "transitions", "transvlm", "flow", "preprocess", "all")

# 清除某层时必须同时删除所有下游产物。
_SCOPE_DIRS: dict[str, tuple[str, ...]] = {
    "transitions": ("transitions",),
    "transvlm": ("transvlm", "transitions"),
    "flow": ("flow", "transvlm", "transitions"),
    "preprocess": ("preprocess", "flow", "transvlm", "transitions"),
    "all": ("preprocess", "flow", "transvlm", "transitions"),
}


@dataclass(frozen=True)
class ShotCachePaths:
    root: Path
    manifest: Path
    preprocess: Path
    flow: Path
    transvlm: Path
    transitions: Path
    transition_segments: Path


def cache_paths(episode_root: Path) -> ShotCachePaths:
    root = Path(episode_root) / "cache" / CACHE_DIR_NAME
    transitions = root / "transitions"
    return ShotCachePaths(
        root=root,
        manifest=root / "manifest.json",
        preprocess=root / "preprocess",
        flow=root / "flow",
        transvlm=root / "transvlm",
        transitions=transitions,
        transition_segments=transitions / "segments.json",
    )


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def runtime_signature(inference_root: Path, checkpoint_dir: Path) -> str:
    """对会改变 TransVLM/NeuFlow 信号的关键 Runtime 文件做轻量签名。

    不哈希多 GB safetensors；checkpoint 由 config.json + 固定模型 profile 标识，Runtime 代码、
    prompt、flow pipeline 直接哈希。setup 更新官方仓库或 prompt 后会自动得到新签名。
    """

    inference_root = Path(inference_root)
    candidates = (
        inference_root / "infer_video.py",
        inference_root / "transvlm" / "data" / "flow_computer.py",
        inference_root / "transvlm" / "assets" / "prompts" / "prompt_only_timestamps.txt",
        Path(checkpoint_dir) / "config.json",
    )
    digest = hashlib.sha256()
    for path in candidates:
        digest.update(str(path.name).encode("utf-8"))
        value = _sha256_file(path)
        digest.update((value or "MISSING").encode("ascii"))
    return digest.hexdigest()


def build_manifest(
    *,
    source_path: Path,
    source_sha256: str,
    runtime_signature_value: str,
    transvlm_profile: dict[str, Any],
) -> dict[str, Any]:
    source = Path(source_path)
    stat = source.stat()
    return {
        "schema": CACHE_SCHEMA_VERSION,
        "source": {
            "sha256": str(source_sha256),
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        },
        "preprocess": {
            "fps": float(transvlm_profile["fps"]),
            "resize": "official-smart-resize",
            "max_pixels_override": transvlm_profile.get("max_pixels_override"),
        },
        "flow": {
            "engine": "NeuFlow-v2",
            "normalization": "whole-video-global",
            "codec": transvlm_profile["flow_codec"],
            "runtime_signature": runtime_signature_value,
        },
        "transvlm": {
            "model": transvlm_profile["model"],
            "backend": transvlm_profile["backend"],
            "window_size": float(transvlm_profile["window_size"]),
            "stride": float(transvlm_profile["stride"]),
            "timestamp_format": transvlm_profile["timestamp_format"],
            "runtime_signature": runtime_signature_value,
        },
    }


def _read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def manifests_match(stored: dict[str, Any] | None, expected: dict[str, Any]) -> bool:
    if stored is None:
        return False
    # 当前 schema 下 manifest 是严格合同。任何上游版本/参数变化都让下游缓存失效。
    return stored == expected


def clear_cache(paths: ShotCachePaths, scope: str = "all") -> dict[str, Any]:
    if scope not in _SCOPE_DIRS:
        raise ValueError(f"不支持的缓存清除范围：{scope}")

    deleted: list[str] = []
    bytes_removed = 0
    for name in _SCOPE_DIRS[scope]:
        target = getattr(paths, name)
        if not target.exists():
            continue
        if target.is_dir():
            for item in target.rglob("*"):
                try:
                    if item.is_file():
                        bytes_removed += int(item.stat().st_size)
                except OSError:
                    pass
            shutil.rmtree(target, ignore_errors=True)
        else:
            try:
                bytes_removed += int(target.stat().st_size)
            except OSError:
                pass
            target.unlink(missing_ok=True)
        deleted.append(name)

    if scope == "all":
        paths.manifest.unlink(missing_ok=True)
        # 只删除 cache/shot_v51；绝不向上删除 source / shots。
        if paths.root.exists():
            try:
                paths.root.rmdir()
            except OSError:
                pass

    return {"scope": scope, "deleted": deleted, "bytes_removed": bytes_removed}


def prepare_cache(
    paths: ShotCachePaths,
    expected_manifest: dict[str, Any],
    *,
    recompute_scope: str = "auto",
) -> dict[str, Any]:
    if recompute_scope not in VALID_RECOMPUTE_SCOPES:
        raise ValueError(f"不支持的重新计算范围：{recompute_scope}")

    stored = _read_manifest(paths.manifest)
    invalidated = not manifests_match(stored, expected_manifest)
    if invalidated and paths.root.exists():
        clear_cache(paths, "all")

    if recompute_scope != "auto":
        clear_cache(paths, recompute_scope)

    paths.root.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(paths.manifest, expected_manifest)
    return {
        "invalidated": invalidated,
        "recompute_scope": recompute_scope,
        "root": str(paths.root),
    }


def load_transition_segments(paths: ShotCachePaths, expected_manifest: dict[str, Any]) -> list[dict[str, int]] | None:
    if not manifests_match(_read_manifest(paths.manifest), expected_manifest):
        return None
    if not paths.transition_segments.is_file():
        return None
    try:
        payload = json.loads(paths.transition_segments.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != CACHE_SCHEMA_VERSION:
        return None
    raw = payload.get("segments")
    if not isinstance(raw, list):
        return None

    result: list[dict[str, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        try:
            start_us = int(item["start_us"])
            end_us = int(item["end_us"])
        except (KeyError, TypeError, ValueError):
            return None
        if start_us < 0 or end_us < 0:
            return None
        result.append({"start_us": start_us, "end_us": end_us})
    return result


def store_transition_segments(
    paths: ShotCachePaths,
    expected_manifest: dict[str, Any],
    segments: list[dict[str, int]],
) -> None:
    # 写 artifact 前再次写 manifest，确保一个成功 Run 的 cache 总是自描述。
    paths.root.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(paths.manifest, expected_manifest)
    _atomic_write_json(
        paths.transition_segments,
        {
            "schema": CACHE_SCHEMA_VERSION,
            "segments": [
                {"start_us": int(item["start_us"]), "end_us": int(item["end_us"])}
                for item in segments
            ],
        },
    )


def cache_status(paths: ShotCachePaths, expected_manifest: dict[str, Any]) -> dict[str, Any]:
    stored = _read_manifest(paths.manifest)
    valid_manifest = manifests_match(stored, expected_manifest)

    def dir_bytes(path: Path) -> int:
        if not path.exists():
            return 0
        total = 0
        for item in path.rglob("*") if path.is_dir() else (path,):
            try:
                if item.is_file():
                    total += int(item.stat().st_size)
            except OSError:
                pass
        return total

    layers = {
        "preprocess": paths.preprocess.exists(),
        "flow": paths.flow.exists(),
        "transvlm": paths.transvlm.exists(),
        "transitions": paths.transition_segments.is_file(),
    }
    return {
        "schema": CACHE_SCHEMA_VERSION,
        "root": str(paths.root),
        "manifest_valid": valid_manifest,
        "layers": layers,
        "transition_cache_usable": bool(valid_manifest and layers["transitions"]),
        "bytes": dir_bytes(paths.root),
    }
