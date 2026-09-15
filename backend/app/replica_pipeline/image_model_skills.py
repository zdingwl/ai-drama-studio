from dataclasses import dataclass

from app.core.errors import AppError
from app.skills.professional import ProfessionalSkillDetail, get_professional_skill_detail


@dataclass(frozen=True)
class ImageModelPromptSkillBinding:
    model_id: str
    prompt_skill_id: str
    prompt_contract: str


_Z_IMAGE_TURBO_BINDING = ImageModelPromptSkillBinding(
    model_id="Z-Image-Turbo",
    prompt_skill_id="z-image-turbo-asset-prompting",
    prompt_contract="z-image-turbo-replica-assets-v1",
)


IMAGE_MODEL_PROMPT_SKILLS: dict[str, ImageModelPromptSkillBinding] = {
    "Z-Image-Turbo": _Z_IMAGE_TURBO_BINDING,
    "z_image_turbo_bf16.safetensors": _Z_IMAGE_TURBO_BINDING,
}


def resolve_image_model_prompt_skill(
    model_id: str,
) -> tuple[ImageModelPromptSkillBinding, ProfessionalSkillDetail]:
    normalized = model_id.strip()
    binding = IMAGE_MODEL_PROMPT_SKILLS.get(normalized)
    if binding is None:
        raise AppError(
            "IMAGE_MODEL_PROMPT_SKILL_NOT_FOUND",
            "当前图片模型没有注册对应的 Prompt Professional Skill，禁止使用通用字符串拼接器代替",
            status_code=409,
            details={"model_id": normalized},
        )
    return binding, get_professional_skill_detail(binding.prompt_skill_id)


def selected_image_model_prompt_skill() -> tuple[ImageModelPromptSkillBinding, ProfessionalSkillDetail]:
    return resolve_image_model_prompt_skill("Z-Image-Turbo")
