import pytest

from engine.app import breakdown_p2_acceptance_v1 as acceptance


def structural(passed: bool = True) -> acceptance.StructuralAssessment:
    return acceptance.StructuralAssessment(
        passed=passed,
        checks=({"name": "test", "passed": passed, "detail": None},),
    )


def review(score: float = 4.0, *, no_ocr: bool = False, blocking: bool = False):
    return {
        "scores": {key: score for key in acceptance.ALL_REVIEW_KEYS},
        "not_applicable": ["ocr_text"] if no_ocr else [],
        "blocking_issues": ["visible identity merge error"] if blocking else [],
    }


def test_structural_pass_still_requires_real_human_review() -> None:
    result = acceptance.evaluate_acceptance(structural(), None)
    assert result["status"] == "NEEDS_HUMAN_REVIEW"
    assert result["average_score"] is None


def test_all_required_scores_at_four_pass() -> None:
    result = acceptance.evaluate_acceptance(structural(), review(4.0))
    assert result["status"] == "PASS"
    assert result["minimum_score"] == 4.0


def test_ocr_can_be_explicitly_not_applicable() -> None:
    payload = review(4.2, no_ocr=True)
    payload["scores"]["ocr_text"] = None
    result = acceptance.evaluate_acceptance(structural(), payload)
    assert result["status"] == "PASS"


def test_low_score_or_blocking_issue_needs_tuning() -> None:
    assert acceptance.evaluate_acceptance(structural(), review(3.5))["status"] == "NEEDS_TUNING"
    assert acceptance.evaluate_acceptance(structural(), review(5.0, blocking=True))["status"] == "NEEDS_TUNING"


def test_structural_failure_cannot_be_overridden_by_high_review_scores() -> None:
    result = acceptance.evaluate_acceptance(structural(False), review(5.0))
    assert result["status"] == "STRUCTURAL_FAIL"


def test_invalid_review_score_fails_closed() -> None:
    payload = review(4.0)
    payload["scores"]["vlm_scene"] = 6
    with pytest.raises(acceptance.BreakdownP2AcceptanceError, match="0..5"):
        acceptance.evaluate_acceptance(structural(), payload)


def test_report_comparison_prefers_pass_then_higher_score() -> None:
    reports = [
        {"run": {"run_id": "B"}, "assessment": {"status": "PASS", "average_score": 4.1, "minimum_score": 4.0}},
        {"run": {"run_id": "A"}, "assessment": {"status": "PASS", "average_score": 4.8, "minimum_score": 4.5}},
        {"run": {"run_id": "C"}, "assessment": {"status": "NEEDS_TUNING", "average_score": 3.9, "minimum_score": 3.0}},
    ]
    ranked = acceptance.compare_acceptance_reports(reports)
    assert [item["run_id"] for item in ranked] == ["A", "B", "C"]
