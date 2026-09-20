"""Real local FFmpeg checks; image model selection uses mock runtimes, not paid calls."""

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.script_to_drama.production_media import runtime_model_name, write_concat_manifest


def test_image_runtime_model_name_for_comfyui_and_seedream() -> None:
    comfy = SimpleNamespace(model_name="z-image-turbo", character_edit_model_name="qwen-image-edit")
    seedream = SimpleNamespace(model_name="seedream-lite", character_pipeline_model_name="seedream-pro")
    assert runtime_model_name(comfy, "CHARACTER") == "z-image-turbo"
    assert runtime_model_name(comfy, "SCENE") == "z-image-turbo"
    assert runtime_model_name(seedream, "CHARACTER") == "seedream-pro"
    assert runtime_model_name(seedream, "PROP") == "seedream-lite"
    with pytest.raises(AppError, match="图片运行时未提供模型名称"):
        runtime_model_name(SimpleNamespace(), "CHARACTER")


def test_ffmpeg_manifest_writes_physical_lines_and_escapes_quotes(tmp_path: Path) -> None:
    video_a = tmp_path / "first.mp4"
    video_b = tmp_path / "john's clip.mp4"
    manifest = tmp_path / "list.txt"
    write_concat_manifest([video_a, video_b], manifest)
    contents = manifest.read_text(encoding="utf-8")
    assert contents.count(chr(10)) == 2
    assert contents.splitlines()[0] == f"file '{video_a.resolve()}'"
    assert "john" in contents.splitlines()[1]
    assert "\\''" in contents.splitlines()[1]
    assert "\\nfile" not in contents
    with pytest.raises(ValueError, match="empty concatenation"):
        write_concat_manifest([], manifest)


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg not installed")
def test_ffmpeg_concat_real_two_video_clips(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg and ffprobe
    paths = []
    for index in range(2):
        path = tmp_path / f"segment-{index}.mp4"
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={'black' if index == 0 else 'white'}:s=160x240:r=24:d=0.5",
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", "0.5", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k", str(path),
        ], check=True, capture_output=True, timeout=20)
        paths.append(path)
    manifest = tmp_path / "clips.txt"
    output = tmp_path / "joined.mp4"
    write_concat_manifest(paths, manifest)
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(manifest),
        "-c:v", "libx264", "-c:a", "aac", str(output),
    ], check=True, capture_output=True, timeout=30)
    assert output.stat().st_size > 0
    duration = subprocess.check_output([
        ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(output),
    ], text=True, timeout=20)
    assert float(duration) > 0.8
