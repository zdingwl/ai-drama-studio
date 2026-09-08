from fastapi import APIRouter

from app.core.errors import AppError
from app.skills.capabilities import CAPABILITIES
from app.skills.models import CapabilityDefinition, RootSkillDefinition, RootSkillDetail
from app.skills.registry import get_root_skill_by_id, get_skill_detail, list_root_skills

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[RootSkillDefinition])
def list_skills_route() -> list[RootSkillDefinition]:
    return list_root_skills()


@router.get("/capabilities", response_model=list[CapabilityDefinition])
def list_capabilities_route() -> list[CapabilityDefinition]:
    return list(CAPABILITIES)


@router.get("/{skill_id}", response_model=RootSkillDetail)
def get_skill_route(skill_id: str) -> RootSkillDetail:
    skill = get_root_skill_by_id(skill_id)
    if skill is None:
        raise AppError("SKILL_NOT_FOUND", "技能不存在", status_code=404, details={"skill_id": skill_id})
    return get_skill_detail(skill)
