from enum import StrEnum


class ProjectType(StrEnum):
    REPLICA = "REPLICA"
    REDRAW = "REDRAW"
    TRANSLATION = "TRANSLATION"
    NOVEL_TO_DRAMA = "NOVEL_TO_DRAMA"
    SCRIPT_TO_DRAMA = "SCRIPT_TO_DRAMA"
    SCRIPT_LOCALIZATION = "SCRIPT_LOCALIZATION"


class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class SceneStrategy(StrEnum):
    KEEP = "KEEP"
    LOCALIZE = "LOCALIZE"
    MIXED = "MIXED"


class AudioPolicy(StrEnum):
    KEEP_SOURCE_AUDIO = "KEEP_SOURCE_AUDIO"
    REGENERATE_AUDIO = "REGENERATE_AUDIO"


class SourceUnderstandingProvider(StrEnum):
    # Cloud production option.
    DOUBAO_SEED_2_1_PRO_API = "DOUBAO_SEED_2_1_PRO_API"
    # Local high-quality option.
    QWEN3_8_27B_LOCAL = "QWEN3_8_27B_LOCAL"
    # Local lower-footprint compatibility option.
    QWEN3_VL_8B_THINKING_LOCAL = "QWEN3_VL_8B_THINKING_LOCAL"
    # Compatibility only for projects saved during the short-lived two-provider implementation.
    # It resolves to the same 8B model and is intentionally not exposed by the UI.
    QWEN3_VL_LOCAL = "QWEN3_VL_LOCAL"


VIDEO_PROJECT_TYPES = frozenset(
    {
        ProjectType.REPLICA,
        ProjectType.REDRAW,
        ProjectType.TRANSLATION,
    }
)

SOURCE_BIBLE_PROJECT_TYPES = frozenset(
    {
        ProjectType.REPLICA,
        ProjectType.REDRAW,
    }
)
