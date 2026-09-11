import pytest
from pydantic import ValidationError

from app.target_assets.schemas import TargetAssetsReviewCommand


def test_p13_review_reason_rejects_blank_and_normalizes_whitespace() -> None:
    with pytest.raises(ValidationError):
        TargetAssetsReviewCommand(
            expected_target_bible_artifact_id="bible-1",
            expected_generation_sequence=1,
            reason="   ",
        )

    command = TargetAssetsReviewCommand(
        expected_target_bible_artifact_id="bible-1",
        expected_generation_sequence=1,
        reason="  visual identities are consistent  ",
    )
    assert command.reason == "visual identities are consistent"
