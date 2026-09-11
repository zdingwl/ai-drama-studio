from types import SimpleNamespace

from app.target_assets import service


class RecordingContext:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, int]] = []

    def checkpoint(self, payload: dict, *, progress_percent: int) -> None:
        self.calls.append((payload, progress_percent))


def test_p13_checkpoint_keeps_generation_context_for_retry_resume() -> None:
    context = RecordingContext()
    fingerprint = "a" * 64

    service._checkpoint(
        context,
        stage="design_visual_identity_packets",
        progress_percent=25,
        generation_sequence=3,
        generation_base_fingerprint=fingerprint,
    )

    assert context.calls == [
        (
            {
                "stage": "design_visual_identity_packets",
                "generation_sequence": 3,
                "generation_base_fingerprint": fingerprint,
            },
            25,
        )
    ]
    task = SimpleNamespace(checkpoint_json=context.calls[0][0])
    assert service._task_generation(task) == (3, fingerprint)
