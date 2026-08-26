from __future__ import annotations

from pathlib import Path

from engine.app import shot_cache_v51 as cache


PROFILE = {
    "model": "TransVLM-Qwen3-VL-4B-Instruct",
    "backend": "hf",
    "fps": 25.0,
    "window_size": 10.0,
    "stride": 9.0,
    "strict_tail": False,
    "merge_eps": 0.02,
    "timestamp_format": "1f",
    "flow_codec": "libx264",
    "flow_viz_device": "gpu",
    "flow_mini_batch_size": 32,
    "max_pixels_override": 524288,
    "image_patch_size": 16,
    "nframes_for_resize": 250,
    "max_new_tokens": 2048,
    "prefix_caching": True,
}


def _manifest(source: Path, *, sha: str = "source-a", runtime: str = "runtime-a") -> dict:
    return cache.build_manifest(
        source_path=source,
        source_sha256=sha,
        runtime_signature_value=runtime,
        transvlm_profile=PROFILE,
    )


def _write_all_layers(paths: cache.ShotCachePaths) -> None:
    paths.model_rgb.parent.mkdir(parents=True, exist_ok=True)
    paths.model_rgb.write_bytes(b"rgb")
    paths.model_flow.parent.mkdir(parents=True, exist_ok=True)
    paths.model_flow.write_bytes(b"flow")
    paths.transvlm_output.parent.mkdir(parents=True, exist_ok=True)
    paths.transvlm_output.write_text("{}\n", encoding="utf-8")
    paths.transition_segments.parent.mkdir(parents=True, exist_ok=True)
    paths.transition_segments.write_text("{}", encoding="utf-8")


def test_transition_cache_round_trip_requires_exact_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    paths = cache.cache_paths(tmp_path / "episode")
    expected = _manifest(source)

    cache.prepare_cache(paths, expected)
    cache.store_transition_segments(
        paths,
        expected,
        [
            {"start_us": 100_000, "end_us": 100_000},
            {"start_us": 880_000, "end_us": 960_000},
        ],
    )

    assert cache.load_transition_segments(paths, expected) == [
        {"start_us": 100_000, "end_us": 100_000},
        {"start_us": 880_000, "end_us": 960_000},
    ]


def test_source_change_invalidates_all_old_cache_layers(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-v1")
    episode_root = tmp_path / "episode"
    paths = cache.cache_paths(episode_root)
    first = _manifest(source, sha="sha-v1")
    cache.prepare_cache(paths, first)
    _write_all_layers(paths)

    source.write_bytes(b"source-v2-longer")
    second = _manifest(source, sha="sha-v2")
    result = cache.prepare_cache(paths, second)

    assert result["invalidated"] is True
    assert not paths.preprocess.exists()
    assert not paths.flow.exists()
    assert not paths.transvlm.exists()
    assert not paths.transitions.exists()
    assert paths.manifest.is_file()


def test_runtime_change_invalidates_transition_cache(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    paths = cache.cache_paths(tmp_path / "episode")
    first = _manifest(source, runtime="runtime-a")
    cache.prepare_cache(paths, first)
    cache.store_transition_segments(paths, first, [{"start_us": 1, "end_us": 1}])

    second = _manifest(source, runtime="runtime-b")
    result = cache.prepare_cache(paths, second)

    assert result["invalidated"] is True
    assert cache.load_transition_segments(paths, second) is None


def test_clear_transitions_keeps_all_upstream_layers(tmp_path: Path) -> None:
    paths = cache.cache_paths(tmp_path / "episode")
    _write_all_layers(paths)

    cache.clear_cache(paths, "transitions")

    assert paths.model_rgb.is_file()
    assert paths.model_flow.is_file()
    assert paths.transvlm_output.is_file()
    assert not paths.transitions.exists()


def test_clear_transvlm_keeps_rgb_and_flow(tmp_path: Path) -> None:
    paths = cache.cache_paths(tmp_path / "episode")
    _write_all_layers(paths)

    cache.clear_cache(paths, "transvlm")

    assert paths.model_rgb.is_file()
    assert paths.model_flow.is_file()
    assert not paths.transvlm.exists()
    assert not paths.transitions.exists()


def test_clear_flow_cascades_to_transvlm_and_transitions_only(tmp_path: Path) -> None:
    paths = cache.cache_paths(tmp_path / "episode")
    _write_all_layers(paths)

    result = cache.clear_cache(paths, "flow")

    assert result["scope"] == "flow"
    assert paths.model_rgb.is_file()
    assert not paths.flow.exists()
    assert not paths.transvlm.exists()
    assert not paths.transitions.exists()


def test_clear_preprocess_removes_every_model_cache_layer(tmp_path: Path) -> None:
    paths = cache.cache_paths(tmp_path / "episode")
    _write_all_layers(paths)

    cache.clear_cache(paths, "preprocess")

    assert not paths.preprocess.exists()
    assert not paths.flow.exists()
    assert not paths.transvlm.exists()
    assert not paths.transitions.exists()


def test_clear_all_never_touches_source_or_shots(tmp_path: Path) -> None:
    episode_root = tmp_path / "episode"
    source = episode_root / "source" / "original.mp4"
    shot = episode_root / "shots" / "runs" / "run1" / "reference" / "shot.mp4"
    source.parent.mkdir(parents=True)
    shot.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    shot.write_bytes(b"shot")

    paths = cache.cache_paths(episode_root)
    _write_all_layers(paths)
    cache.clear_cache(paths, "all")

    assert source.read_bytes() == b"source"
    assert shot.read_bytes() == b"shot"
    assert not paths.root.exists()


def test_explicit_recompute_transitions_keeps_raw_transvlm_output(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    paths = cache.cache_paths(tmp_path / "episode")
    expected = _manifest(source)
    cache.prepare_cache(paths, expected)
    _write_all_layers(paths)

    cache.prepare_cache(paths, expected, recompute_scope="transitions")

    assert cache.load_transition_segments(paths, expected) is None
    assert cache.cached_transvlm_output(paths, expected) == paths.transvlm_output
    assert paths.model_rgb.is_file()
    assert paths.model_flow.is_file()
    assert paths.manifest.is_file()


def test_cache_status_reports_real_artifacts_not_empty_directories(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    paths = cache.cache_paths(tmp_path / "episode")
    expected = _manifest(source)
    cache.prepare_cache(paths, expected)
    paths.preprocess.mkdir(parents=True, exist_ok=True)
    paths.flow.mkdir(parents=True, exist_ok=True)

    status = cache.cache_status(paths, expected)
    assert status["layers"] == {
        "preprocess": False,
        "flow": False,
        "transvlm": False,
        "transitions": False,
    }
