import pytest
import httpx
from types import SimpleNamespace

from app.core.errors import AppError
from app.core.config import Settings
from app.p15.schemas import GenerationSegment
import app.p16.runtime as p16_runtime
from app.p16.provider import (
    H3RuntimeMode,
    LocalComfyUIH3Config,
    LocalComfyUIH3Provider,
    LocalSGLangH3Config,
    LocalSGLangH3Provider,
    MiniMaxH3Config,
    MiniMaxH3Provider,
    build_h3_generation_provider,
)


def _segment(duration_us: int = 1_000_000) -> GenerationSegment:
    return GenerationSegment(
        generation_segment_id="seg:ep-1:0001",
        episode_id="ep-1",
        episode_order=1,
        segment_number=1,
        storyboard_shot_ids=["sb:ep-1:shot-1"],
        start_us=0,
        end_us=duration_us,
        duration_us=duration_us,
        output_ratio="9:16",
        continuation_index=1,
        continuation_count=1,
        generation_prompt="A woman enters the room and speaks naturally.",
        negative_prompt="watermark; source-language subtitle",
    )


def test_p16_settings_read_standard_backend_env_names(monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_P16_H3_RUNTIME", "LOCAL_SGLANG")
    monkeypatch.setenv("AI_DRAMA_P16_H3_LOCAL_BASE_URL", "http://127.0.0.1:30123")

    settings = Settings()
    provider = build_h3_generation_provider(settings)

    assert settings.p16_h3_local_base_url == "http://127.0.0.1:30123"
    assert provider.profile()["base_url"] == "http://127.0.0.1:30123"


def _comfy_config() -> LocalComfyUIH3Config:
    return LocalComfyUIH3Config(
        base_url="http://127.0.0.1:8188",
        model="MiniMaxAI/MiniMax-H3",
        unet_name="minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        clip_name="qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        video_vae_name="minimax_h3_video_vae_fp16.safetensors",
        audio_vae_name="minimax_h3_audio_vae_fp32.safetensors",
        short_edge=768,
        num_inference_steps=20,
        timeout_seconds=3600,
        poll_interval_seconds=1,
        readiness_timeout_seconds=3,
        output_prefix="ai_drama_studio/h3",
    )


def _combo(options: list[str]) -> list:
    return [options, {}]


def _comfy_object_info() -> dict:
    required_nodes = {
        name: {"input": {"required": {}}}
        for name in LocalComfyUIH3Provider._required_nodes
    }
    required_nodes["UNETLoader"]["input"]["required"]["unet_name"] = _combo([
        "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    ])
    required_nodes["CLIPLoader"]["input"]["required"]["clip_name"] = _combo([
        "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
    ])
    required_nodes["VAELoader"]["input"]["required"]["vae_name"] = _combo([
        "minimax_h3_video_vae_fp16.safetensors",
        "minimax_h3_audio_vae_fp32.safetensors",
    ])
    return required_nodes


def test_default_h3_runtime_is_windows_comfyui_and_does_not_require_cloud_key(monkeypatch) -> None:
    monkeypatch.delenv("AI_DRAMA_P16_H3_RUNTIME", raising=False)
    monkeypatch.delenv("AI_DRAMA_P16_MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    provider = build_h3_generation_provider()

    assert isinstance(provider, LocalComfyUIH3Provider)
    assert provider.profile()["runtime_mode"] == H3RuntimeMode.LOCAL_COMFYUI.value
    assert provider.profile()["base_url"] == "http://127.0.0.1:8188"
    assert provider.profile()["task"] == "multi-reference-native-av"
    assert provider.profile()["model_variant"] == "ref2va-primary/fl2va-legacy"
    assert provider.profile()["ref2va_unet_name"] == "minimax_h3_ref2va_pruned_int8_convrot.safetensors"


def test_explicit_sglang_runtime_remains_available(monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_P16_H3_RUNTIME", "LOCAL_SGLANG")

    provider = build_h3_generation_provider()

    assert isinstance(provider, LocalSGLangH3Provider)
    assert provider.profile()["runtime_mode"] == H3RuntimeMode.LOCAL_SGLANG.value
    assert provider.profile()["base_url"] == "http://127.0.0.1:30010"


def test_local_h3_request_matches_sglang_async_video_contract() -> None:
    provider = LocalSGLangH3Provider(
        LocalSGLangH3Config(
            base_url="http://127.0.0.1:30010",
            model="MiniMaxAI/MiniMax-H3",
            short_edge=768,
            num_inference_steps=50,
            flow_shift=12.0,
            audio_flow_shift=3.0,
            timeout_seconds=1800,
            poll_interval_seconds=1,
            readiness_timeout_seconds=3,
        )
    )

    payload = provider.request_payload(_segment())

    assert payload["model"] == "MiniMaxAI/MiniMax-H3"
    assert payload["seconds"] == 4
    assert payload["task"] == "t2va"
    assert payload["conditions"] == []
    assert payload["target"] == {
        "short_edge": 768,
        "aspect_ratio": "9:16",
        "duration_seconds": 4.0,
    }
    assert payload["num_outputs_per_prompt"] == 1
    assert payload["num_inference_steps"] == 50
    assert payload["flow_shift"] == 12.0
    assert payload["audio_flow_shift"] == 3.0
    assert "Avoid: watermark; source-language subtitle" in payload["prompt"]


def test_comfyui_readiness_checks_native_h3_nodes_and_model_files() -> None:
    provider = LocalComfyUIH3Provider(_comfy_config())

    class FakeClient:
        def get(self, url: str):
            if url.endswith("/system_stats"):
                return httpx.Response(200, json={"system": {"comfyui_version": "0.35.1"}})
            if url.endswith("/object_info"):
                return httpx.Response(200, json=_comfy_object_info())
            raise AssertionError(url)

    readiness = provider.readiness(FakeClient())

    assert readiness.ready is True
    assert readiness.state.value == "READY"
    assert readiness.runtime_mode == "LOCAL_COMFYUI"
    assert readiness.provider == "local-comfyui"


def test_comfyui_readiness_fails_closed_when_h3_weights_are_missing() -> None:
    provider = LocalComfyUIH3Provider(_comfy_config())
    object_info = _comfy_object_info()
    object_info["UNETLoader"]["input"]["required"]["unet_name"] = _combo(["other.safetensors"])

    class FakeClient:
        def get(self, url: str):
            if url.endswith("/system_stats"):
                return httpx.Response(200, json={"system": {"comfyui_version": "0.35.1"}})
            if url.endswith("/object_info"):
                return httpx.Response(200, json=object_info)
            raise AssertionError(url)

    readiness = provider.readiness(FakeClient())

    assert readiness.ready is False
    assert readiness.state.value == "MODEL_MISMATCH"
    assert "minimax_h3_fl2va_pruned_int8_convrot.safetensors" in readiness.message
    assert "minimax_h3_ref2va_pruned_int8_convrot.safetensors" in readiness.message


def test_comfyui_workflow_uses_native_audio_video_h3_pipeline() -> None:
    provider = LocalComfyUIH3Provider(_comfy_config())

    payload = provider.workflow_payload(_segment(4_000_000), seed=1234)
    graph = payload["prompt"]

    assert graph["1"] == {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
            "weight_dtype": "default",
        },
    }
    assert graph["5"]["class_type"] == "MiniMaxH3ImageToVideo"
    assert graph["5"]["inputs"]["width"] == 768
    assert graph["5"]["inputs"]["height"] == 1344
    assert graph["5"]["inputs"]["length"] == 107
    assert graph["6"]["inputs"]["noise_seed"] == 1234
    assert graph["9"]["inputs"]["steps"] == 20
    assert graph["12"]["class_type"] == "VAEDecodeAudio"
    assert graph["13"]["inputs"]["audio"] == ["12", 0]
    assert graph["14"]["inputs"]["format"] == "mp4"
    assert "Avoid: watermark; source-language subtitle" in graph["5"]["inputs"]["prompt"]


def test_comfyui_history_media_extraction_accepts_save_video_result() -> None:
    provider = LocalComfyUIH3Provider(_comfy_config())
    entry = {
        "outputs": {
            "14": {
                "video": [
                    {"filename": "h3_00001_.mp4", "subfolder": "ai_drama_studio/h3", "type": "output"}
                ]
            }
        }
    }

    assert provider._find_saved_media(entry) == {
        "filename": "h3_00001_.mp4",
        "subfolder": "ai_drama_studio/h3",
        "type": "output",
    }


def test_local_runtime_readiness_checks_health_and_expected_model() -> None:
    provider = LocalSGLangH3Provider(
        LocalSGLangH3Config(
            base_url="http://127.0.0.1:30010",
            model="MiniMaxAI/MiniMax-H3",
            short_edge=768,
            num_inference_steps=50,
            flow_shift=12.0,
            audio_flow_shift=3.0,
            timeout_seconds=60,
            poll_interval_seconds=1,
            readiness_timeout_seconds=3,
        )
    )

    class FakeClient:
        def get(self, url: str):
            if url.endswith("/health"):
                return httpx.Response(200, content=b"")
            if url.endswith("/v1/models"):
                return httpx.Response(200, json={"object": "list", "data": [{"id": "MiniMaxAI/MiniMax-H3"}]})
            raise AssertionError(url)

    readiness = provider.readiness(FakeClient())

    assert readiness.ready is True
    assert readiness.state.value == "READY"
    assert readiness.model == "MiniMaxAI/MiniMax-H3"


def test_local_runtime_readiness_reports_connection_failure_without_creating_a_job() -> None:
    provider = LocalSGLangH3Provider(
        LocalSGLangH3Config(
            base_url="http://127.0.0.1:30010",
            model="MiniMaxAI/MiniMax-H3",
            short_edge=768,
            num_inference_steps=50,
            flow_shift=12.0,
            audio_flow_shift=3.0,
            timeout_seconds=60,
            poll_interval_seconds=1,
            readiness_timeout_seconds=3,
        )
    )

    class OfflineClient:
        def get(self, url: str):
            request = httpx.Request("GET", url)
            raise httpx.ConnectError("offline", request=request)

    readiness = provider.readiness(OfflineClient())

    assert readiness.ready is False
    assert readiness.state.value == "UNAVAILABLE"
    assert "未启动" in readiness.message


def test_local_runtime_non_json_error_keeps_http_diagnostics() -> None:
    provider = LocalSGLangH3Provider(
        LocalSGLangH3Config(
            base_url="http://127.0.0.1:30010",
            model="MiniMaxAI/MiniMax-H3",
            short_edge=768,
            num_inference_steps=50,
            flow_shift=12.0,
            audio_flow_shift=3.0,
            timeout_seconds=60,
            poll_interval_seconds=1,
            readiness_timeout_seconds=3,
        )
    )
    response = httpx.Response(502, headers={"content-type": "text/html"}, text="<html>proxy failure</html>")

    with pytest.raises(AppError) as captured:
        provider._request_json(response, code="P16_LOCAL_RUNTIME_CREATE_FAILED", action="create")

    assert captured.value.code == "P16_LOCAL_RUNTIME_CREATE_FAILED"
    assert "HTTP 502" in captured.value.message
    assert "text/html" in captured.value.message
    assert "proxy failure" in captured.value.message


def test_local_and_cloud_duration_rules_remain_bounded() -> None:
    local = LocalSGLangH3Provider(
        LocalSGLangH3Config(
            base_url="http://127.0.0.1:30010",
            model="MiniMaxAI/MiniMax-H3",
            short_edge=768,
            num_inference_steps=50,
            flow_shift=12.0,
            audio_flow_shift=3.0,
            timeout_seconds=60,
            poll_interval_seconds=1,
            readiness_timeout_seconds=3,
        )
    )
    cloud = MiniMaxH3Provider(
        MiniMaxH3Config(
            api_key="server-only",
            base_url="https://api.minimax.io",
            model="MiniMax-H3-Max",
            resolution="768P",
            timeout_seconds=60,
            poll_interval_seconds=1,
        )
    )

    assert local.requested_duration(_segment(1_000_000)) == 4
    assert local.requested_duration(_segment(14_200_000)) == 15
    assert cloud.requested_duration(_segment(1_000_000)) == 5


def test_cloud_fallback_is_explicit_and_requires_key(monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_P16_H3_RUNTIME", "MINIMAX_CLOUD")
    monkeypatch.delenv("AI_DRAMA_P16_MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    with pytest.raises(AppError) as captured:
        build_h3_generation_provider()

    assert captured.value.code == "P16_PROVIDER_NOT_CONFIGURED"


def test_explicit_cloud_mode_builds_cloud_provider(monkeypatch) -> None:
    monkeypatch.setenv("AI_DRAMA_P16_H3_RUNTIME", "MINIMAX_CLOUD")
    monkeypatch.setenv("AI_DRAMA_P16_MINIMAX_API_KEY", "test-only")

    provider = build_h3_generation_provider()

    assert isinstance(provider, MiniMaxH3Provider)
    assert provider.profile()["runtime_mode"] == H3RuntimeMode.MINIMAX_CLOUD.value
    assert provider.provider_name == "minimax-cloud"


def test_retry_replaces_failed_p16_task_when_runtime_fingerprint_changes(monkeypatch) -> None:
    old_task = SimpleNamespace(
        id="old-task",
        task_type=p16_runtime.P16_TASK_TYPE,
        status=p16_runtime.TaskStatus.FAILED,
        project_id="project-1",
        input_artifact_ids_json=["storyboard", "segments", "assets"],
        input_fingerprint="a" * 64,
        checkpoint_json={"p16_generation_sequence": 1},
        attempt=1,
        max_attempts=3,
    )
    replacement = SimpleNamespace(id="new-task", checkpoint_json={})
    inputs = object()

    class FakeProvider:
        def assert_ready(self) -> None:
            return None

    class FakeDB:
        def add(self, value) -> None:
            self.added = value

        def commit(self) -> None:
            return None

        def refresh(self, value) -> None:
            return None

    captured: dict[str, str] = {}
    monkeypatch.setattr(p16_runtime, "get_project", lambda db, project_id: SimpleNamespace(id=project_id))
    monkeypatch.setattr(p16_runtime, "load_inputs", lambda db, project: inputs)
    monkeypatch.setattr(p16_runtime, "input_artifact_ids", lambda loaded: ["storyboard", "segments", "assets"])
    monkeypatch.setattr(p16_runtime, "build_h3_generation_provider", lambda: FakeProvider())
    monkeypatch.setattr(p16_runtime, "_fingerprint", lambda loaded, sequence, provider: "b" * 64)

    def fake_create(db, *, project_id: str, idempotency_key: str):
        captured["project_id"] = project_id
        captured["idempotency_key"] = idempotency_key
        return replacement

    monkeypatch.setattr(p16_runtime, "create_generation_task", fake_create)

    result = p16_runtime.replace_generation_task_for_retry_if_needed(
        FakeDB(),
        project_id="project-1",
        task=old_task,
    )

    assert result is replacement
    assert replacement.checkpoint_json["p16_replaces_failed_task_id"] == "old-task"
    assert captured["project_id"] == "project-1"
    assert captured["idempotency_key"].startswith("p16-runtime-retry-old-task-")


def test_retry_replaces_failed_p16_task_when_current_artifact_lineage_changes(monkeypatch) -> None:
    old_task = SimpleNamespace(
        id="old-task",
        task_type=p16_runtime.P16_TASK_TYPE,
        status=p16_runtime.TaskStatus.FAILED,
        project_id="project-1",
        input_artifact_ids_json=["old-storyboard", "old-segments", "assets"],
        input_fingerprint="a" * 64,
        checkpoint_json={"p16_generation_sequence": 1},
        attempt=2,
        max_attempts=3,
    )
    replacement = SimpleNamespace(id="new-task", checkpoint_json={})
    inputs = object()

    class FakeProvider:
        def assert_ready(self) -> None:
            return None

    class FakeDB:
        def add(self, value) -> None:
            self.added = value

        def commit(self) -> None:
            return None

        def refresh(self, value) -> None:
            return None

    monkeypatch.setattr(p16_runtime, "get_project", lambda db, project_id: SimpleNamespace(id=project_id))
    monkeypatch.setattr(p16_runtime, "load_inputs", lambda db, project: inputs)
    monkeypatch.setattr(p16_runtime, "input_artifact_ids", lambda loaded: ["new-storyboard", "new-segments", "assets"])
    monkeypatch.setattr(p16_runtime, "build_h3_generation_provider", lambda: FakeProvider())
    monkeypatch.setattr(p16_runtime, "_fingerprint", lambda loaded, sequence, provider: "b" * 64)
    monkeypatch.setattr(p16_runtime, "create_generation_task", lambda db, **kwargs: replacement)

    result = p16_runtime.replace_generation_task_for_retry_if_needed(
        FakeDB(),
        project_id="project-1",
        task=old_task,
    )

    assert result is replacement
    assert replacement.checkpoint_json["p16_replaces_failed_task_id"] == "old-task"


def test_resume_replaces_interrupted_p16_task_when_current_artifact_lineage_changes(monkeypatch) -> None:
    old_task = SimpleNamespace(
        id="old-task",
        task_type=p16_runtime.P16_TASK_TYPE,
        status=p16_runtime.TaskStatus.INTERRUPTED,
        project_id="project-1",
        input_artifact_ids_json=["old-storyboard", "old-segments", "assets"],
        input_fingerprint="a" * 64,
        checkpoint_json={"p16_generation_sequence": 1},
        attempt=1,
        max_attempts=3,
    )
    replacement = SimpleNamespace(id="new-task", checkpoint_json={})
    inputs = object()

    class FakeProvider:
        def assert_ready(self) -> None:
            return None

    class FakeDB:
        def add(self, value) -> None:
            self.added = value

        def commit(self) -> None:
            return None

        def refresh(self, value) -> None:
            return None

    monkeypatch.setattr(p16_runtime, "get_project", lambda db, project_id: SimpleNamespace(id=project_id))
    monkeypatch.setattr(p16_runtime, "load_inputs", lambda db, project: inputs)
    monkeypatch.setattr(p16_runtime, "input_artifact_ids", lambda loaded: ["new-storyboard", "new-segments", "assets"])
    monkeypatch.setattr(p16_runtime, "build_h3_generation_provider", lambda: FakeProvider())
    monkeypatch.setattr(p16_runtime, "_fingerprint", lambda loaded, sequence, provider: "b" * 64)
    monkeypatch.setattr(p16_runtime, "create_generation_task", lambda db, **kwargs: replacement)

    result = p16_runtime.replace_generation_task_for_retry_if_needed(
        FakeDB(),
        project_id="project-1",
        task=old_task,
    )

    assert result is replacement
    assert replacement.checkpoint_json["p16_replaces_task_id"] == "old-task"
    assert replacement.checkpoint_json["p16_replaces_failed_task_id"] is None


def test_comfyui_reference_workflow_uses_autogrow_v3_container() -> None:
    provider = LocalComfyUIH3Provider(_comfy_config())
    segment = _segment().model_copy(update={"reference_conditions": [object(), object()]})

    payload = provider.workflow_payload(
        segment,
        seed=7,
        uploaded_images=["refs/one.png", "refs/two.png"],
    )

    inputs = payload["prompt"]["5"]["inputs"]
    assert inputs["ref_images"] == {
        "ref_image_0": ["15", 0],
        "ref_image_1": ["16", 0],
    }
    assert "ref_image_1" not in {key for key in inputs if key != "ref_images"}
