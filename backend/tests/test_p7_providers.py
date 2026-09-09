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
    assert provider.profile["mode"] == "CLOUD_API"
    assert provider.profile["video_input"] == "ARK_FILES_API_FULL_EPISODE"


def test_p7_local_qwen_defaults_to_30b_a3b_thinking() -> None:
    settings = Settings(_env_file=None)
    provider = build_source_episode_understanding_provider(
        settings,
        SourceUnderstandingProvider.QWEN3_VL_LOCAL,
    )

    assert isinstance(provider, LocalQwenSourceEpisodeUnderstandingProvider)
    assert provider.model_name == "Qwen/Qwen3-VL-30B-A3B-Thinking"
    assert provider.profile["mode"] == "LOCAL_OPENAI_COMPATIBLE"
    assert provider.profile["video_input"] == "VLLM_FILE_URL_FULL_EPISODE"
