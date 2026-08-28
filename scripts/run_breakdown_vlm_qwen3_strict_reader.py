"""Strict video-reader launcher for the P2 Qwen3-VL diagnostic runner.

qwen-vl-utils 0.0.14 honors FORCE_QWENVL_VIDEO_READER when choosing the first
video backend, but fetch_video() still catches any backend exception and
unconditionally retries VIDEO_READER_BACKENDS["torchvision"]. On Windows this
can mask the real decoder error with torchvision's KeyError('video_fps').

This launcher runs inside the isolated Qwen runtime and, when a non-torchvision
backend is explicitly forced, redirects qwen-vl-utils' torchvision fallback to
the same forced backend. It also installs the production Simplified-Chinese
Draft prompt profile before the diagnostic runner imports the shared base runner.
The provider remains fail-closed; decoder/model errors still escape through the
diagnostic transport instead of being hidden or converted into partial Drafts.
"""
from __future__ import annotations

import os

_ALLOWED_STRICT_READERS = frozenset({"decord", "torchcodec", "torchvision"})


def _install_strict_reader() -> str | None:
    forced = os.getenv("FORCE_QWENVL_VIDEO_READER", "").strip().lower()
    if not forced:
        return None
    if forced not in _ALLOWED_STRICT_READERS:
        raise RuntimeError(
            "FORCE_QWENVL_VIDEO_READER must be decord/torchcodec/torchvision"
        )
    if forced == "torchvision":
        return forced

    import qwen_vl_utils.vision_process as vision_process

    backend = vision_process.VIDEO_READER_BACKENDS.get(forced)
    if backend is None:
        raise RuntimeError(f"qwen-vl-utils does not provide video backend: {forced}")

    # qwen-vl-utils reads FORCE_QWENVL_VIDEO_READER into a module global at
    # import time and caches the selected backend. Keep all three in sync.
    vision_process.FORCE_QWENVL_VIDEO_READER = forced
    cache_clear = getattr(vision_process.get_video_reader_backend, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()

    # fetch_video() hard-codes a torchvision retry after any backend exception.
    # Point that fallback slot at the same explicitly forced backend so the
    # original decoder failure remains visible to our diagnostic runner.
    vision_process.VIDEO_READER_BACKENDS["torchvision"] = backend
    return forced


def _install_draft_prompt() -> str:
    import breakdown_vlm_prompt_zh_v1 as prompt_profile

    prompt_profile.install()
    return prompt_profile.PROMPT_PROFILE


def main() -> int:
    _install_strict_reader()
    _install_draft_prompt()

    # Import after installing both compatibility layers so the diagnostic
    # runner and its base helpers observe the strict reader + Chinese prompt.
    import run_breakdown_vlm_qwen3_diagnostic as diagnostic

    return int(diagnostic.main())


if __name__ == "__main__":
    raise SystemExit(main())
