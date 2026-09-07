"""Versioned runtime-model skill contracts for the drama remake pipeline.

The package is intentionally isolated from ``engine.app`` while all contracts are
``CONTRACT_ONLY``. Importing this package must never start model inference.
"""

from engine.skills.registry import (
    RUNTIME_SKILLS,
    RuntimeSkillContract,
    RuntimeSkillNotReadyError,
    UnknownRuntimeSkillError,
    get_runtime_skill,
    list_runtime_skills,
    validate_runtime_skill_ref,
)

__all__ = [
    "RUNTIME_SKILLS",
    "RuntimeSkillContract",
    "RuntimeSkillNotReadyError",
    "UnknownRuntimeSkillError",
    "get_runtime_skill",
    "list_runtime_skills",
    "validate_runtime_skill_ref",
]
