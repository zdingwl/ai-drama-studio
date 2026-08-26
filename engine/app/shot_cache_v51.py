"""Stage 02 Shot V5.1 Episode-level cache infrastructure.

The cache is deliberately outside ``source/`` and ``shots/``.  A cache purge can never delete the
original video, Current Shot Revision, or Reference Clips.

Dependency order is strict::

    preprocess RGB -> optical flow -> raw TransVLM window output -> merged transitions

Clearing one layer clears every downstream layer.  The manifest is a strict contract over source
identity, the official TransVLM runtime, and every signal-affecting production parameter.  Any
contract change invalidates the whole cache before reuse.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable

CACHE_SCHEMA_VERSION = "shot-v5.1-cache-2"
CACHE_DIR_NAME = "shot_v51"
VALID_RECOMPUTE_SCOPES = ("auto", "transitions", "transvlm", "flow", "preprocess", "all")

# Clearing an upstream layer MUST remove all descendants.
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
    model_rgb: Path
    flow: Path
    model_flow: Path
    transvlm: Path
    transvlm_output: Path
    transitions: Path
    transition_segments: Path


def cache_paths(episode_root: Path) -> ShotCachePaths:
    root = Path(episode_root) / "cache" / CACHE_DIR_NAME
    preprocess = root / "preprocess"
    flow = root / "flow"
    transvlm = root / "transvlm"
    transitions = root / "transitions"
    return ShotCachePaths(
        root=root,
        manifest=root / "manifest.json",
        preprocess=preprocess,
        model_rgb=preprocess / "model_rgb.mp4",
        flow=flow,
        model_flow=flow / "model_flow.mp4",
        transvlm=transvlm,
        transvlm_output=transvlm / "transvlm.jsonl",
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


def runtime_signature(
    inference_root: Path,
    checkpoint_dir: Path,
    *,
    extra_files: Iterable[Path] = (),
) -> str:
    """Hash code/config that can alter the cached model signal.

    Multi-GB safetensors are intentionally not hashed on every run.  The checkpoint config plus the
    fixed model profile identifies the weights, while the executable inference/resize/flow/prompt
    code is hashed directly.  App-side cache capture code may be supplied through ``extra_files``.
    """

    inference_root = Path(inference_root)
    candidates = [
        inference_root / "infer_video.py",
        inference_root / "transvlm" / "data" / "flow_computer.py",
        inference_root / "transvlm" / "data" / "flow_config.py",
        inference_root / "transvlm" / "data" / "flow_writer.py",
        inference_root / "transvlm" / "data" / "resize_video_helper.py",
        inference_root / "transvlm" / "inference" / "clip_engine.py",
        inference_root / "transvlm" / "assets" / "prompts" / "prompt_only_timestamps.txt",
        Path(checkpoint_dir) / "config.json",
        *[Path(item) for item in extra_files],
    ]
    digest = hashlib.sha256()
    for path in candidates:
        digest.update(str(path).encode("utf-8"))
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
            "max_pixels_override": int(transvlm_profile["max_pixels_override"]),
            "image_patch_size": int(transvlm_profile["image_patch_size"]),
            "nframes_for_resize": int(transvlm_profile["nframes_for_resize"]),
        },
        "flow": {
            "engine": "NeuFlow-v2",
            "normalization": "whole-video-global",
            "codec": transvlm_profile["flow_codec"],
            "viz_device": transvlm_profile["flow_viz_device"],
            "mini_batch_size": int(transvlm_profile["flow_mini_batch_size"]),
            "runtime_signature": runtime_signature_value,
        },
        "transvlm": {
            "model": transvlm_profile["model"],
            "backend": transvlm_profile["backend"],
            "window_size": float(transvlm_profile["window_size"]),
            "stride": float(transvlm_profile["stride"]),
            "strict_tail": bool(transvlm_profile["strict_tail"]),
            "merge_eps": float(transvlm_profile["merge_eps"]),
            "timestamp_format": transvlm_profile["timestamp_format"],
            "max_new_tokens": int(transvlm_profile["max_new_tokens"]),
            "prefix_caching": bool(transvlm_profile["prefix_caching"]),
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
    # The current schema uses an exact manifest contract.  No stale/partial compatibility layer.
    return stored is not None and stored == expected


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
        # Only remove cache/shot_v51.  Never walk upward into source/ or shots/.
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


def cached_transvlm_output(paths: ShotCachePaths, expected_manifest: dict[str, Any]) -> Path | None:
    if not manifests_match(_read_manifest(paths.manifest), expected_manifest):
        return None
    return paths.transvlm_output if paths.transvlm_output.is_file() else None


def store_transition_segments(
    paths: ShotCachePaths,
    expected_manifest: dict[str, Any],
    segments: list[dict[str, int]],
) -> None:
    # Re-write the manifest before the artifact so every successful cache is self-describing.
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
        "preprocess": paths.model_rgb.is_file(),
        "flow": paths.model_flow.is_file(),
        "transvlm": paths.transvlm_output.is_file(),
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
