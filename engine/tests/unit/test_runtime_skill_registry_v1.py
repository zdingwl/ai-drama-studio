from __future__ import annotations

from pathlib import Path

import pytest

from engine.skills.registry import (
    CONTRACT_ONLY,
    RuntimeSkillNotReadyError,
    UnknownRuntimeSkillError,
    get_runtime_skill,
    list_runtime_skills,
    validate_runtime_skill_ref,
)


EXPECTED_SKILLS = {
    "shot_facts",
    "episode_understanding",
    "screenplay_reconstruction",
    "country_adaptation",
    "script_to_storyboard",
    "qwen3_tts",
    "video_qc",
}


def test_registry_contains_exact_v1_contract_baseline() -> None:
    contracts = list_runtime_skills()

    assert {contract.skill_id for contract in contracts} == EXPECTED_SKILLS
    assert {contract.version for contract in contracts} == {"1.0.0"}
    assert {contract.status for contract in contracts} == {CONTRACT_ONLY}


def test_every_registered_contract_file_exists() -> None:
    repo_root = Path(__file__).resolve().parents[3]

    for contract in list_runtime_skills():
        contract_file = repo_root / contract.contract_path
        assert contract_file.is_file(), contract.contract_path
        text = contract_file.read_text(encoding="utf-8")
        assert f"**Skill ID:** `{contract.skill_id}`" in text
        assert f"**Version:** `{contract.version}`" in text
        assert "**Status:** `CONTRACT_ONLY`" in text


def test_exact_contract_reference_can_be_validated_without_dispatch() -> None:
    contract = validate_runtime_skill_ref("shot_facts", "1.0.0")

    assert contract == get_runtime_skill("shot_facts", "1.0.0")
    assert contract.is_runtime_ready is False


def test_live_inference_gate_rejects_contract_only_skill() -> None:
    with pytest.raises(RuntimeSkillNotReadyError, match="not ready for live inference"):
        validate_runtime_skill_ref(
            "shot_facts",
            "1.0.0",
            require_runtime_ready=True,
        )


@pytest.mark.parametrize(
    ("skill_id", "version"),
    [
        ("unknown_skill", "1.0.0"),
        ("shot_facts", "latest"),
        ("shot_facts", "2.0.0"),
    ],
)
def test_unknown_or_unpinned_skill_reference_fails_closed(
    skill_id: str,
    version: str,
) -> None:
    with pytest.raises(UnknownRuntimeSkillError):
        validate_runtime_skill_ref(skill_id, version)
