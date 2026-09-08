from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.skills.models import ArtifactType


class ArtifactNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    artifact_type: str
    label: str
    revision: int
    is_current: bool
    metadata_json: dict
    created_at: datetime


class ArtifactEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    source_node_id: str
    target_node_id: str
    relation_type: str
    created_at: datetime


class ArtifactGraphRead(BaseModel):
    project_id: str
    available_artifact_types: tuple[ArtifactType, ...]
    nodes: tuple[ArtifactNodeRead, ...]
    edges: tuple[ArtifactEdgeRead, ...]
