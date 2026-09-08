from types import SimpleNamespace

import numpy as np

from app.core.config import get_settings
from app.evidence.providers import RapidOcrProvider


def test_rapidocr_provider_accepts_numpy_box_arrays(monkeypatch) -> None:
    provider = RapidOcrProvider(get_settings())
    rapid_output = SimpleNamespace(
        txts=("画面字幕",),
        scores=(0.99,),
        boxes=np.array(
            [[[10.0, 10.0], [100.0, 10.0], [100.0, 40.0], [10.0, 40.0]]],
            dtype=np.float32,
        ),
    )

    monkeypatch.setattr(provider, "_get_engine", lambda: lambda image: rapid_output)

    detections = provider.recognize(np.zeros((64, 128, 3), dtype=np.uint8))

    assert len(detections) == 1
    assert detections[0].text == "画面字幕"
    assert detections[0].confidence == 0.99
    assert detections[0].bbox == [
        [10.0, 10.0],
        [100.0, 10.0],
        [100.0, 40.0],
        [10.0, 40.0],
    ]
