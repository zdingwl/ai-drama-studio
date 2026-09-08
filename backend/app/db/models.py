"""Import all SQLAlchemy models so Base.metadata is complete."""

from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.projects.models import Project

__all__ = ["ArtifactEdge", "ArtifactNode", "Project"]
