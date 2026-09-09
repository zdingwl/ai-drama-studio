from app.core.config import Settings
from app.projects.enums import SourceUnderstandingProvider
from app.understanding.providers import (
    DoubaoSeedSourceEpisodeUnderstandingProvider,
    LocalQwenSourceEpisodeUnderstandingProvider,
    build_source_episode_understanding_provider,
)


def test_p7_doubao_provider_profile_is_cloud_full_episode() -> None:
    settings = Settings(_env_file=None, p7_doubao_api_key="test-only")
    provider = build_source_episode_understanding_provider(
        settings,
        SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API,
    )

    assert isinstance(provider, DoubaoSeedSourceEpisodeUnderstandingProvider)
    assert provider.model_name == "doubao-seed-2-1-pro-260628"
    assert provider.profile["selection"] == "DOUBAO_SEED_2_1_PRO_API"
    assert provider.profile["mode"] == "CLOUD_API"
    assert provider.profile["video_input"] == "ARK_FILES_API_FULL_EPISODE"


def test_p7_local_qwen38_is_high_quality_choice() -> None:
    settings = Settings(_env_file=None)
    provider = build_source_episode_understanding_provider(
        settings,
        SourceUnderstandingProvider.QWEN3_8_27B_LOCAL,
    )

    assert isinstance(provider, LocalQwenSourceEpisodeUnderstandingProvider)
    assert provider.model_name == "Qwen/Qwen3.8-27B"
    assert provider.profile["selection"] == "QWEN3_8_27B_LOCAL"
    assert provider.profile["mode"] == "LOCAL_OPENAI_COMPATIBLE"
    assert provider.profile["video_input"] == "VLLM_FILE_URL_FULL_EPISODE"


def test_p7_local_qwen3_vl_8b_is_low_footprint_choice() -> None:
    settings = Settings(_env_file=None)
    provider = build_source_episode_understanding_provider(
        settings,
        SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL,
    )

    assert isinstance(provider, LocalQwenSourceEpisodeUnderstandingProvider)
    assert provider.model_name == "Qwen/Qwen3-VL-8B-Thinking"
    assert provider.profile["selection"] == "QWEN3_VL_8B_THINKING_LOCAL"
    assert provider.profile["mode"] == "LOCAL_OPENAI_COMPATIBLE"
    assert provider.profile["video_input"] == "VLLM_FILE_URL_FULL_EPISODE"
