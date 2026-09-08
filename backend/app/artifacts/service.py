from collections import deque

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.schemas import ArtifactGraphRead
from app.core.errors import AppError
from app.projects.models import Project
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.skills.plan_models import ProjectExecutionPlanRecord


_SOURCE_ARTIFACT_TYPES = {
    ArtifactType.SOURCE_VIDEO,
    ArtifactType.SOURCE_TEXT,
    ArtifactType.SHOT_ANCHORS,
    ArtifactType.SOURCE_DIALOGUE,
    ArtifactType.SOURCE_BIBLE,
    ArtifactType.STORY_SKELETON,
    ArtifactType.RHYTHM_SKELETON,
    ArtifactType.SOURCE_SHOT_FACTS,
    ArtifactType.SOURCE_CHARACTERS,
    ArtifactType.SOURCE_SCENES,
    ArtifactType.SOURCE_PROPS,
    ArtifactType.SOURCE_VIDEO_SNAPSHOT,
    ArtifactType.SOURCE_TEXT_SNAPSHOT,
}

_TARGET_ARTIFACT_TYPES = {
    ArtifactType.ADAPTATION_PLAN,
    ArtifactType.TARGET_BIBLE,
    ArtifactType.TARGET_SCRIPT,
    ArtifactType.TARGET_ASSETS,
}


def expected_namespace(artifact_type: ArtifactType) -> ArtifactNamespace:
    if artifact_type in _SOURCE_ARTIFACT_TYPES:
        return ArtifactNamespace.SOURCE
    if artifact_type in _TARGET_ARTIFACT_TYPES:
        return ArtifactNamespace.TARGET
    return ArtifactNamespace.PRODUCTION


def get_current_artifacts(db: Session, project_id: str) -> list[ArtifactNode]:
    statement = (
        select(ArtifactNode)
        .where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.is_current.is_(True),
            ArtifactNode.validity == ArtifactValidity.CURRENT,
        )
        .order_by(ArtifactNode.artifact_type.asc(), ArtifactNode.revision.asc())
    )
    return list(db.scalars(statement).all())


def get_current_artifact_types(db: Session, project_id: str) -> set[ArtifactType]:
    return {node.type_enum for node in get_current_artifacts(db, project_id)}


def list_artifacts(db: Session, project_id: str) -> list[ArtifactNode]:
    get_project(db, project_id)
    return list(
        db.scalars(
            select(ArtifactNode)
            .where(ArtifactNode.project_id == project_id)
            .order_by(ArtifactNode.created_at.asc(), ArtifactNode.revision.asc())
        ).all()
    )


def _invalidate_project_plan(db: Session, project: Project) -> None:
    if project.current_plan_id:
        plan = db.get(ProjectExecutionPlanRecord, project.current_plan_id)
        if plan is not None:
            plan.is_current = False
            db.add(plan)
    project.current_plan_id = None
    db.add(project)


def _mark_stale_with_downstream(db: Session, roots: list[ArtifactNode]) -> None:
    queue = deque(node.id for node in roots)
    seen: set[str] = set()
    while queue:
        node_id = queue.popleft()
        if node_id in seen:
            continue
        seen.add(node_id)
        node = db.get(ArtifactNode, node_id)
        if node is None:
            continue
        node.validity = ArtifactValidity.STALE
        node.is_current = False
        db.add(node)
        child_ids = db.scalars(
            select(ArtifactEdge.target_node_id).where(ArtifactEdge.source_node_id == node_id)
        ).all()
        queue.extend(child_ids)


def invalidate_current_artifact_type(
    db: Session,
    *,
    project_id: str,
    artifact_type: ArtifactType,
) -> None:
    project = get_project(db, project_id)
    current_nodes = list(
        db.scalars(
            select(ArtifactNode).where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == artifact_type.value,
                ArtifactNode.is_current.is_(True),
                ArtifactNode.validity == ArtifactValidity.CURRENT,
            )
        ).all()
    )
    if not current_nodes:
        return
    _mark_stale_with_downstream(db, current_nodes)
    _invalidate_project_plan(db, project)
    db.commit()


