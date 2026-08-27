"""Breakdown-first Phase P2.1 的统一 Evidence Provider / 本地 sidecar 基础层。

职责：
- 从一个 PROCESSING BreakdownRun 恢复其冻结的 ShotRevision 输入上下文；
- 为后续 ASR / OCR / VLM Adapter 提供统一、匿名、可测试的 Provider Contract；
- 把原始模型 Evidence 以不可变、可追溯 JSON sidecar 保存到 Episode workspace；
- 把组件状态和 artifact provenance 摘要写回当前 BreakdownRun；
- 在真正的 P2.5 Fusion 之前保留“原始 Evidence”和“结构化 Draft”两层数据。

输入：
- BreakdownRun.id；
- 该 Run 冻结的 ShotRevision / ShotRevisionItem / Reference Clip / keyframes；
- Episode preprocess audio；
- 实现 ``BreakdownP2Provider`` 的同步本地 Provider。

输出：
- ``P2RunContext``：模型只读输入快照；
- ``P2ProviderResult``：统一 Evidence 结果；
- ``P2EvidenceArtifact``：workspace 中按 fingerprint 固化的原始 Evidence sidecar。

明确不负责：
- P2.1 不执行具体 ASR/OCR/VLM 模型；具体 Provider 从 P2.2 起逐项接入；
- 不生成 SceneSegmentDraft / ShotSemanticDraft / LocalSubject / TimelineEvent；这些由后续 Fusion 阶段写入；
- 不创建 Character / Scene / Prop / AssetRevision，也不写任何 Final Shot Binding；
- 不把 VLM 文本当人物身份真值，不接触 Character V10.1 identity / Final Gate；
- 本模块只定义同步本地 Provider。未来若接外部异步/计费 Provider，必须另外遵守
  ``docs/PROVIDER_JOB_RULES.md``，不能把远端 Job 生命周期藏进本 Contract。

稳定依赖：
- P1 ``breakdown-draft-v1`` 数据 Contract；
- ``BreakdownRun.source_shot_revision_id`` 历史锚点；
- 正式时间单位统一为 integer microseconds。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol

from sqlalchemy import select

from engine.app import studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem

P2_SIDECAR_SCHEMA_VERSION = "breakdown-p2-evidence-v1"
P2_COMPONENTS = frozenset({"ASR", "OCR", "VLM"})
P2_PROVIDER_RESULT_STATUSES = frozenset({"READY", "NO_EVIDENCE", "NOT_CONFIGURED", "NOT_AVAILABLE", "FAILED"})
P2_EVIDENCE_SOURCE_TYPES = frozenset({
    "ASR_SEGMENT",
    "ASR_WORD",
    "OCR_OBSERVATION",
    "VLM_OUTPUT",
    "FRAME",
    "AUDIO_RANGE",
    "RULE",
})
P2_COMPONENT_SOURCE_TYPES = {
    "ASR": frozenset({"ASR_SEGMENT", "ASR_WORD", "AUDIO_RANGE", "RULE"}),
    "OCR": frozenset({"OCR_OBSERVATION", "FRAME", "RULE"}),
    "VLM": frozenset({"VLM_OUTPUT", "FRAME", "AUDIO_RANGE", "RULE"}),
}
FORBIDDEN_FINAL_ASSET_KEYS = frozenset({
    "character_id",
    "scene_id",
    "prop_id",
    "asset_revision_id",
    "speaker_character_id",
    "shot_character_binding_id",
    "shot_scene_binding_id",
    "shot_prop_binding_id",
})


class BreakdownP2SidecarError(RuntimeError):
    """P2 Evidence sidecar 输入、状态或 Contract 不合法。"""


@dataclass(frozen=True)
class P2ShotInput:
    """一个 Provider 可消费的历史 ShotRevisionItem 输入快照。

    ``original_shot_id`` 只保留分析时 Shot ID 快照；真正历史锚点始终是
    ``revision_item_id``。Provider 不允许反向 UPDATE Current ``v2_shots``。
    """

    revision_item_id: str
    original_shot_id: str
    ordinal: int
    start_us: int
    end_us: int
    duration_us: int
    reference_clip_path: str
    thumbnail_path: str | None
    keyframes: tuple[Any, ...]


@dataclass(frozen=True)
class P2RunContext:
    """一次 P2 Provider 调用看到的只读 Run/媒体上下文。"""

    run_id: str
    project_id: str
    episode_id: str
    source_language: str
    source_shot_revision_id: str
    audio_path: str | None
    shots: tuple[P2ShotInput, ...]


@dataclass(frozen=True)
class P2EvidenceRecord:
    """ASR/OCR/VLM 原始 Evidence 的统一最小结构。

    ``payload`` 保存 Provider 特有但仍属于原始证据的字段，例如 ASR token probability、
    OCR polygon、VLM structured JSON。它不能包含 Final Asset/Binding ID；P2 只认识匿名语义。
    ``shot_revision_item_id`` 可以为空，例如跨 Shot 的 ASR segment，后续 Fusion 再按时间切分。
    """

    source_type: str
    source_id: str
    source_start_us: int | None = None
    source_end_us: int | None = None
    shot_revision_item_id: str | None = None
    text: str | None = None
    language: str | None = None
    confidence: float | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class P2ProviderResult:
    """一个同步本地 Provider 的标准化完成结果。

    Provider 自己的 SDK/模型对象、状态名和临时字段必须在 Adapter 内消化；业务层只消费
    本结构。``FAILED`` 可以保存已明确失败的诊断 metadata，但不得包含 API key/secret。
    """

    component: str
    provider: str
    model: str
    status: str
    evidence: tuple[P2EvidenceRecord, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class P2EvidenceArtifact:
    """已固化到 workspace 的原始 Evidence artifact 描述。"""

    component: str
    fingerprint: str
    path: str
    uri: str
    evidence_count: int


class BreakdownP2Provider(Protocol):
    """P2 同步本地 Provider Adapter Contract。

    P2.2/P2.3/P2.4 的 ASR/OCR/VLM Adapter 都实现本接口。模型品牌和 SDK 不应渗透到
    Fusion/业务层。外部异步或计费 Provider 不得直接实现成“同步假象”，必须先建立
    ``PROVIDER_JOB_RULES`` 要求的持久化 Job 层。
    """

    component: str

    def analyze(self, context: P2RunContext) -> P2ProviderResult:
        """读取冻结媒体上下文并返回标准化原始 Evidence；不得写 Final Asset。"""
        ...


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _keyframes(raw: str | None) -> tuple[Any, ...]:
    if not raw:
        return ()
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    return tuple(value) if isinstance(value, list) else ()


def _assert_no_final_asset_keys(value: Any, *, path: str = "payload") -> None:
    """递归拒绝 Final Asset/Binding 业务 ID 泄漏进匿名 P2 原始 Evidence。"""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_FINAL_ASSET_KEYS:
                raise BreakdownP2SidecarError(f"匿名 P2 Evidence 禁止字段 {path}.{key}")
            _assert_no_final_asset_keys(nested, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _assert_no_final_asset_keys(nested, path=f"{path}[{index}]")


def _current_revision_for_episode(session: Any, episode_id: str) -> ShotRevision | None:
    return session.scalar(
        select(ShotRevision).where(
            ShotRevision.episode_id == episode_id,
            ShotRevision.is_current.is_(True),
        )
    )


def load_p2_run_context(run_id: str) -> P2RunContext:
    """恢复 PROCESSING BreakdownRun 的冻结 P2 媒体输入。

    副作用：无业务写入，也不会创建 BASELINE Revision。
    异常：Run 不存在、不是 PROCESSING、source revision 已失去 Current、Revision 无 Shot 时 fail closed。
    """

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")
        if run.status != "PROCESSING":
            raise BreakdownP2SidecarError(f"P2 Provider 只允许消费 PROCESSING Run，当前状态为 {run.status}")

        project = session.get(studio_v2.Project, run.project_id)
        episode = session.get(studio_v2.Episode, run.episode_id)
        revision = session.get(ShotRevision, run.source_shot_revision_id)
        if project is None or episode is None or revision is None:
            raise BreakdownP2SidecarError("Breakdown Run 的 Project/Episode/ShotRevision 历史锚点不完整")
        current_revision = _current_revision_for_episode(session, episode.id)
        if current_revision is None or current_revision.id != revision.id or not revision.is_current:
            raise BreakdownP2SidecarError("Run source ShotRevision 已不是 Episode Current，禁止继续 P2 推理")

        items = session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == revision.id)
            .order_by(ShotRevisionItem.ordinal)
        ).all()
        if not items:
            raise BreakdownP2SidecarError("Run source ShotRevision 没有 ShotRevisionItem")

        preprocess = session.scalar(
            select(studio_v2.Preprocess).where(studio_v2.Preprocess.episode_id == episode.id)
        )
        shots = tuple(
            P2ShotInput(
                revision_item_id=item.id,
                original_shot_id=item.original_shot_id,
                ordinal=item.ordinal,
                start_us=item.start_us,
                end_us=item.end_us,
                duration_us=item.duration_us,
                reference_clip_path=item.reference_clip_path,
                thumbnail_path=item.thumbnail_path,
                keyframes=_keyframes(item.keyframes_json),
            )
            for item in items
        )
        return P2RunContext(
            run_id=run.id,
            project_id=run.project_id,
            episode_id=run.episode_id,
            source_language=project.source_language,
            source_shot_revision_id=run.source_shot_revision_id,
            audio_path=preprocess.audio_path if preprocess else None,
            shots=shots,
        )


def _validate_record(context: P2RunContext, component: str, record: P2EvidenceRecord) -> None:
    source_type = record.source_type.strip().upper()
    if source_type not in P2_EVIDENCE_SOURCE_TYPES:
        raise BreakdownP2SidecarError(f"未知 P2 Evidence source_type: {record.source_type}")
    if source_type not in P2_COMPONENT_SOURCE_TYPES[component]:
        raise BreakdownP2SidecarError(f"{component} Provider 不允许产出 {source_type}")
    if not record.source_id.strip():
        raise BreakdownP2SidecarError("P2 Evidence source_id 不能为空")
    if (record.source_start_us is None) != (record.source_end_us is None):
        raise BreakdownP2SidecarError(f"Evidence {record.source_id} 的 source 时间必须成对出现")
    if record.source_start_us is not None and record.source_end_us is not None:
        if record.source_start_us < 0 or record.source_end_us <= record.source_start_us:
            raise BreakdownP2SidecarError(f"Evidence {record.source_id} 的 source 时间范围非法")
    if record.confidence is not None and not 0.0 <= record.confidence <= 1.0:
        raise BreakdownP2SidecarError(f"Evidence {record.source_id} confidence 必须在 0..1")

    shots_by_id = {shot.revision_item_id: shot for shot in context.shots}
    if record.shot_revision_item_id is not None:
        shot = shots_by_id.get(record.shot_revision_item_id)
        if shot is None:
            raise BreakdownP2SidecarError(
                f"Evidence {record.source_id} 引用了不属于 Run source revision 的 ShotRevisionItem"
            )
        if record.source_start_us is not None and record.source_end_us is not None:
            if record.source_start_us < shot.start_us or record.source_end_us > shot.end_us:
                raise BreakdownP2SidecarError(
                    f"Evidence {record.source_id} 已绑定 ShotRevisionItem，但时间越出该 Shot"
                )
    _assert_no_final_asset_keys(record.payload)


def validate_provider_result(context: P2RunContext, result: P2ProviderResult) -> None:
    """在写 sidecar 前校验统一 Provider Result；任何越界都 fail closed。"""

    component = result.component.strip().upper()
    if component not in P2_COMPONENTS:
        raise BreakdownP2SidecarError(f"未知 P2 component: {result.component}")
    if result.status not in P2_PROVIDER_RESULT_STATUSES:
        raise BreakdownP2SidecarError(f"未知 P2 Provider result status: {result.status}")
    if not result.provider.strip() or not result.model.strip():
        raise BreakdownP2SidecarError("P2 Provider result 必须记录 provider 和 model")
    if result.status == "READY" and not result.evidence:
        raise BreakdownP2SidecarError("READY Provider result 必须包含至少一条原始 Evidence")
    if result.status != "READY" and result.evidence:
        raise BreakdownP2SidecarError(f"{result.status} Provider result 不应携带可消费 Evidence")
    _assert_no_final_asset_keys(result.metadata, path="metadata")
    for record in result.evidence:
        _validate_record(context, component, record)


def _record_payload(record: P2EvidenceRecord) -> dict[str, Any]:
    return {
        "source_type": record.source_type.strip().upper(),
        "source_id": record.source_id,
        "source_start_us": record.source_start_us,
        "source_end_us": record.source_end_us,
        "shot_revision_item_id": record.shot_revision_item_id,
        "text": record.text,
        "language": record.language,
        "confidence": record.confidence,
        "payload": dict(record.payload),
    }


def _artifact_payload(context: P2RunContext, result: P2ProviderResult) -> dict[str, Any]:
    return {
        "schema_version": P2_SIDECAR_SCHEMA_VERSION,
        "run_id": context.run_id,
        "project_id": context.project_id,
        "episode_id": context.episode_id,
        "source_shot_revision_id": context.source_shot_revision_id,
        "component": result.component.strip().upper(),
        "provider": result.provider,
        "model": result.model,
        "status": result.status,
        "metadata": dict(result.metadata),
        "warnings": list(result.warnings),
        "evidence": [_record_payload(item) for item in result.evidence],
    }


def _stable_json(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise BreakdownP2SidecarError("P2 Provider result 必须可安全 JSON 序列化") from exc


def _assert_context_still_writable(context: P2RunContext) -> None:
    """Provider 完成后再次检查 Run/Revision，阻止长推理竞态把旧结果写成活动 Evidence。"""

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, context.run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")
        if run.status != "PROCESSING":
            raise BreakdownP2SidecarError(f"P2 Evidence 写入要求 PROCESSING Run，当前状态为 {run.status}")
        current_revision = _current_revision_for_episode(session, context.episode_id)
        if (
            run.source_shot_revision_id != context.source_shot_revision_id
            or current_revision is None
            or current_revision.id != context.source_shot_revision_id
        ):
            raise BreakdownP2SidecarError("Provider 执行期间 ShotRevision 已变化，拒绝写入旧 P2 Evidence")


def p2_evidence_root(context: P2RunContext) -> Path:
    """返回当前 Run 的原始 Evidence sidecar 根目录；目录仅在真正写 artifact 时创建。"""

    return studio_v2.episode_dir(context.project_id, context.episode_id) / "breakdown" / context.run_id / "evidence"


def persist_provider_result(context: P2RunContext, result: P2ProviderResult) -> P2EvidenceArtifact:
    """按内容 fingerprint 原子固化一个 Provider Result。

    同一 Run + 同一标准化结果会得到同一文件名，因此本地同步重试是幂等的；不同结果会
    新建 artifact，不覆盖历史 Evidence。文件先写 ``.tmp``，再 ``os.replace``，避免进程
    中断留下半个 JSON。该函数不创建 Final Asset，也不发布 Breakdown Run。
    """

    validate_provider_result(context, result)
    _assert_context_still_writable(context)
    payload = _artifact_payload(context, result)
    serialized = _stable_json(payload)
    fingerprint = sha256(serialized.encode("utf-8")).hexdigest()
    component = result.component.strip().upper()
    directory = p2_evidence_root(context) / component.lower()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{fingerprint}.json"

    if path.exists():
        if path.read_text(encoding="utf-8") != serialized:
            raise BreakdownP2SidecarError("P2 Evidence fingerprint 冲突，拒绝覆盖已有 artifact")
    else:
        temp = directory / f".{fingerprint}.tmp"
        temp.write_text(serialized, encoding="utf-8")
        os.replace(temp, path)

    return P2EvidenceArtifact(
        component=component,
        fingerprint=fingerprint,
        path=str(path),
        uri=path.resolve().as_uri(),
        evidence_count=len(result.evidence),
    )


def record_component_artifact(
    context: P2RunContext,
    result: P2ProviderResult,
    artifact: P2EvidenceArtifact,
) -> None:
    """把已固化 artifact 的非敏感 provenance 摘要合并进 PROCESSING BreakdownRun。

    原始 Evidence 仍以 artifact 为准；Run JSON 只用于快速查看组件状态，不复制完整模型输出。
    若 ShotRevision 在文件落盘后发生切换，本函数会拒绝更新活动 Run；孤立 artifact 可保留
    作为诊断文件，但不会进入 Current Draft/Final Asset。
    """

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, context.run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")
        current_revision = _current_revision_for_episode(session, context.episode_id)
        if (
            run.status != "PROCESSING"
            or run.source_shot_revision_id != context.source_shot_revision_id
            or current_revision is None
            or current_revision.id != context.source_shot_revision_id
        ):
            raise BreakdownP2SidecarError("P2 component 状态写入时 Run/ShotRevision 已不可写")

        component = result.component.strip().upper()
        statuses = _json_object(run.component_status_json)
        statuses[component] = {
            "status": result.status,
            "provider": result.provider,
            "model": result.model,
            "artifact_uri": artifact.uri,
            "fingerprint": artifact.fingerprint,
            "evidence_count": artifact.evidence_count,
            "warnings": list(result.warnings),
        }
        providers = _json_object(run.provider_metadata_json)
        p2_meta = providers.get("p2_sidecar")
        if not isinstance(p2_meta, dict):
            p2_meta = {}
        p2_meta[component] = {
            "provider": result.provider,
            "model": result.model,
            "metadata": dict(result.metadata),
        }
        providers["p2_sidecar"] = p2_meta
        run.component_status_json = _stable_json(statuses)
        run.provider_metadata_json = _stable_json(providers)
        session.commit()


def run_local_provider(run_id: str, provider: BreakdownP2Provider) -> P2EvidenceArtifact:
    """执行一个同步本地 P2 Provider，并固化/登记原始 Evidence。

    P2.2+ 可以用它接 faster-whisper、OCR、本地 VLM。这里不捕获 Provider 推理异常，
    因为 P2.5 orchestration 才负责组件级失败策略和最终 ``fail_breakdown_run`` / publish。
    """

    context = load_p2_run_context(run_id)
    expected_component = str(provider.component).strip().upper()
    if expected_component not in P2_COMPONENTS:
        raise BreakdownP2SidecarError(f"Provider 声明了未知 component: {provider.component}")
    result = provider.analyze(context)
    if result.component.strip().upper() != expected_component:
        raise BreakdownP2SidecarError("Provider.component 与 ProviderResult.component 不一致")
    artifact = persist_provider_result(context, result)
    record_component_artifact(context, result, artifact)
    return artifact
