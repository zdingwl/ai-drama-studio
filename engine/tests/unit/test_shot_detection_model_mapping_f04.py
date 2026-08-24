from __future__ import annotations

import sys
import types
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import pytest

import engine.app.shot_detection as shot_detection
from engine.app.shot_detection import ShotDetectionError, detect_proxy_cut_events


class _FakeTransNetV2:
    """测试替身：只提供 F04 真正依赖的最小 TransNetV2 接口，不执行神经网络。"""

    predictions: np.ndarray = np.array([], dtype=np.float64)

    def __init__(self, device: str = "auto") -> None:
        assert device == "auto"
        self.device = "cpu"

    def load_state_dict(self, _: object) -> None:
        pass

    def eval(self) -> "_FakeTransNetV2":
        return self

    def predict_video(self, _: str) -> tuple[None, np.ndarray, None]:
        return None, self.predictions, None


@pytest.fixture
def fake_transnet_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """伪造固定版本模型包与权重，让测试只验证 F04 的时间映射逻辑。"""

    package_dir = tmp_path / "transnetv2_pytorch"
    package_dir.mkdir()
    package_init = package_dir / "__init__.py"
    package_init.write_text("", encoding="utf-8")
    (package_dir / shot_detection.TRANSNET_WEIGHT_FILENAME).write_bytes(b"fake-weight")

    fake_package = types.ModuleType("transnetv2_pytorch")
    fake_package.__file__ = str(package_init)
    fake_package.TransNetV2 = _FakeTransNetV2

    fake_torch = types.ModuleType("torch")
    fake_torch.__version__ = "2.5.1"
    fake_torch.load = lambda *args, **kwargs: {}
    fake_torch.no_grad = nullcontext

    monkeypatch.setitem(sys.modules, "transnetv2_pytorch", fake_package)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(
        shot_detection.importlib.metadata,
        "version",
        lambda package_name: shot_detection.TRANSNET_PACKAGE_VERSION,
    )
    return package_dir


def test_gradual_transition_uses_first_real_pts_after_transition(fake_transnet_runtime: Path) -> None:
    # 第 2～3 个 prediction 连续超过阈值，表示一个 transition interval。
    # F04 不把它拆成两个 cut，而是锚定到 interval 后第一帧（index 3）的真实 PTS。
    _FakeTransNetV2.predictions = np.array([0.01, 0.70, 0.93, 0.04, 0.02], dtype=np.float64)
    pts = (100_000, 133_333, 200_000, 266_666, 300_000)

    result = detect_proxy_cut_events(
        proxy_path=Path("proxy.mp4"),
        frame_pts_us=pts,
        threshold=0.5,
    )

    assert result.analyzed_frame_count == 5
    assert len(result.events) == 1
    assert result.events[0].proxy_time_us == 266_666
    assert result.events[0].boundary_score == pytest.approx(0.93)
    assert result.torch_version == "2.5.1"
    assert result.detector_device == "cpu"


def test_vfr_pts_are_used_directly_instead_of_frame_div_fps(fake_transnet_runtime: Path) -> None:
    # 这里刻意使用 33ms / 67ms / 40ms 的不规则 PTS 间隔。
    # 若实现偷偷 frame/fps，本断言会得到规则时间而不是 240000us。
    _FakeTransNetV2.predictions = np.array([0.02, 0.03, 0.88, 0.02, 0.01], dtype=np.float64)
    pts = (100_000, 133_000, 200_000, 240_000, 307_000)

    result = detect_proxy_cut_events(
        proxy_path=Path("proxy.mp4"),
        frame_pts_us=pts,
    )

    assert [event.proxy_time_us for event in result.events] == [240_000]


def test_transition_that_reaches_video_tail_does_not_create_invalid_end_cut(fake_transnet_runtime: Path) -> None:
    _FakeTransNetV2.predictions = np.array([0.01, 0.02, 0.80, 0.95], dtype=np.float64)

    result = detect_proxy_cut_events(
        proxy_path=Path("proxy.mp4"),
        frame_pts_us=(0, 40_000, 80_000, 120_000),
    )

    assert result.events == ()


def test_prediction_count_must_exactly_match_real_pts_count(fake_transnet_runtime: Path) -> None:
    _FakeTransNetV2.predictions = np.array([0.1, 0.9, 0.1], dtype=np.float64)

    with pytest.raises(ShotDetectionError) as error:
        detect_proxy_cut_events(
            proxy_path=Path("proxy.mp4"),
            frame_pts_us=(0, 40_000),
        )

    assert error.value.code == "SHOT_DETECTION_FRAME_ALIGNMENT_FAILED"
    assert "不会按 FPS 补偿" in error.value.message


def test_invalid_transition_score_fails_closed(fake_transnet_runtime: Path) -> None:
    _FakeTransNetV2.predictions = np.array([0.1, float("nan"), 0.2], dtype=np.float64)

    with pytest.raises(ShotDetectionError) as error:
        detect_proxy_cut_events(
            proxy_path=Path("proxy.mp4"),
            frame_pts_us=(0, 40_000, 80_000),
        )

    assert error.value.code == "SHOT_DETECTION_MODEL_INVALID"
