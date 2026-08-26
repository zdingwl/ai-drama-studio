from __future__ import annotations

from pathlib import Path

from engine.app import transvlm_runtime_v5 as base
from engine.app import transvlm_runtime_v51 as runtime


def _config(tmp_path: Path) -> base.TransVLMRuntimeConfig:
    inference = tmp_path / "inference"
    inference.mkdir()
    python = inference / "python.exe"
    python.write_bytes(b"")
    ckpt = inference / "pretrained" / "TransVLM-v1"
    ckpt.mkdir(parents=True)
    (ckpt / "config.json").write_text("{}", encoding="utf-8")
    infer_script = inference / "infer_video.py"
    infer_script.write_text("# test", encoding="utf-8")
    return base.TransVLMRuntimeConfig(
        inference_root=inference,
        python_executable=python,
        checkpoint_dir=ckpt,
        infer_script=infer_script,
        device="cuda:0",
        ffmpeg_shared_bin=None,
    )


def _wire_fake_process(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    captured: list[list[str]] = []
    monkeypatch.setattr(base, "runtime_status", lambda: {"ready": True, "missing": []})
    monkeypatch.setattr(base, "runtime_config", lambda: config)
    monkeypatch.setattr(base, "_transvlm_subprocess_env", lambda _config: {})
    monkeypatch.setattr(
        base,
        "_parse_output",
        lambda _path: [base.TransVLMTransition(start_us=100_000, end_us=100_000)],
    )

    def fake_run(command, *, cwd, env, log_path, on_line=None):
        captured.append(command)
        output = Path(command[command.index("--output-jsonl") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text('{"segments": []}\n', encoding="utf-8")
        return 0, "Done in 1.0 s — 1 ok, 0 failed"

    monkeypatch.setattr(base, "_run_streaming_process", fake_run)
    return config, captured


def test_first_run_uses_capture_driver_without_skipping_official_preprocess(monkeypatch, tmp_path: Path) -> None:
    _config_value, captured = _wire_fake_process(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    rgb_cache = tmp_path / "cache" / "rgb.mp4"
    flow_cache = tmp_path / "cache" / "flow.mp4"

    runtime.detect_transition_segments(
        source,
        tmp_path / "work",
        cache_rgb_path=rgb_cache,
        cache_flow_path=flow_cache,
    )

    command = captured[0]
    assert Path(command[1]).name == "run_transvlm_cached.py"
    assert "--ai-cache-rgb" in command
    assert "--ai-cache-flow" in command
    assert "--no-fps-resample" not in command
    assert "--no-pre-resize" not in command
    assert "--flow" not in command
    assert command[command.index("--max-pixels-override") + 1] == "524288"


def test_rgb_only_recompute_skips_resize_but_runs_flow_in_official_process(monkeypatch, tmp_path: Path) -> None:
    _config_value, captured = _wire_fake_process(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    rgb = tmp_path / "rgb.mp4"
    source.write_bytes(b"source")
    rgb.write_bytes(b"rgb")

    runtime.detect_transition_segments(
        source,
        tmp_path / "work",
        model_rgb_path=rgb,
        cache_flow_path=tmp_path / "flow.mp4",
    )

    command = captured[0]
    assert Path(command[1]).name == "run_transvlm_cached.py"
    assert command[command.index("--video") + 1] == str(rgb)
    assert "--no-fps-resample" in command
    assert "--no-pre-resize" in command
    assert "--flow" not in command
    assert "--ai-cache-flow" in command


def test_rgb_and_flow_reuse_runs_official_qwen_without_capture_driver(monkeypatch, tmp_path: Path) -> None:
    config, captured = _wire_fake_process(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    rgb = tmp_path / "rgb.mp4"
    flow = tmp_path / "flow.mp4"
    source.write_bytes(b"source")
    rgb.write_bytes(b"rgb")
    flow.write_bytes(b"flow")

    runtime.detect_transition_segments(
        source,
        tmp_path / "work",
        model_rgb_path=rgb,
        model_flow_path=flow,
    )

    command = captured[0]
    assert Path(command[1]) == config.infer_script
    assert command[command.index("--video") + 1] == str(rgb)
    assert command[command.index("--flow") + 1] == str(flow)
    assert "--no-fps-resample" in command
    assert "--no-pre-resize" in command
    assert "--ai-cache-flow" not in command


def test_successful_raw_output_is_atomically_published_to_episode_cache(monkeypatch, tmp_path: Path) -> None:
    _config_value, _captured = _wire_fake_process(monkeypatch, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    cached_output = tmp_path / "cache" / "transvlm.jsonl"

    runtime.detect_transition_segments(
        source,
        tmp_path / "work",
        output_cache_path=cached_output,
    )

    assert cached_output.read_text(encoding="utf-8") == '{"segments": []}\n'
