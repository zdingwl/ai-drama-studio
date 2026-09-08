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


VIDEO_PROJECT_TYPES = frozenset(
    {
        ProjectType.REPLICA,
        ProjectType.REDRAW,
        ProjectType.TRANSLATION,
    }
)
