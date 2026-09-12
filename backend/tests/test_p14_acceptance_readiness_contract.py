from app.p14.acceptance_readiness import MANUAL_CHECKS_REQUIRED, P14AcceptanceReadiness


def test_p14_readiness_contract_keeps_technical_and_human_pass_separate() -> None:
    result = P14AcceptanceReadiness(
        project_id="project-1",
        technical_ready=False,
        blockers=["缺少 CURRENT TARGET_AUDIO。"],
    )

    assert result.technical_ready is False
    assert result.blockers
    assert any("P14 PASS" in item for item in MANUAL_CHECKS_REQUIRED)
    assert "p14_pass" not in P14AcceptanceReadiness.model_fields
    assert "capability_available" not in P14AcceptanceReadiness.model_fields
