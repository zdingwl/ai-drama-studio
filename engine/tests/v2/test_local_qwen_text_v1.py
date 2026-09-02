from __future__ import annotations

from engine.app import local_qwen_text_v1 as qwen


class _FakeLocalAdapter:
    def __init__(self, *, ready: bool = True, outputs: dict[int, str] | None = None) -> None:
        self.ready = ready
        self.outputs = outputs or {}
        self.generate_calls = 0
        self.last_requests = ()

    def runtime_preflight(self):
        if self.ready:
            return {"status": "READY", "missing": []}
        return {"status": "NOT_CONFIGURED", "missing": ["checkpoint"]}

    def generate_many(self, requests):
        self.generate_calls += 1
        self.last_requests = tuple(requests)
        return dict(self.outputs)

    def last_batch_diagnostics(self):
        return {}


def test_runtime_status_accepts_breakdown_local_checkpoint_without_http(monkeypatch) -> None:
    adapter = _FakeLocalAdapter(ready=True)
    monkeypatch.setattr(qwen, "semantic_model_status", lambda: {"ready": False})
    monkeypatch.setattr(qwen, "_local_adapter", lambda: adapter)

    status = qwen.local_qwen_text_runtime_status()

    assert status["ready"] is True
    assert status["provider"] == "qwen3-vl-local-subprocess"
    assert status["http_configured"] is False
    assert status["local_ready"] is True


def test_request_many_uses_one_local_model_batch_when_http_is_not_configured(monkeypatch) -> None:
    adapter = _FakeLocalAdapter(
        ready=True,
        outputs={
            1: '{"characters":[{"source_character_id":"CHAR_1"}]}',
            2: '{"scenes":[{"scene_key":"SCENE_1"}]}',
        },
    )
    monkeypatch.setattr(qwen, "semantic_model_status", lambda: {"ready": False})
    monkeypatch.setattr(qwen, "_local_adapter", lambda: adapter)

    output = qwen.request_local_qwen_json_many(["character prompt", "scene prompt"])

    assert adapter.generate_calls == 1
    assert len(adapter.last_requests) == 2
    assert output[0]["characters"][0]["source_character_id"] == "CHAR_1"
    assert output[1]["scenes"][0]["scene_key"] == "SCENE_1"


def test_http_failure_falls_back_to_existing_local_runtime(monkeypatch) -> None:
    adapter = _FakeLocalAdapter(ready=True, outputs={1: '{"ok":true}'})
    monkeypatch.setattr(
        qwen,
        "semantic_model_status",
        lambda: {"ready": True, "base_url": "http://127.0.0.1:8001/v1", "model": "Qwen3-VL-4B-Instruct"},
    )
    monkeypatch.setattr(
        qwen,
        "_request_http_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(qwen.LocalQwenTextError("offline")),
    )
    monkeypatch.setattr(qwen, "_local_adapter", lambda: adapter)

    output = qwen.request_local_qwen_json("prompt")

    assert output == {"ok": True}
    assert adapter.generate_calls == 1
