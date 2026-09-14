from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.skills.professional import ProfessionalSkillDetail, get_professional_skill_detail


@dataclass(frozen=True)
class VideoModelPromptSkillBinding:
    model_id: str
    prompt_skill_id: str
    prompt_contract: str


_H3_BINDING = VideoModelPromptSkillBinding(
    model_id="MiniMaxAI/MiniMax-H3",
    prompt_skill_id="minimax-h3-prompting",
    prompt_contract="minimax-h3-multi-reference-av-v1",
)


VIDEO_MODEL_PROMPT_SKILLS: dict[str, VideoModelPromptSkillBinding] = {
    "MiniMaxAI/MiniMax-H3": _H3_BINDING,
    "MiniMax-H3": _H3_BINDING,
    "MiniMax-H3-Max": _H3_BINDING,
}


def selected_video_model_id(settings: Settings | None = None) -> str:
    effective = settings or get_settings()
    if effective.p16_h3_runtime in {"LOCAL_COMFYUI", "LOCAL_SGLANG"}:
        return effective.p16_h3_local_model.strip()
    return effective.p16_minimax_model.strip()


def resolve_video_model_prompt_skill(model_id: str) -> tuple[VideoModelPromptSkillBinding, ProfessionalSkillDetail]:
    normalized = model_id.strip()
    binding = VIDEO_MODEL_PROMPT_SKILLS.get(normalized)
    if binding is None:
        raise AppError(
            "VIDEO_MODEL_PROMPT_SKILL_NOT_FOUND",
            "当前视频模型没有注册对应的 Prompt Professional Skill，禁止使用通用提示词代替",
            status_code=409,
            details={"model_id": normalized},
        )
    skill = get_professional_skill_detail(binding.prompt_skill_id)
    return binding, skill


def selected_video_model_prompt_skill(settings: Settings | None = None) -> tuple[VideoModelPromptSkillBinding, ProfessionalSkillDetail]:
    return resolve_video_model_prompt_skill(selected_video_model_id(settings))