def create_artifact(
    db: Session,
    *,
    project_id: str,
    artifact_type: ArtifactType,
    namespace: ArtifactNamespace,
    label: str,
    input_fingerprint: str,
    skill_id: str,
    skill_version: str,
    metadata_json: dict | None = None,
) -> ArtifactNode:
    project = get_project(db, project_id)
    required_namespace = expected_namespace(artifact_type)
    if namespace != required_namespace:
        raise AppError(
            "ARTIFACT_NAMESPACE_MISMATCH",
            "Artifact 命名空间与类型不匹配",
            status_code=422,
            details={
                "artifact_type": artifact_type.value,
                "expected": required_namespace.value,
                "actual": namespace.value,
            },
        )
    if len(input_fingerprint) != 64:
        raise AppError("INVALID_ARTIFACT_FINGERPRINT", "Artifact fingerprint 必须是 64 位 SHA256", status_code=422)

    current_nodes = list(
        db.scalars(
            select(ArtifactNode).where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == artifact_type.value,
                ArtifactNode.is_current.is_(True),
            )
        ).all()
    )
    if current_nodes:
        _mark_stale_with_downstream(db, current_nodes)

    latest_revision = db.scalar(
        select(func.max(ArtifactNode.revision)).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
        )
    )
    node = ArtifactNode(
        project_id=project_id,
        artifact_type=artifact_type.value,
        namespace=namespace,
        label=label.strip(),
        revision=(latest_revision or 0) + 1,
        input_fingerprint=input_fingerprint,
        skill_id=skill_id,
        skill_version=skill_version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json=metadata_json or {},
    )
    db.add(node)
    _invalidate_project_plan(db, project)
    db.commit()
    db.refresh(node)
    return node


def create_artifact_relation(
    db: Session,
    *,
    project_id: str,
    source_node_id: str,
    target_node_id: str,
    relation_type: ArtifactRelationType,
) -> ArtifactEdge:
    get_project(db, project_id)
    source = db.get(ArtifactNode, source_node_id)
    target = db.get(ArtifactNode, target_node_id)
    if source is None or target is None:
        raise AppError(
            "ARTIFACT_NOT_FOUND",
            "ArtifactRelation 引用了不存在的 Artifact",
            status_code=422,
            details={"source_node_id": source_node_id, "target_node_id": target_node_id},
        )
    if source.project_id != project_id or target.project_id != project_id:
        raise AppError("CROSS_PROJECT_ARTIFACT_RELATION", "ArtifactRelation 不能跨项目", status_code=422)
    if source.id == target.id:
        raise AppError("SELF_ARTIFACT_RELATION", "Artifact 不能引用自己", status_code=422)
    if target.namespace == ArtifactNamespace.SOURCE and source.namespace != ArtifactNamespace.SOURCE:
        raise AppError("SOURCE_NAMESPACE_BACKFLOW", "Target/Production Artifact 不能反向写入 Source", status_code=422)
    if relation_type == ArtifactRelationType.CONTAINS and source.namespace != target.namespace:
        raise AppError("CONTAINS_NAMESPACE_MISMATCH", "CONTAINS 关系必须位于同一命名空间", status_code=422)
    if relation_type == ArtifactRelationType.SUPERSEDES:
        if source.namespace != target.namespace or source.artifact_type != target.artifact_type:
            raise AppError("INVALID_SUPERSEDES_RELATION", "SUPERSEDES 必须连接同类型同命名空间 Artifact", status_code=422)

    edge = ArtifactEdge(
        project_id=project_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relation_type=relation_type,
    )
    db.add(edge)
    db.commit()
    db.refresh(edge)
    return edge


def get_artifact_graph(db: Session, project_id: str) -> ArtifactGraphRead:
    get_project(db, project_id)
    nodes = tuple(list_artifacts(db, project_id))
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
