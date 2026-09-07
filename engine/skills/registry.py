from __future__ import annotations

from dataclasses import dataclass
from typing import Final

CONTRACT_ONLY: Final[str] = "CONTRACT_ONLY"
RUNTIME_READY: Final[str] = "RUNTIME_READY"


class UnknownRuntimeSkillError(ValueError):
    """Raised when a caller references an unregistered skill id/version."""


class RuntimeSkillNotReadyError(RuntimeError):
    """Raised when a contract-only skill is requested for live inference."""


@dataclass(frozen=True, slots=True)
class RuntimeSkillContract:
    skill_id: str
    version: str
    status: str
    contract_path: str

    @property
    def is_runtime_ready(self) -> bool:
        return self.status == RUNTIME_READY


RUNTIME_SKILLS: Final[dict[tuple[str, str], RuntimeSkillContract]] = {
    ("shot_facts", "1.0.0"): RuntimeSkillContract(
        skill_id="shot_facts",
        version="1.0.0",
        status=CONTRACT_ONLY,
        contract_path="engine/skills/shot_facts/SKILL.md",
    ),
    ("episode_understanding", "1.0.0"): RuntimeSkillContract(
        skill_id="episode_understanding",
        version="1.0.0",
        status=CONTRACT_ONLY,
        contract_path="engine/skills/episode_understanding/SKILL.md",
    ),
    ("screenplay_reconstruction", "1.0.0"): RuntimeSkillContract(
        skill_id="screenplay_reconstruction",
        version="1.0.0",
        status=CONTRACT_ONLY,
        contract_path="engine/skills/screenplay_reconstruction/SKILL.md",
    ),
    ("country_adaptation", "1.0.0"): RuntimeSkillContract(
        skill_id="country_adaptation",
        version="1.0.0",
        status=CONTRACT_ONLY,
        contract_path="engine/skills/country_adaptation/SKILL.md",
    ),
    ("script_to_storyboard", "1.0.0"): RuntimeSkillContract(
        skill_id="script_to_storyboard",
        version="1.0.0",
        status=CONTRACT_ONLY,
        contract_path="engine/skills/script_to_storyboard/SKILL.md",
    ),
    ("qwen3_tts", "1.0.0"): RuntimeSkillContract(
        skill_id="qwen3_tts",
        version="1.0.0",
        status=CONTRACT_ONLY,
        contract_path="engine/skills/qwen3_tts/SKILL.md",
    ),
    ("video_qc", "1.0.0"): RuntimeSkillContract(
        skill_id="video_qc",
        version="1.0.0",
        status=CONTRACT_ONLY,
        contract_path="engine/skills/video_qc/SKILL.md",
    ),
}


def get_runtime_skill(skill_id: str, version: str) -> RuntimeSkillContract:
    """Return one exact registered skill contract.

    Version resolution is deliberately strict. Production callers must pin an
    explicit version; aliases such as ``latest`` are not accepted.
    """

    key = (str(skill_id).strip(), str(version).strip())
    try:
        return RUNTIME_SKILLS[key]
    except KeyError as exc:
        raise UnknownRuntimeSkillError(
            f"Unknown runtime skill reference: {key[0]}@{key[1]}"
        ) from exc


def validate_runtime_skill_ref(
    skill_id: str,
    version: str,
    *,
    require_runtime_ready: bool = False,
) -> RuntimeSkillContract:
    """Validate a pinned skill reference and optionally enforce live readiness.

    ``require_runtime_ready=True`` is the integration gate Providers should use
    before dispatching live model inference. It intentionally rejects every v1
    contract in the current baseline because they are ``CONTRACT_ONLY``.
    """

    contract = get_runtime_skill(skill_id, version)
    if require_runtime_ready and not contract.is_runtime_ready:
        raise RuntimeSkillNotReadyError(
            f"Runtime skill is not ready for live inference: "
            f"{contract.skill_id}@{contract.version} status={contract.status}"
        )
    return contract


def list_runtime_skills() -> tuple[RuntimeSkillContract, ...]:
    """Return the registry in a stable order for diagnostics/tests."""

    return tuple(RUNTIME_SKILLS[key] for key in sorted(RUNTIME_SKILLS))
