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
    prompt_contract="replica-assets-zimage-front-qwen-edit-v4",
)

_QWEN_IMAGE_EDIT_CHARACTER_BINDING = ImageModelPromptSkillBinding(
    model_id="Qwen-Image-Edit-2511",
    prompt_skill_id="qwen-image-edit-character-asset-prompting",
    prompt_contract="qwen-image-edit-2511-character-orientation-v1",
)


IMAGE_MODEL_PROMPT_SKILLS: dict[str, ImageModelPromptSkillBinding] = {
    "Z-Image-Turbo": _Z_IMAGE_TURBO_BINDING,
    "z_image_turbo_bf16.safetensors": _Z_IMAGE_TURBO_BINDING,
    "Qwen-Image-Edit-2511": _QWEN_IMAGE_EDIT_CHARACTER_BINDING,
    "qwen_image_edit_2511_fp8mixed.safetensors": _QWEN_IMAGE_EDIT_CHARACTER_BINDING,
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
    try:
        skill = get_professional_skill_detail(binding.prompt_skill_id)
    except RuntimeError as exc:
        raise AppError(
            "IMAGE_MODEL_PROMPT_SKILL_NOT_LOADED",
            "图片模型已绑定 Professional Skill，但该 Skill 未安装或尚未加载",
            status_code=500,
            details={"model_id": normalized, "prompt_skill_id": binding.prompt_skill_id},
        ) from exc
    return binding, skill


def selected_image_model_prompt_skill() -> tuple[ImageModelPromptSkillBinding, ProfessionalSkillDetail]:
    return resolve_image_model_prompt_skill("Z-Image-Turbo")


def selected_character_edit_prompt_skill() -> tuple[ImageModelPromptSkillBinding, ProfessionalSkillDetail]:
    return resolve_image_model_prompt_skill("Qwen-Image-Edit-2511")
