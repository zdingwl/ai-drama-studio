from types import SimpleNamespace

from pydantic import SecretStr

from app.projects.enums import SourceUnderstandingProvider
from app.replica_pipeline.localized_storyboard import _provider


def test_storyboard_localization_uses_volcengine_even_when_source_provider_is_local() -> None:
    settings = SimpleNamespace(
        p7_doubao_api_key=SecretStr("test-key"),
        p7_doubao_model="doubao-seed-2-1-pro-260628",
    )

    provider = _provider(settings, SourceUnderstandingProvider.QWEN3_8_27B_LOCAL)

    assert provider.provider_name == "volcengine-ark"
    assert provider.model_name == "doubao-seed-2-1-pro-260628"
