from __future__ import annotations

from pathlib import Path

from engine.app import transvlm_runtime_v5


def test_windows_shared_ffmpeg_contract_requires_runtime_dlls(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ffmpeg.exe").write_bytes(b"")

    assert transvlm_runtime_v5._is_windows_shared_ffmpeg_bin(bin_dir) is False

    (bin_dir / "avcodec-61.dll").write_bytes(b"")
    (bin_dir / "avformat-61.dll").write_bytes(b"")
    (bin_dir / "avutil-59.dll").write_bytes(b"")

    assert transvlm_runtime_v5._is_windows_shared_ffmpeg_bin(bin_dir) is True


def test_shared_ffmpeg_env_override_wins(tmp_path: Path, monkeypatch) -> None:
    inference_root = tmp_path / "runtime" / "inference"
    inference_root.mkdir(parents=True)
    override = tmp_path / "shared" / "bin"
    override.mkdir(parents=True)
    marker = inference_root.parent / "ffmpeg_shared_bin.txt"
    marker.write_text("C:/stale/ffmpeg/bin", encoding="utf-8")

    monkeypatch.setenv("AI_DRAMA_TRANSVLM_FFMPEG_BIN", str(override))

    assert transvlm_runtime_v5._configured_shared_ffmpeg_bin(inference_root) == override


def test_shared_ffmpeg_marker_is_used_when_no_override(tmp_path: Path, monkeypatch) -> None:
    inference_root = tmp_path / "runtime" / "inference"
    inference_root.mkdir(parents=True)
    shared = tmp_path / "ffmpeg-shared" / "bin"
    shared.mkdir(parents=True)
    marker = inference_root.parent / "ffmpeg_shared_bin.txt"
    marker.write_text(str(shared), encoding="utf-8")
    monkeypatch.delenv("AI_DRAMA_TRANSVLM_FFMPEG_BIN", raising=False)

    assert transvlm_runtime_v5._configured_shared_ffmpeg_bin(inference_root) == shared
