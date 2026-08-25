from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from engine.app import character_tracking_v6 as tracking
from engine.app import character_visual_v5 as v5


def observation(
    *,
    at_us: int,
    local_us: int,
    bbox: tuple[int, int, int, int] = (10, 10, 100, 300),
    shot_id: str = "SHOT_1",
) -> v5.Observation:
    return v5.Observation(
        shot_id=shot_id,
        episode_id="EP1",
        episode_order=1,
        shot_ordinal=1,
        source_time_us=at_us,
        local_time_us=local_us,
        bbox=bbox,
        face_bbox=None,
        reference_path="unused.mp4",
        detection_score=0.96,
        face_embedding=None,
        reid_embedding=np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
        body_hist=None,
        face_visible=False,
        detection_source="test",
        frame_width=720,
        frame_height=1280,
        face_score=0.0,
        clarity_score=0.9,
        body_completeness=0.9,
        interference_ratio=0.0,
        other_person_boxes=[],
    )


def tracked(*, ids: list[int], boxes: list[list[float]]) -> SimpleNamespace:
    return SimpleNamespace(
        tracker_id=np.asarray(ids, dtype=np.int64),
        xyxy=np.asarray(boxes, dtype=np.float32),
    )


def install_lightweight_frame_stubs(monkeypatch) -> None:
    monkeypatch.setattr(tracking, "_frame_detections", lambda values: values)
    monkeypatch.setattr(
        tracking.v5,
        "_read_frames",
        lambda _path, local_times: [
            (value, np.zeros((32, 32, 3), dtype=np.uint8))
            for value in local_times
        ],
    )
    monkeypatch.setattr(tracking, "_split_track_on_face_conflict", lambda value: [value])


def test_assign_tracker_rows_uses_iou_instead_of_output_order() -> None:
    left = observation(at_us=0, local_us=0, bbox=(10, 10, 100, 300))
    right = observation(at_us=0, local_us=0, bbox=(300, 20, 80, 260))

    # tracker 输出顺序故意与 observation 输入顺序相反。
    result = tracking._assign_tracker_rows(
        [left, right],
        tracked(
            ids=[21, 11],
            boxes=[
                [300, 20, 380, 280],
                [10, 10, 110, 310],
            ],
        ),
    )

    assert result[21] is right
    assert result[11] is left


def test_track_shot_passes_real_sample_timestamps_to_botsort(monkeypatch) -> None:
    install_lightweight_frame_stubs(monkeypatch)
    values = [
        observation(at_us=5_000_000, local_us=0),
        observation(at_us=5_400_000, local_us=400_000),
    ]

    class FakeBoT:
        def __init__(self) -> None:
            self.timestamps: list[float] = []
            self.frames: list[np.ndarray] = []

        def update(self, _detections, *, frame, timestamp):
            self.timestamps.append(timestamp)
            self.frames.append(frame)
            return tracked(ids=[7], boxes=[[10, 10, 110, 310]])

    fake = FakeBoT()
    result = tracking._track_shot(values, fake, "BoT-SORT")

    assert fake.timestamps == [0.0, 0.4]
    assert len(fake.frames) == 2
    assert len(result[7]) == 2


def test_botsort_runtime_failure_restarts_whole_shot_with_bytetrack(monkeypatch) -> None:
    """不能保留半条 BoT-SORT 结果后从中间切 ByteTrack；fallback 必须从 Shot 开头重跑。"""

    install_lightweight_frame_stubs(monkeypatch)
    values = [
        observation(at_us=8_000_000, local_us=0),
        observation(at_us=8_400_000, local_us=400_000),
        observation(at_us=8_900_000, local_us=900_000),
    ]

    class FailingBoT:
        def __init__(self) -> None:
            self.timestamps: list[float] = []

        def update(self, _detections, *, frame, timestamp):
            self.timestamps.append(timestamp)
            if len(self.timestamps) == 2:
                raise RuntimeError("simulated CMC failure")
            return tracked(ids=[3], boxes=[[10, 10, 110, 310]])

    class FakeByteTrack:
        def __init__(self) -> None:
            self.timestamps: list[float] = []

        def update(self, _detections, *, timestamp):
            self.timestamps.append(timestamp)
            return tracked(ids=[9], boxes=[[10, 10, 110, 310]])

    bot = FailingBoT()
    byte = FakeByteTrack()
    monkeypatch.setattr(tracking, "_make_tracker", lambda: (bot, "BoT-SORT"))
    monkeypatch.setattr(tracking, "_make_bytetrack", lambda: (byte, "ByteTrack fallback"))

    result = tracking.build_tracks(values)

    assert bot.timestamps == [0.0, 0.4]
    # 关键不变量：ByteTrack 从 0.0 开始，完整重放当前 Shot，而不是只接管 0.9s 的尾巴。
    assert byte.timestamps == [0.0, 0.4, 0.9]
    assert len(result) == 1
    assert [item.local_time_us for item in result[0].observations] == [0, 400_000, 900_000]


def test_unconfirmed_observation_is_preserved_as_evidence(monkeypatch) -> None:
    install_lightweight_frame_stubs(monkeypatch)
    value = observation(at_us=2_000_000, local_us=250_000)

    class EmptyTracker:
        def update(self, _detections, *, timestamp):
            return tracked(ids=[], boxes=[])

    result = tracking._track_shot([value], EmptyTracker(), "ByteTrack fallback")

    assert len(result) == 1
    singleton = next(iter(result.values()))
    assert singleton == [value]
