from __future__ import annotations

from pathlib import Path

from engine.app import shot_cache_v51 as cache


PROFILE = {
    "model": "TransVLM-Qwen3-VL-4B-Instruct",
    "backend": "hf",
    "fps": 25.0,
    "window_size": 10.0,
    "stride": 9.0,
    "timestamp_format": "1f",
    "flow_codec": "libx264",
    "max_pixels_override": None,
}


def _manifest(source: Path, *, sha: str = "source-a", runtime: str = "runtime-a") -> dict:
    return cache.build_manifest(
        source_path=source,
        source_sha256=sha,
        runtime_signature_value=runtime,
        transvlm_profile=PROFILE,
    )


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

    for directory in (paths.preprocess, paths.flow, paths.transvlm, paths.transitions):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "old.bin").write_bytes(b"old")

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


def test_clear_flow_cascades_to_transvlm_and_transitions_only(tmp_path: Path) -> None:
    paths = cache.cache_paths(tmp_path / "episode")
    for directory in (paths.preprocess, paths.flow, paths.transvlm, paths.transitions):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "artifact.bin").write_bytes(b"x")

    result = cache.clear_cache(paths, "flow")

    assert result["scope"] == "flow"
    assert paths.preprocess.exists()
    assert not paths.flow.exists()
    assert not paths.transvlm.exists()
    assert not paths.transitions.exists()


def test_clear_transitions_never_touches_source_or_shots(tmp_path: Path) -> None:
    episode_root = tmp_path / "episode"
    source = episode_root / "source" / "original.mp4"
    shot = episode_root / "shots" / "runs" / "run1" / "reference" / "shot.mp4"
    source.parent.mkdir(parents=True)
    shot.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    shot.write_bytes(b"shot")

    paths = cache.cache_paths(episode_root)
    paths.transitions.mkdir(parents=True)
    paths.transition_segments.write_text("{}", encoding="utf-8")

    cache.clear_cache(paths, "all")

    assert source.read_bytes() == b"source"
    assert shot.read_bytes() == b"shot"
    assert not paths.transition_segments.exists()


def test_explicit_recompute_scope_deletes_requested_dependency_chain(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    paths = cache.cache_paths(tmp_path / "episode")
    expected = _manifest(source)
    cache.prepare_cache(paths, expected)
    cache.store_transition_segments(paths, expected, [{"start_us": 1, "end_us": 1}])

    cache.prepare_cache(paths, expected, recompute_scope="transitions")

    assert cache.load_transition_segments(paths, expected) is None
    assert paths.manifest.is_file()
