from pathlib import Path
from types import SimpleNamespace

from engine.app import media_v2
from engine.app.media_v2 import _normalize_boundaries


def test_normalize_boundaries_filters_noise_and_keeps_full_duration() -> None:
    boundaries = _normalize_boundaries(
        5_000_000,
        [50_000, 1_000_000, 1_050_000, 3_500_000, 4_950_000],
    )
    assert boundaries == [0, 1_000_000, 3_500_000, 5_000_000]


def test_normalize_boundaries_returns_single_shot_when_no_cuts() -> None:
    assert _normalize_boundaries(2_000_000, []) == [0, 2_000_000]


def test_preprocess_proxy_keeps_optional_source_audio(tmp_path, monkeypatch) -> None:
    """新 Proxy 不能再次使用 -an；源片有声音时必须映射音轨并编码为 AAC。"""

    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    episode = SimpleNamespace(id="EP1", project_id="P1", source_path=str(source))
    commands: list[list[str]] = []

    monkeypatch.setattr(media_v2, "get_episode_record", lambda _: episode)
    monkeypatch.setattr(media_v2, "episode_dir", lambda _project_id, _episode_id: tmp_path / "episode")
    monkeypatch.setattr(media_v2, "upsert_preprocess", lambda **_: None)
    monkeypatch.setattr(
        media_v2,
        "probe_media",
        lambda _: {
            "duration_us": 1_000_000,
            "width": 720,
            "height": 1280,
            "fps": 25.0,
            "video_codec": "h264",
            "audio_codec": "aac",
            "has_audio": True,
        },
    )

    def fake_run(command: list[str], **_):
        commands.append(command)
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"media")
        return SimpleNamespace(stdout="", stderr="")

    # This unit test locks FFmpeg command construction. Full decode validation has its own
    # production boundary and must not require a host FFmpeg binary in this lightweight test.
    monkeypatch.setattr(media_v2, "_run", fake_run)
    monkeypatch.setattr(media_v2, "_validate_video_decode", lambda *_args, **_kwargs: None)
    media_v2.preprocess_episode("EP1")

    proxy_command = commands[0]
    assert "-an" not in proxy_command
    assert ["-map", "0:a:0?"] == proxy_command[proxy_command.index("0:a:0?") - 1 : proxy_command.index("0:a:0?") + 1]
    assert "aac" in proxy_command


def test_ensure_playable_proxy_repairs_legacy_silent_proxy(tmp_path, monkeypatch) -> None:
    """历史无声 Proxy 应复用已有 audio.wav 快速封装声音，视频流不得重新编码。"""

    source = tmp_path / "source.mp4"
    proxy = tmp_path / "proxy.mp4"
    audio = tmp_path / "audio.wav"
    source.write_bytes(b"source")
    proxy.write_bytes(b"silent-proxy")
    audio.write_bytes(b"audio")
    preprocess = SimpleNamespace(status="READY", proxy_path=str(proxy), audio_path=str(audio))
    episode = SimpleNamespace(source_path=str(source), preprocess=preprocess)
    commands: list[list[str]] = []

    monkeypatch.setattr(media_v2, "get_episode_record", lambda _: episode)

    def fake_probe(path: Path):
        path = Path(path)
        if path == proxy:
            # 第一次读取旧 Proxy 时无声；修复完成后文件内容会变化。
            has_audio = path.read_bytes() != b"silent-proxy"
        elif path.name.endswith("audio-repair.tmp.mp4"):
            has_audio = True
        else:
            has_audio = True
        return {
            "duration_us": 1_000_000,
            "width": 720,
            "height": 1280,
            "fps": 25.0,
            "video_codec": "h264",
            "audio_codec": "aac" if has_audio else None,
            "has_audio": has_audio,
        }

    def fake_run(command: list[str], **_):
        commands.append(command)
        Path(command[-1]).write_bytes(b"repaired-proxy")
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr(media_v2, "probe_media", fake_probe)
    monkeypatch.setattr(media_v2, "_run", fake_run)

    result = media_v2.ensure_playable_proxy("EP1")

    assert result == proxy
    assert proxy.read_bytes() == b"repaired-proxy"
    assert len(commands) == 1
    assert commands[0][commands[0].index("-c:v") + 1] == "copy"
    assert commands[0][commands[0].index("-c:a") + 1] == "aac"
