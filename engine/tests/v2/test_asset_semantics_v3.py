from engine.app.asset_semantics_v3 import semantic_model_status


def test_qwen_semantics_is_explicitly_not_ready_without_configuration(monkeypatch) -> None:
    monkeypatch.delenv("AI_DRAMA_VLM_BASE_URL", raising=False)
    monkeypatch.delenv("AI_DRAMA_VLM_MODEL", raising=False)
    monkeypatch.delenv("AI_DRAMA_VLM_API_KEY", raising=False)

    status = semantic_model_status()

    assert status["ready"] is False
    assert status["configured"] is False
    assert status["model"] is None
    assert status["base_url"] is None
    assert "Qwen3-VL" in status["purpose"]
