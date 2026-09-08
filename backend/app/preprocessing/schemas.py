from enum import StrEnum

from pydantic import BaseModel


class ShotBoundaryResultStatus(StrEnum):
    NOT_BUILT = "NOT_BUILT"
    CURRENT = "CURRENT"
    STALE = "STALE"


class ShotAnchorRead(BaseModel):
    id: str
    shot_number: int
    start_us: int
    end_us: int
    duration_us: int
    thumbnail_url: str
    reference_clip_url: str


class EpisodeShotBoundaryRead(BaseModel):
    episode_id: str
    episode_order: int
    source_filename: str
    status: ShotBoundaryResultStatus
    revision: int | None
    artifact_revision: int | None
    shot_count: int
    shots: list[ShotAnchorRead]
