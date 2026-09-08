from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.schemas import ArtifactGraphRead
from app.projects.service import get_project
from app.skills.models import ArtifactType


def get_current_artifact_types(db: Session, project_id: str) -> set[ArtifactType]:
    statement = select(ArtifactNode.artifact_type).where(
        ArtifactNode.project_id == project_id,
        ArtifactNode.is_current.is_(True),
    )
    values = db.scalars(statement).all()
    return {ArtifactType(value) for value in values}


def get_artifact_graph(db: Session, project_id: str) -> ArtifactGraphRead:
    get_project(db, project_id)
    nodes = tuple(
        db.scalars(
            select(ArtifactNode)
            .where(ArtifactNode.project_id == project_id)
            .order_by(ArtifactNode.created_at.asc())
        ).all()
    )
    edges = tuple(
        db.scalars(
            select(ArtifactEdge)
            .where(ArtifactEdge.project_id == project_id)
            .order_by(ArtifactEdge.created_at.asc())
        ).all()
    )
    current_types = tuple(sorted(get_current_artifact_types(db, project_id), key=lambda item: item.value))
    return ArtifactGraphRead(
        project_id=project_id,
        available_artifact_types=current_types,
        nodes=nodes,
        edges=edges,
    )
