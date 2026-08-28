"""Breakdown-first Phase P2.5：ASR/OCR/VLM raw Evidence → 完整 P1 匿名 Draft Fusion。

职责：
- 只消费一个 PROCESSING BreakdownRun 已登记并固化的 P2 immutable sidecars；
- 验证 sidecar fingerprint/schema/component/run/source ShotRevision，禁止隐式重跑模型；
- 把跨 Shot ASR segment 按 exact ShotRevisionItem source-time 边界拆分；
- 在 Fusion 层对 OCR frame observations 做保守 temporal stitching / dedupe；
- 把 P2.4 VLM Shot-level anonymous semantics 映射到 P1 Draft graph；
- 一次事务写 SceneSegmentDraft / ShotSemanticDraft / LocalSubject / TimelineEvent /
  DraftPropHint / BreakdownEvidenceLink；
- 交给真实 P1 validator + publish gate 发布 READY / READY_WITH_WARNINGS。

明确不负责：
- 不运行 ASR/OCR/VLM；
- 不把 VLM subject_* 当 Character；
- 不创建 Character / Scene / Prop / AssetRevision；
- 不写任何 Final Shot Binding；
- 不修改 Character V10.1 identity/cannot-link/Face conflict/explicit assignment/Final Gate。

P2.5 是 deterministic fusion，不是第二个语言模型推理阶段。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from sqlalchemy import select

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_service_v1, studio_v2
from engine.app.breakdown_models_v1 import (
    BreakdownEvidenceLink,
    BreakdownRun,
    DraftPropHint,
    DraftPropOccurrence,
    LocalSubject,
    SceneSegmentDraft,
    ShotLocalSubject,
    ShotSemanticDraft,
    TimelineEvent,
    TimelineEventSubject,
)
from engine.app.shot_revision_v2 import ShotRevision

FUSION_PROFILE = "breakdown-p2-fusion-v1"
FUSION_VERSION = "1"
_REQUIRED_COMPONENTS = ("ASR", "OCR", "VLM")
_ALLOWED_DEGRADED_STATUSES = {"NO_EVIDENCE", "NOT_AVAILABLE"}
_OCR_DEFAULT_SAMPLE_INTERVAL_US = 500_000
_OCR_MIN_GEOMETRY_IOU = 0.20
_OCR_MAX_CENTER_DISTANCE = 0.20


class BreakdownP2FusionError(RuntimeError):
    """P2.5 sidecar / fusion Contract 违反或无法安全生成完整匿名 Draft。"""


@dataclass(frozen=True)
class LoadedComponent:
    component: str
    artifact_uri: str
    fingerprint: str
    result: p2.P2ProviderResult


@dataclass(frozen=True)
class FusionInputBundle:
    context: p2.P2RunContext
    components: Mapping[str, LoadedComponent]
    warnings: tuple[dict[str, Any], ...]


@dataclass
class _SegmentPlan:
    index: int
    shots: list[p2.P2ShotInput] = field(default_factory=list)
    semantics: list[Mapping[str, Any] | None] = field(default_factory=list)


@dataclass
class _SubjectPlan:
    key: str
    ordinal: int
    display_label: str
    appearance_summary: str | None
    source_labels: set[str] = field(default_factory=set)
    first_seen_us: int | None = None
    last_seen_us: int | None = None
    speaking_states: list[str] = field(default_factory=list)


@dataclass
class _PropPlan:
    normalized_label: str
    label: str
    importance: str
    reasons: list[str] = field(default_factory=list)
    first_seen_us: int | None = None
    last_seen_us: int | None = None
    source_ids: list[str] = field(default_factory=list)


@dataclass
class _OCRCluster:
    text: str
    normalized_text: str
    shot: p2.P2ShotInput
    records: list[p2.P2EvidenceRecord] = field(default_factory=list)
    bbox_norm: tuple[float, float, float, float] | None = None


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _clean_text(value: Any, *, max_len: int = 2000) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text[:max_len] if text else None


def _normalized_text(value: Any) -> str:
    text = _clean_text(value, max_len=2000) or ""
    return "".join(text.lower().split())


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _mean_confidence(records: Iterable[p2.P2EvidenceRecord]) -> float | None:
    values = [float(item.confidence) for item in records if item.confidence is not None]
    if not values:
        return None
    return min(1.0, max(0.0, sum(values) / len(values)))


def _file_path_from_uri(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise BreakdownP2FusionError("P2.5 当前只允许消费本地 file:// Evidence artifact")
    raw_path = url2pathname(unquote(parsed.path))
    if parsed.netloc and parsed.netloc not in {"", "localhost"}:
        raw_path = f"//{parsed.netloc}{raw_path}"
    return Path(raw_path)


def _evidence_from_payload(value: Mapping[str, Any]) -> p2.P2EvidenceRecord:
    payload = value.get("payload")
    return p2.P2EvidenceRecord(
        source_type=str(value.get("source_type") or ""),
        source_id=str(value.get("source_id") or ""),
        source_start_us=value.get("source_start_us"),
        source_end_us=value.get("source_end_us"),
        shot_revision_item_id=value.get("shot_revision_item_id"),
        text=value.get("text"),
        language=value.get("language"),
        confidence=value.get("confidence"),
        payload=payload if isinstance(payload, Mapping) else {},
    )


def _load_one_component(
    context: p2.P2RunContext,
    status_entry: Mapping[str, Any],
    component: str,
) -> LoadedComponent:
    artifact_uri = str(status_entry.get("artifact_uri") or "").strip()
    fingerprint = str(status_entry.get("fingerprint") or "").strip().lower()
    if not artifact_uri or len(fingerprint) != 64:
        raise BreakdownP2FusionError(f"{component} component provenance 缺少 artifact_uri/fingerprint")

    path = _file_path_from_uri(artifact_uri)
    if not path.is_file():
        raise BreakdownP2FusionError(f"{component} Evidence artifact 不存在")
    try:
        serialized = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BreakdownP2FusionError(f"{component} Evidence artifact 无法读取") from exc
    actual_fingerprint = sha256(serialized.encode("utf-8")).hexdigest()
    if actual_fingerprint != fingerprint:
        raise BreakdownP2FusionError(f"{component} Evidence artifact fingerprint 不匹配")

    try:
        payload = json.loads(serialized)
    except (TypeError, ValueError) as exc:
        raise BreakdownP2FusionError(f"{component} Evidence artifact JSON 无效") from exc
    if not isinstance(payload, Mapping):
        raise BreakdownP2FusionError(f"{component} Evidence artifact 顶层必须是 JSON object")

    if payload.get("schema_version") != p2.P2_SIDECAR_SCHEMA_VERSION:
        raise BreakdownP2FusionError(f"{component} Evidence sidecar schema 不匹配")
    expected = {
        "run_id": context.run_id,
        "project_id": context.project_id,
        "episode_id": context.episode_id,
        "source_shot_revision_id": context.source_shot_revision_id,
        "component": component,
    }
    for key, value in expected.items():
        if str(payload.get(key) or "") != value:
            raise BreakdownP2FusionError(f"{component} Evidence artifact {key} 与当前 Run 不一致")

    raw_evidence = payload.get("evidence")
    if not isinstance(raw_evidence, list):
        raise BreakdownP2FusionError(f"{component} Evidence artifact evidence 必须是数组")
    evidence = tuple(_evidence_from_payload(item) for item in raw_evidence if isinstance(item, Mapping))
    metadata = payload.get("metadata")
    warnings = payload.get("warnings")
    result = p2.P2ProviderResult(
        component=component,
        provider=str(payload.get("provider") or ""),
        model=str(payload.get("model") or ""),
        status=str(payload.get("status") or ""),
        evidence=evidence,
        metadata=metadata if isinstance(metadata, Mapping) else {},
        warnings=tuple(str(item) for item in warnings) if isinstance(warnings, list) else (),
    )
    p2.validate_provider_result(context, result)

    if str(status_entry.get("status") or "") != result.status:
        raise BreakdownP2FusionError(f"{component} component status 与 sidecar 不一致")
    if str(status_entry.get("provider") or "") != result.provider:
        raise BreakdownP2FusionError(f"{component} component provider 与 sidecar 不一致")
    if str(status_entry.get("model") or "") != result.model:
        raise BreakdownP2FusionError(f"{component} component model 与 sidecar 不一致")
    try:
        recorded_count = int(status_entry.get("evidence_count"))
    except (TypeError, ValueError):
        recorded_count = -1
    if recorded_count != len(result.evidence):
        raise BreakdownP2FusionError(f"{component} component evidence_count 与 sidecar 不一致")

    return LoadedComponent(
        component=component,
        artifact_uri=artifact_uri,
        fingerprint=fingerprint,
        result=result,
    )


def load_fusion_inputs(run_id: str) -> FusionInputBundle:
    """读取且验证 P2.1–P2.4 已登记 immutable sidecars；绝不隐式运行 Provider。"""

    context = p2.load_p2_run_context(run_id)
    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")
        statuses = _json_object(run.component_status_json)

    components: dict[str, LoadedComponent] = {}
    warnings: list[dict[str, Any]] = []
    for component in _REQUIRED_COMPONENTS:
        entry = statuses.get(component)
        if not isinstance(entry, Mapping):
            raise BreakdownP2FusionError(f"P2.5 要求 {component} Provider 已执行并登记 sidecar")
        loaded = _load_one_component(context, entry, component)
        components[component] = loaded
        status = loaded.result.status
        if status == "FAILED":
            raise BreakdownP2FusionError(f"{component} Provider 已失败，禁止 Fusion 发布不完整 Draft")
        if status == "NOT_CONFIGURED":
            raise BreakdownP2FusionError(f"{component} Provider 未配置，禁止 Fusion")
        if status in _ALLOWED_DEGRADED_STATUSES:
            warnings.append({
                "code": f"{component}_DEGRADED_{status}",
                "message": f"{component} Provider status={status}; Draft 将缺少该模态的可消费 Evidence",
            })

    if components["VLM"].result.status != "READY":
        raise BreakdownP2FusionError("P2.5 需要 READY VLM Shot semantics 才能生成完整 ShotSemanticDraft")

    return FusionInputBundle(
        context=context,
        components=components,
        warnings=tuple(warnings),
    )


def _semantic(record: p2.P2EvidenceRecord | None) -> Mapping[str, Any] | None:
    if record is None or not isinstance(record.payload, Mapping):
        return None
    value = record.payload.get("semantic")
    return value if isinstance(value, Mapping) else None


def _scene_signature(semantic: Mapping[str, Any] | None) -> tuple[str, str, str] | None:
    if not semantic:
        return None
    scene = semantic.get("scene")
    if not isinstance(scene, Mapping):
        return None
    location = _normalized_text(scene.get("location_hint"))
    if not location:
        return None
    interior = str(scene.get("interior_exterior") or "UNKNOWN").strip().upper()
    time_of_day = _normalized_text(scene.get("time_of_day"))
    return location, interior, time_of_day


def _segment_plans(
    shots: Sequence[p2.P2ShotInput],
    vlm_by_shot: Mapping[str, p2.P2EvidenceRecord],
) -> list[_SegmentPlan]:
    plans: list[_SegmentPlan] = []
    current: _SegmentPlan | None = None
    current_signature: tuple[str, str, str] | None = None
    for shot in shots:
        semantic = _semantic(vlm_by_shot.get(shot.revision_item_id))
        signature = _scene_signature(semantic)
        if current is None or signature is None or current_signature is None or signature != current_signature:
            current = _SegmentPlan(index=len(plans) + 1)
            plans.append(current)
            current_signature = signature
        current.shots.append(shot)
        current.semantics.append(semantic)
    return plans


def _map_interior_exterior(value: Any) -> str:
    normalized = str(value or "UNKNOWN").strip().upper()
    return {
        "INT": "INTERIOR",
        "EXT": "EXTERIOR",
        "INTERIOR": "INTERIOR",
        "EXTERIOR": "EXTERIOR",
        "MIXED": "MIXED",
    }.get(normalized, "UNKNOWN")


def _map_time_of_day(value: Any) -> str:
    normalized = _normalized_text(value)
    if normalized in {"day", "daytime", "白天", "日间", "上午", "下午"}:
        return "DAY"
    if normalized in {"night", "nighttime", "夜", "夜晚", "晚上", "深夜"}:
        return "NIGHT"
    if normalized in {"dawn", "黎明", "清晨"}:
        return "DAWN"
    if normalized in {"dusk", "黄昏", "傍晚"}:
        return "DUSK"
    return "UNKNOWN"


def _map_visibility(value: Any) -> str:
    normalized = str(value or "UNKNOWN").strip().upper()
    return normalized if normalized in {"FULL", "PARTIAL", "OCCLUDED", "BACK_VIEW", "UNKNOWN"} else "UNKNOWN"


def _map_speaking_state(value: Any) -> str:
    normalized = str(value or "UNKNOWN").strip().upper()
    if normalized in {"LIKELY_SPEAKING", "POSSIBLE", "SPEAKING"}:
        return "POSSIBLE"
    if normalized == "NOT_SPEAKING":
        return "NOT_SPEAKING"
    return "UNKNOWN"


def _map_screen_position(value: Any) -> str:
    normalized = _normalized_text(value)
    if not normalized:
        return "UNKNOWN"
    hits: list[str] = []
    if any(token in normalized for token in ("left", "左")):
        hits.append("LEFT")
    if any(token in normalized for token in ("center", "centre", "middle", "中间", "中央", "中心")):
        hits.append("CENTER")
    if any(token in normalized for token in ("right", "右")):
        hits.append("RIGHT")
    if len(set(hits)) > 1:
        return "MIXED"
    return hits[0] if hits else "UNKNOWN"


def _subject_display_label(ordinal: int) -> str:
    value = max(1, int(ordinal))
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return f"人物{letters}"


def _appearance_key(
    subject: Mapping[str, Any],
    shot: p2.P2ShotInput,
    label: str,
    ambiguous_appearances: set[str] | None = None,
) -> str:
    appearance = _normalized_text(subject.get("appearance_summary"))
    if len(appearance) >= 4 and appearance not in (ambiguous_appearances or set()):
        return f"appearance:{appearance}"
    # VLM label 只在单 Shot 内有效。没有足够外观文本，或同一外观在同镜头出现多人时，
    # 都必须退回 Shot-local key，防止语义 Draft 制造伪身份合并。
    return f"shot:{shot.revision_item_id}:{label}"


def _ambiguous_subject_appearances(segment_plan: _SegmentPlan) -> set[str]:
    """返回本 Segment 内不能用于跨 Shot 合并的外观签名。

    只要某个 normalized appearance 在任一 Shot 同时出现两次以上，就说明仅靠这段
    appearance_summary 无法区分当时的两个人。此时整个 Segment 都禁用该 appearance
    的跨 Shot 合并；宁可多建匿名 LocalSubject，也不能把同镜头两个人合成一个人。
    """

    ambiguous: set[str] = set()
    for semantic in segment_plan.semantics:
        if not isinstance(semantic, Mapping):
            continue
        raw_subjects = semantic.get("subjects")
        if not isinstance(raw_subjects, list):
            continue
        counts: dict[str, int] = {}
        for raw_subject in raw_subjects:
            if not isinstance(raw_subject, Mapping):
                continue
            appearance = _normalized_text(raw_subject.get("appearance_summary"))
            if len(appearance) < 4:
                continue
            counts[appearance] = counts.get(appearance, 0) + 1
        ambiguous.update(appearance for appearance, count in counts.items() if count > 1)
    return ambiguous


def _speaking_summary(states: Sequence[str]) -> str:
    meaningful = {item for item in states if item != "UNKNOWN"}
    if not meaningful:
        return "UNKNOWN"
    if meaningful == {"NOT_SPEAKING"}:
        return "NOT_SPEAKING"
    if meaningful == {"POSSIBLE"}:
        return "POSSIBLE"
    return "MIXED"


def _ratio_range(shot: p2.P2ShotInput, start_ratio: Any, end_ratio: Any) -> tuple[int, int]:
    start = _finite_float(start_ratio)
    end = _finite_float(end_ratio)
    if start is None:
        start = 0.0
    if end is None:
        end = 1.0
    start = min(1.0, max(0.0, start))
    end = min(1.0, max(0.0, end))
    if end < start:
        start, end = end, start
    duration = max(1, shot.end_us - shot.start_us)
    source_start = shot.start_us + int(round(duration * start))
    source_end = shot.start_us + int(round(duration * end))
    source_start = max(shot.start_us, min(shot.end_us - 1, source_start))
    source_end = max(source_start + 1, min(shot.end_us, source_end))
    return source_start, source_end


def _bbox_norm(record: p2.P2EvidenceRecord) -> tuple[float, float, float, float] | None:
    payload = record.payload if isinstance(record.payload, Mapping) else {}
    bbox = payload.get("bbox_px")
    width = _finite_float(payload.get("image_width"))
    height = _finite_float(payload.get("image_height"))
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4 or not width or not height or width <= 0 or height <= 0:
        return None
    values = [_finite_float(item) for item in bbox[:4]]
    if any(item is None for item in values):
        return None
    x1, y1, x2, y2 = (float(item) for item in values)
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return (
        min(1.0, max(0.0, x1 / width)),
        min(1.0, max(0.0, y1 / height)),
        min(1.0, max(0.0, x2 / width)),
        min(1.0, max(0.0, y2 / height)),
    )


def _bbox_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - intersection
    return intersection / union if union > 0 else 0.0


def _bbox_center_distance(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay = (a[0] + a[2]) / 2.0, (a[1] + a[3]) / 2.0
    bx, by = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def _geometry_compatible(a: tuple[float, float, float, float] | None, b: tuple[float, float, float, float] | None) -> bool:
    if a is None or b is None:
        return True
    return _bbox_iou(a, b) >= _OCR_MIN_GEOMETRY_IOU or _bbox_center_distance(a, b) <= _OCR_MAX_CENTER_DISTANCE


def _ocr_clusters(
    records: Sequence[p2.P2EvidenceRecord],
    shots_by_id: Mapping[str, p2.P2ShotInput],
    *,
    sample_interval_us: int,
) -> tuple[list[_OCRCluster], list[dict[str, Any]]]:
    clusters: list[_OCRCluster] = []
    warnings: list[dict[str, Any]] = []
    max_gap = max(1, int(sample_interval_us) * 2)
    by_shot: dict[str, list[p2.P2EvidenceRecord]] = {}
    for record in records:
        shot_id = record.shot_revision_item_id
        if not shot_id or shot_id not in shots_by_id:
            warnings.append({"code": "OCR_UNBOUND_OBSERVATION", "message": f"OCR Evidence {record.source_id} 没有合法 ShotRevisionItem，已忽略"})
            continue
        if not _normalized_text(record.text):
            continue
        by_shot.setdefault(shot_id, []).append(record)

    for shot_id, shot_records in by_shot.items():
        shot = shots_by_id[shot_id]
        active_by_text: dict[str, list[_OCRCluster]] = {}
        for record in sorted(shot_records, key=lambda item: (item.source_start_us or 0, item.source_id)):
            normalized = _normalized_text(record.text)
            bbox = _bbox_norm(record)
            candidates = active_by_text.setdefault(normalized, [])
            chosen: _OCRCluster | None = None
            for candidate in reversed(candidates):
                last = candidate.records[-1]
                if record.source_start_us is None or last.source_start_us is None:
                    continue
                if record.source_start_us - last.source_start_us > max_gap:
                    continue
                if _geometry_compatible(candidate.bbox_norm, bbox):
                    chosen = candidate
                    break
            if chosen is None:
                chosen = _OCRCluster(
                    text=_clean_text(record.text, max_len=2000) or "",
                    normalized_text=normalized,
                    shot=shot,
                    bbox_norm=bbox,
                )
                candidates.append(chosen)
                clusters.append(chosen)
            chosen.records.append(record)
            if chosen.bbox_norm is None and bbox is not None:
                chosen.bbox_norm = bbox
    return clusters, warnings


def _importance(value: Any) -> str:
    return {
        "HIGH": "KEY",
        "MEDIUM": "SUPPORTING",
        "LOW": "AMBIENT",
        "KEY": "KEY",
        "SUPPORTING": "SUPPORTING",
        "AMBIENT": "AMBIENT",
    }.get(str(value or "").strip().upper(), "UNKNOWN")


def _unique_join(values: Iterable[str | None], *, max_len: int = 2000, separator: str = "；") -> str | None:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        text = _clean_text(value, max_len=max_len)
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    joined = separator.join(items)
    return joined[:max_len] if joined else None


def _component_records(bundle: FusionInputBundle, component: str, source_type: str) -> list[p2.P2EvidenceRecord]:
    return [
        item for item in bundle.components[component].result.evidence
        if item.source_type.strip().upper() == source_type
    ]


def _safe_fail_run(run_id: str, exc: BaseException) -> None:
    try:
        with studio_v2.get_session() as session:
            run = session.get(BreakdownRun, run_id)
            should_fail = run is not None and run.status == "PROCESSING"
        if should_fail:
            breakdown_service_v1.fail_breakdown_run(
                run_id,
                f"P2.5 Fusion failed: {type(exc).__name__}",
            )
    except Exception:
        # 原异常更重要；STALE/并发状态变化时不覆盖其生命周期事实。
        return


def _assert_empty_processing_run(session: Any, run: BreakdownRun) -> None:
    if run.status != "PROCESSING":
        raise BreakdownP2FusionError(f"P2.5 只允许写 PROCESSING Run，当前状态为 {run.status}")
    current_revision = session.scalar(
        select(ShotRevision).where(
            ShotRevision.episode_id == run.episode_id,
            ShotRevision.is_current.is_(True),
        )
    )
    if current_revision is None or current_revision.id != run.source_shot_revision_id:
        raise BreakdownP2FusionError("P2.5 写 Draft 前 source ShotRevision 已不是 Current")
    existing = session.scalar(
        select(ShotSemanticDraft.id).where(ShotSemanticDraft.run_id == run.id).limit(1)
    )
    if existing is not None:
        raise BreakdownP2FusionError("PROCESSING Run 已存在 ShotSemanticDraft，拒绝重复/覆盖 P2.5 Draft")


def _add_link(
    session: Any,
    dedupe: set[tuple[str, str, str, str | None, str]],
    *,
    run_id: str,
    owner_type: str,
    owner_id: str,
    record: p2.P2EvidenceRecord,
    source_uri: str,
    role: str,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    key = (owner_type, owner_id, record.source_type, record.source_id, role)
    if key in dedupe:
        return
    dedupe.add(key)
    session.add(BreakdownEvidenceLink(
        id=studio_v2.new_id("EVIDENCE"),
        run_id=run_id,
        owner_type=owner_type,
        owner_id=owner_id,
        source_type=record.source_type,
        source_id=record.source_id,
        source_uri=source_uri,
        role=role,
        confidence=record.confidence,
        metadata_json=_json_text(dict(metadata or {})),
    ))


def _write_fused_draft(bundle: FusionInputBundle) -> tuple[list[dict[str, Any]], dict[str, int]]:
    context = bundle.context
    warnings: list[dict[str, Any]] = [dict(item) for item in bundle.warnings]
    shots_by_id = {shot.revision_item_id: shot for shot in context.shots}

    vlm_records = _component_records(bundle, "VLM", "VLM_OUTPUT")
    vlm_by_shot = {
        item.shot_revision_item_id: item
        for item in vlm_records
        if item.shot_revision_item_id in shots_by_id
    }
    missing_vlm_shots = [shot for shot in context.shots if shot.revision_item_id not in vlm_by_shot]
    for shot in missing_vlm_shots:
        warnings.append({
            "code": "VLM_SHOT_SEMANTICS_MISSING",
            "message": f"Shot {shot.ordinal} 没有可用 VLM_OUTPUT；将生成保守空语义 Shot Draft",
        })

    segment_plans = _segment_plans(context.shots, vlm_by_shot)
    asr_segments = _component_records(bundle, "ASR", "ASR_SEGMENT")
    asr_words = _component_records(bundle, "ASR", "ASR_WORD")
    ocr_records = _component_records(bundle, "OCR", "OCR_OBSERVATION")
    ocr_interval_raw = bundle.components["OCR"].result.metadata.get("sample_interval_us")
    try:
        ocr_interval = max(1, int(ocr_interval_raw))
    except (TypeError, ValueError):
        ocr_interval = _OCR_DEFAULT_SAMPLE_INTERVAL_US
    ocr_clusters, ocr_warnings = _ocr_clusters(
        ocr_records,
        shots_by_id,
        sample_interval_us=ocr_interval,
    )
    warnings.extend(ocr_warnings)

    # ASR word → segment provenance index.
    words_by_segment: dict[str, list[p2.P2EvidenceRecord]] = {}
    for word in asr_words:
        payload = word.payload if isinstance(word.payload, Mapping) else {}
        segment_id = str(payload.get("segment_id") or "").strip()
        if segment_id:
            words_by_segment.setdefault(segment_id, []).append(word)

    with studio_v2.get_session() as session:
        run = session.get(BreakdownRun, context.run_id)
        if run is None:
            raise LookupError("Breakdown Run 不存在")
        _assert_empty_processing_run(session, run)

        link_dedupe: set[tuple[str, str, str, str | None, str]] = set()
        shot_draft_by_item: dict[str, ShotSemanticDraft] = {}
        segment_by_shot_item: dict[str, SceneSegmentDraft] = {}
        subject_by_shot_label: dict[tuple[str, str], LocalSubject] = {}
        vlm_uri = bundle.components["VLM"].artifact_uri
        asr_uri = bundle.components["ASR"].artifact_uri
        ocr_uri = bundle.components["OCR"].artifact_uri

        generated_counts = {
            "scene_segment": 0,
            "shot": 0,
            "local_subject": 0,
            "shot_local_subject": 0,
            "timeline_event": 0,
            "timeline_event_subject": 0,
            "prop_hint": 0,
            "prop_occurrence": 0,
            "evidence_link": 0,
        }

        # 1) Scene segments + ShotSemanticDrafts.
        for segment_plan in segment_plans:
            first_shot = segment_plan.shots[0]
            last_shot = segment_plan.shots[-1]
            scene_values = [
                semantic.get("scene") if isinstance(semantic, Mapping) and isinstance(semantic.get("scene"), Mapping) else {}
                for semantic in segment_plan.semantics
            ]
            shot_values = [
                semantic.get("shot") if isinstance(semantic, Mapping) and isinstance(semantic.get("shot"), Mapping) else {}
                for semantic in segment_plan.semantics
            ]
            location = _unique_join((item.get("location_hint") for item in scene_values), max_len=255)
            mapped_ie = [_map_interior_exterior(item.get("interior_exterior")) for item in scene_values]
            ie_meaningful = {item for item in mapped_ie if item != "UNKNOWN"}
            interior_exterior = next(iter(ie_meaningful)) if len(ie_meaningful) == 1 else ("MIXED" if ie_meaningful else "UNKNOWN")
            mapped_tod = [_map_time_of_day(item.get("time_of_day")) for item in scene_values]
            tod_meaningful = {item for item in mapped_tod if item != "UNKNOWN"}
            time_of_day = next(iter(tod_meaningful)) if len(tod_meaningful) == 1 else "UNKNOWN"
            segment = SceneSegmentDraft(
                id=studio_v2.new_id("SCENESEG"),
                run_id=run.id,
                episode_id=run.episode_id,
                ordinal=segment_plan.index,
                source_start_us=first_shot.start_us,
                source_end_us=last_shot.end_us,
                location_hint=location,
                interior_exterior=interior_exterior,
                time_of_day=time_of_day,
                scene_function_hint=_clean_text(
                    next((item.get("narrative_function_hint") for item in shot_values if item.get("narrative_function_hint")), None),
                    max_len=128,
                ),
                summary=_unique_join((item.get("summary") for item in shot_values), max_len=2000),
                environment_description=_unique_join((item.get("environment_description") for item in scene_values), max_len=2000),
                confidence=None,
                metadata_json=_json_text({
                    "fusion_profile": FUSION_PROFILE,
                    "segmentation_policy": "consecutive-exact-scene-signature-v1",
                }),
            )
            session.add(segment)
            generated_counts["scene_segment"] += 1

            for shot, semantic in zip(segment_plan.shots, segment_plan.semantics):
                shot_semantic = semantic.get("shot") if isinstance(semantic, Mapping) and isinstance(semantic.get("shot"), Mapping) else {}
                vlm_record = vlm_by_shot.get(shot.revision_item_id)
                draft = ShotSemanticDraft(
                    id=studio_v2.new_id("SHOTDRAFT"),
                    run_id=run.id,
                    scene_segment_id=segment.id,
                    source_shot_revision_item_id=shot.revision_item_id,
                    source_shot_id_snapshot=shot.original_shot_id,
                    shot_ordinal_snapshot=shot.ordinal,
                    source_start_us=shot.start_us,
                    source_end_us=shot.end_us,
                    summary=_clean_text(shot_semantic.get("summary"), max_len=2000),
                    visual_description=_clean_text(shot_semantic.get("visual_description"), max_len=4000),
                    shot_language=context.source_language or None,
                    shot_type_hint=_clean_text(shot_semantic.get("shot_type_hint"), max_len=64),
                    camera_motion_hint=_clean_text(shot_semantic.get("camera_motion_hint"), max_len=64),
                    narrative_function_hint=_clean_text(shot_semantic.get("narrative_function_hint"), max_len=128),
                    confidence=None,
                    model_metadata_json=_json_text({
                        "fusion_profile": FUSION_PROFILE,
                        "vlm_semantic_schema": (
                            semantic.get("schema_version") if isinstance(semantic, Mapping) else None
                        ),
                        "vlm_output_missing": vlm_record is None,
                        "composition_hint": _clean_text(shot_semantic.get("composition_hint"), max_len=500),
                    }),
                )
                session.add(draft)
                shot_draft_by_item[shot.revision_item_id] = draft
                segment_by_shot_item[shot.revision_item_id] = segment
                generated_counts["shot"] += 1
                if vlm_record is not None:
                    _add_link(
                        session,
                        link_dedupe,
                        run_id=run.id,
                        owner_type="SHOT_DRAFT",
                        owner_id=draft.id,
                        record=vlm_record,
                        source_uri=vlm_uri,
                        role="PRIMARY",
                    )
                    _add_link(
                        session,
                        link_dedupe,
                        run_id=run.id,
                        owner_type="SCENE_SEGMENT",
                        owner_id=segment.id,
                        record=vlm_record,
                        source_uri=vlm_uri,
                        role="CONTEXT",
                    )

        # 2) Segment-scoped LocalSubject + per-Shot presence.
        for segment_plan in segment_plans:
            segment = segment_by_shot_item[segment_plan.shots[0].revision_item_id]
            ambiguous_appearances = _ambiguous_subject_appearances(segment_plan)
            subject_plans: dict[str, _SubjectPlan] = {}
            presences: list[tuple[p2.P2ShotInput, str, Mapping[str, Any], _SubjectPlan, p2.P2EvidenceRecord]] = []
            for shot, semantic in zip(segment_plan.shots, segment_plan.semantics):
                vlm_record = vlm_by_shot.get(shot.revision_item_id)
                if vlm_record is None or not isinstance(semantic, Mapping):
                    continue
                raw_subjects = semantic.get("subjects")
                if not isinstance(raw_subjects, list):
                    continue
                for raw_subject in raw_subjects:
                    if not isinstance(raw_subject, Mapping):
                        continue
                    label = str(raw_subject.get("label") or "").strip()
                    if not label:
                        continue
                    key = _appearance_key(raw_subject, shot, label, ambiguous_appearances)
                    plan = subject_plans.get(key)
                    if plan is None:
                        plan = _SubjectPlan(
                            key=key,
                            ordinal=len(subject_plans) + 1,
                            display_label=_subject_display_label(len(subject_plans) + 1),
                            appearance_summary=_clean_text(raw_subject.get("appearance_summary"), max_len=2000),
                        )
                        subject_plans[key] = plan
                    plan.source_labels.add(label)
                    plan.first_seen_us = shot.start_us if plan.first_seen_us is None else min(plan.first_seen_us, shot.start_us)
                    plan.last_seen_us = shot.end_us if plan.last_seen_us is None else max(plan.last_seen_us, shot.end_us)
                    plan.speaking_states.append(_map_speaking_state(raw_subject.get("speaking_state")))
                    presences.append((shot, label, raw_subject, plan, vlm_record))

            subject_row_by_key: dict[str, LocalSubject] = {}
            for plan in subject_plans.values():
                local = LocalSubject(
                    id=studio_v2.new_id("LOCALSUBJECT"),
                    run_id=run.id,
                    scene_segment_id=segment.id,
                    ordinal=plan.ordinal,
                    display_label=plan.display_label,
                    role_hint=None,
                    appearance_summary=plan.appearance_summary,
                    appearance_json=_json_text({
                        "fusion_profile": FUSION_PROFILE,
                        "source_labels": sorted(plan.source_labels),
                        "link_policy": "exact-normalized-appearance-with-same-shot-cannot-link-v2",
                        "ambiguous_appearance": plan.key.startswith("shot:"),
                    }),
                    first_seen_us=int(plan.first_seen_us if plan.first_seen_us is not None else segment.source_start_us),
                    last_seen_us=int(plan.last_seen_us if plan.last_seen_us is not None else segment.source_end_us),
                    speaking_state_summary=_speaking_summary(plan.speaking_states),
                    confidence=None,
                )
                session.add(local)
                subject_row_by_key[plan.key] = local
                generated_counts["local_subject"] += 1

            for shot, label, raw_subject, plan, vlm_record in presences:
                local = subject_row_by_key[plan.key]
                draft = shot_draft_by_item[shot.revision_item_id]
                presence = ShotLocalSubject(
                    id=studio_v2.new_id("SHOTSUBJECT"),
                    run_id=run.id,
                    shot_draft_id=draft.id,
                    local_subject_id=local.id,
                    first_seen_us=shot.start_us,
                    last_seen_us=shot.end_us,
                    screen_position=_map_screen_position(raw_subject.get("screen_position")),
                    visibility=_map_visibility(raw_subject.get("visibility")),
                    speaking_state=_map_speaking_state(raw_subject.get("speaking_state")),
                    activity_summary=_clean_text(raw_subject.get("activity_summary"), max_len=2000),
                    confidence=None,
                    search_hint_json=_json_text({
                        "source_vlm_label": label,
                        "raw_screen_position": _clean_text(raw_subject.get("screen_position"), max_len=200),
                        "appearance_summary": _clean_text(raw_subject.get("appearance_summary"), max_len=2000),
                    }),
                )
                session.add(presence)
                subject_by_shot_label[(shot.revision_item_id, label)] = local
                generated_counts["shot_local_subject"] += 1
                _add_link(
                    session,
                    link_dedupe,
                    run_id=run.id,
                    owner_type="LOCAL_SUBJECT",
                    owner_id=local.id,
                    record=vlm_record,
                    source_uri=vlm_uri,
                    role="SUPPORT",
                    metadata={"shot_revision_item_id": shot.revision_item_id, "source_label": label},
                )

        # 3) VLM visual/action timeline events.
        event_ordinals: dict[str, int] = {item_id: 0 for item_id in shot_draft_by_item}
        for shot in context.shots:
            vlm_record = vlm_by_shot.get(shot.revision_item_id)
            semantic = _semantic(vlm_record)
            if vlm_record is None or not isinstance(semantic, Mapping):
                continue
            raw_events = semantic.get("events")
            if not isinstance(raw_events, list):
                raw_events = []
            if not raw_events:
                shot_semantic = semantic.get("shot") if isinstance(semantic.get("shot"), Mapping) else {}
                summary = _clean_text(shot_semantic.get("summary"), max_len=2000)
                if summary:
                    raw_events = [{
                        "event_type": "VISUAL",
                        "start_ratio": 0.0,
                        "end_ratio": 1.0,
                        "content": summary,
                        "subject_labels": [],
                        "fallback_from_shot_summary": True,
                    }]
            for raw_event in raw_events:
                if not isinstance(raw_event, Mapping):
                    continue
                content = _clean_text(raw_event.get("content"), max_len=4000)
                event_type = str(raw_event.get("event_type") or "").strip().upper()
                if not content or event_type not in {"VISUAL", "ACTION"}:
                    continue
                source_start, source_end = _ratio_range(
                    shot,
                    raw_event.get("start_ratio"),
                    raw_event.get("end_ratio"),
                )
                draft = shot_draft_by_item[shot.revision_item_id]
                event_ordinals[shot.revision_item_id] += 1
                event = TimelineEvent(
                    id=studio_v2.new_id("EVENT"),
                    run_id=run.id,
                    shot_draft_id=draft.id,
                    ordinal=event_ordinals[shot.revision_item_id],
                    event_type=event_type,
                    source_start_us=source_start,
                    source_end_us=source_end,
                    shot_relative_start_us=source_start - shot.start_us,
                    shot_relative_end_us=source_end - shot.start_us,
                    content_text=content,
                    language=context.source_language or None,
                    emotion_hint=None,
                    speaking_style_hint=None,
                    confidence=None,
                    origin="VLM",
                    metadata_json=_json_text({
                        "fusion_profile": FUSION_PROFILE,
                        "start_ratio": raw_event.get("start_ratio"),
                        "end_ratio": raw_event.get("end_ratio"),
                        "fallback_from_shot_summary": bool(raw_event.get("fallback_from_shot_summary")),
                    }),
                )
                session.add(event)
                generated_counts["timeline_event"] += 1
                _add_link(
                    session,
                    link_dedupe,
                    run_id=run.id,
                    owner_type="TIMELINE_EVENT",
                    owner_id=event.id,
                    record=vlm_record,
                    source_uri=vlm_uri,
                    role="PRIMARY",
                )
                raw_labels = raw_event.get("subject_labels")
                if isinstance(raw_labels, list):
                    for raw_label in raw_labels:
                        label = str(raw_label or "").strip()
                        local = subject_by_shot_label.get((shot.revision_item_id, label))
                        if local is None:
                            continue
                        session.add(TimelineEventSubject(
                            id=studio_v2.new_id("EVENTSUBJECT"),
                            event_id=event.id,
                            local_subject_id=local.id,
                            role="ACTOR",
                            confidence=None,
                        ))
                        generated_counts["timeline_event_subject"] += 1

        # 4) ASR: split every segment against exact historical Shot boundaries.
        for segment_record in sorted(asr_segments, key=lambda item: (item.source_start_us or 0, item.source_id)):
            if segment_record.source_start_us is None or segment_record.source_end_us is None:
                warnings.append({"code": "ASR_SEGMENT_NO_TIME", "message": f"ASR segment {segment_record.source_id} 无合法 source time，已忽略"})
                continue
            segment_words = sorted(
                words_by_segment.get(segment_record.source_id, []),
                key=lambda item: (item.source_start_us or 0, item.source_id),
            )
            matched_shots = 0
            for shot in context.shots:
                overlap_start = max(segment_record.source_start_us, shot.start_us)
                overlap_end = min(segment_record.source_end_us, shot.end_us)
                if overlap_end <= overlap_start:
                    continue
                matched_shots += 1
                words_in_shot = [
                    word for word in segment_words
                    if word.source_start_us is not None
                    and word.source_end_us is not None
                    and min(word.source_end_us, shot.end_us) > max(word.source_start_us, shot.start_us)
                ]
                if words_in_shot:
                    source_start = max(shot.start_us, min(int(word.source_start_us) for word in words_in_shot if word.source_start_us is not None))
                    source_end = min(shot.end_us, max(int(word.source_end_us) for word in words_in_shot if word.source_end_us is not None))
                    raw_parts = []
                    for word in words_in_shot:
                        payload = word.payload if isinstance(word.payload, Mapping) else {}
                        raw_parts.append(str(payload.get("raw_word") or word.text or ""))
                    content = "".join(raw_parts).strip() or " ".join(str(word.text or "").strip() for word in words_in_shot).strip()
                    text_policy = "word-timestamp-split"
                else:
                    source_start, source_end = overlap_start, overlap_end
                    content = _clean_text(segment_record.text, max_len=4000) or ""
                    text_policy = "segment-text-fallback"
                    if matched_shots > 1 or (
                        segment_record.source_start_us < shot.start_us
                        or segment_record.source_end_us > shot.end_us
                    ):
                        warnings.append({
                            "code": "ASR_CROSS_SHOT_TEXT_FALLBACK",
                            "message": f"ASR segment {segment_record.source_id} 跨 Shot 但无可用 word timing；片段文本被保守复制到交集事件",
                        })
                if not content:
                    continue
                source_start = max(shot.start_us, min(shot.end_us - 1, int(source_start)))
                source_end = max(source_start + 1, min(shot.end_us, int(source_end)))
                draft = shot_draft_by_item[shot.revision_item_id]
                event_ordinals[shot.revision_item_id] += 1
                event = TimelineEvent(
                    id=studio_v2.new_id("EVENT"),
                    run_id=run.id,
                    shot_draft_id=draft.id,
                    ordinal=event_ordinals[shot.revision_item_id],
                    event_type="DIALOGUE",
                    source_start_us=source_start,
                    source_end_us=source_end,
                    shot_relative_start_us=source_start - shot.start_us,
                    shot_relative_end_us=source_end - shot.start_us,
                    content_text=content,
                    language=segment_record.language or context.source_language or None,
                    emotion_hint=None,
                    speaking_style_hint=None,
                    confidence=_mean_confidence(words_in_shot),
                    origin="ASR",
                    metadata_json=_json_text({
                        "fusion_profile": FUSION_PROFILE,
                        "asr_segment_id": segment_record.source_id,
                        "text_policy": text_policy,
                        "word_ids": [item.source_id for item in words_in_shot],
                        "cross_shot": not (
                            segment_record.source_start_us >= shot.start_us
                            and segment_record.source_end_us <= shot.end_us
                        ),
                    }),
                )
                session.add(event)
                generated_counts["timeline_event"] += 1
                _add_link(
                    session,
                    link_dedupe,
                    run_id=run.id,
                    owner_type="TIMELINE_EVENT",
                    owner_id=event.id,
                    record=segment_record,
                    source_uri=asr_uri,
                    role="PRIMARY",
                )
                for word in words_in_shot:
                    _add_link(
                        session,
                        link_dedupe,
                        run_id=run.id,
                        owner_type="TIMELINE_EVENT",
                        owner_id=event.id,
                        record=word,
                        source_uri=asr_uri,
                        role="SUPPORT",
                    )
            if matched_shots == 0:
                warnings.append({"code": "ASR_SEGMENT_OUTSIDE_SHOTS", "message": f"ASR segment {segment_record.source_id} 未与任何 source Shot 相交，已忽略"})

        # 5) OCR: dedupe/stitch frame observations into OCR TimelineEvents.
        for cluster in ocr_clusters:
            if not cluster.records:
                continue
            shot = cluster.shot
            first = cluster.records[0]
            last = cluster.records[-1]
            if first.source_start_us is None or last.source_start_us is None:
                continue
            source_start = max(shot.start_us, min(shot.end_us - 1, int(first.source_start_us)))
            if len(cluster.records) == 1:
                source_end = min(shot.end_us, source_start + 1)
                duration_policy = "point-observation"
            else:
                source_end = min(shot.end_us, int(last.source_start_us) + ocr_interval)
                source_end = max(source_start + 1, source_end)
                duration_policy = "repeat-observation-inferred"
            draft = shot_draft_by_item[shot.revision_item_id]
            event_ordinals[shot.revision_item_id] += 1
            event = TimelineEvent(
                id=studio_v2.new_id("EVENT"),
                run_id=run.id,
                shot_draft_id=draft.id,
                ordinal=event_ordinals[shot.revision_item_id],
                event_type="OCR",
                source_start_us=source_start,
                source_end_us=source_end,
                shot_relative_start_us=source_start - shot.start_us,
                shot_relative_end_us=source_end - shot.start_us,
                content_text=cluster.text,
                language=first.language or context.source_language or None,
                emotion_hint=None,
                speaking_style_hint=None,
                confidence=_mean_confidence(cluster.records),
                origin="OCR",
                metadata_json=_json_text({
                    "fusion_profile": FUSION_PROFILE,
                    "duration_policy": duration_policy,
                    "observation_count": len(cluster.records),
                    "observation_ids": [item.source_id for item in cluster.records],
                    "bbox_norm": list(cluster.bbox_norm) if cluster.bbox_norm is not None else None,
                }),
            )
            session.add(event)
            generated_counts["timeline_event"] += 1
            for index, record in enumerate(cluster.records):
                _add_link(
                    session,
                    link_dedupe,
                    run_id=run.id,
                    owner_type="TIMELINE_EVENT",
                    owner_id=event.id,
                    record=record,
                    source_uri=ocr_uri,
                    role="PRIMARY" if index == 0 else "SUPPORT",
                )

        # 6) VLM props → Segment-scoped DraftPropHint + per-Shot occurrence.
        prop_plans_by_segment: dict[str, dict[str, _PropPlan]] = {}
        prop_occurrence_specs: list[tuple[str, p2.P2ShotInput, Mapping[str, Any], p2.P2EvidenceRecord]] = []
        for shot in context.shots:
            vlm_record = vlm_by_shot.get(shot.revision_item_id)
            semantic = _semantic(vlm_record)
            if vlm_record is None or not isinstance(semantic, Mapping):
                continue
            raw_props = semantic.get("props")
            if not isinstance(raw_props, list):
                continue
            segment = segment_by_shot_item[shot.revision_item_id]
            plans = prop_plans_by_segment.setdefault(segment.id, {})
            seen_in_shot: set[str] = set()
            for raw_prop in raw_props:
                if not isinstance(raw_prop, Mapping):
                    continue
                label = _clean_text(raw_prop.get("label"), max_len=255)
                normalized = _normalized_text(label)
                if not label or not normalized or normalized in seen_in_shot:
                    continue
                seen_in_shot.add(normalized)
                plan = plans.get(normalized)
                if plan is None:
                    plan = _PropPlan(
                        normalized_label=normalized,
                        label=label,
                        importance=_importance(raw_prop.get("importance")),
                    )
                    plans[normalized] = plan
                # 同一 prop 多 Shot 出现时保留更高重要度。
                rank = {"UNKNOWN": 0, "AMBIENT": 1, "SUPPORTING": 2, "KEY": 3}
                candidate_importance = _importance(raw_prop.get("importance"))
                if rank[candidate_importance] > rank[plan.importance]:
                    plan.importance = candidate_importance
                reason = _clean_text(raw_prop.get("narrative_reason"), max_len=2000)
                if reason and reason not in plan.reasons:
                    plan.reasons.append(reason)
                plan.first_seen_us = shot.start_us if plan.first_seen_us is None else min(plan.first_seen_us, shot.start_us)
                plan.last_seen_us = shot.end_us if plan.last_seen_us is None else max(plan.last_seen_us, shot.end_us)
                if vlm_record.source_id not in plan.source_ids:
                    plan.source_ids.append(vlm_record.source_id)
                prop_occurrence_specs.append((normalized, shot, raw_prop, vlm_record))

        prop_row_by_segment_key: dict[tuple[str, str], DraftPropHint] = {}
        for segment_id, plans in prop_plans_by_segment.items():
            for ordinal, plan in enumerate(plans.values(), start=1):
                prop = DraftPropHint(
                    id=studio_v2.new_id("PROPHINT"),
                    run_id=run.id,
                    scene_segment_id=segment_id,
                    ordinal=ordinal,
                    label_hint=plan.label,
                    normalized_hint=plan.normalized_label[:255],
                    importance=plan.importance,
                    narrative_reason=_unique_join(plan.reasons, max_len=3000),
                    first_seen_us=int(plan.first_seen_us or 0),
                    last_seen_us=int(plan.last_seen_us or plan.first_seen_us or 0),
                    confidence=None,
                    metadata_json=_json_text({
                        "fusion_profile": FUSION_PROFILE,
                        "source": "VLM",
                    }),
                )
                session.add(prop)
                prop_row_by_segment_key[(segment_id, plan.normalized_label)] = prop
                generated_counts["prop_hint"] += 1
                for source_id in plan.source_ids:
                    source_record = next((item for item in vlm_records if item.source_id == source_id), None)
                    if source_record is not None:
                        _add_link(
                            session,
                            link_dedupe,
                            run_id=run.id,
                            owner_type="PROP_HINT",
                            owner_id=prop.id,
                            record=source_record,
                            source_uri=vlm_uri,
                            role="SUPPORT",
                        )

        for normalized, shot, raw_prop, _vlm_record in prop_occurrence_specs:
            segment = segment_by_shot_item[shot.revision_item_id]
            prop = prop_row_by_segment_key[(segment.id, normalized)]
            labels = raw_prop.get("subject_labels")
            label_text = ", ".join(str(item) for item in labels) if isinstance(labels, list) else ""
            reason = _clean_text(raw_prop.get("narrative_reason"), max_len=1600)
            interaction = reason
            if label_text:
                interaction = f"{label_text}: {reason}" if reason else label_text
            session.add(DraftPropOccurrence(
                id=studio_v2.new_id("PROPOCC"),
                prop_hint_id=prop.id,
                shot_draft_id=shot_draft_by_item[shot.revision_item_id].id,
                source_start_us=shot.start_us,
                source_end_us=shot.end_us,
                screen_position_hint=None,
                interaction_summary=interaction,
                confidence=None,
                search_region_hint_json=_json_text({
                    "source": "VLM",
                    "subject_labels": labels if isinstance(labels, list) else [],
                }),
            ))
            generated_counts["prop_occurrence"] += 1

        generated_counts["evidence_link"] = len(link_dedupe)
        statuses = _json_object(run.component_status_json)
        statuses["FUSION"] = {
            "status": "READY_WITH_WARNINGS" if warnings else "READY",
            "profile": FUSION_PROFILE,
            "version": FUSION_VERSION,
            "warnings": warnings,
            "generated_counts": generated_counts,
        }
        providers = _json_object(run.provider_metadata_json)
        providers["p2_fusion"] = {
            "profile": FUSION_PROFILE,
            "version": FUSION_VERSION,
            "scene_segmentation_policy": "consecutive-exact-scene-signature-v1",
            "subject_link_policy": "exact-normalized-appearance-with-same-shot-cannot-link-v2",
            "asr_policy": "exact-shot-boundary-word-timestamp-split-v1",
            "ocr_policy": "text-time-geometry-stitch-v1",
            "vlm_event_time_policy": "shot-relative-ratio-to-source-us-v1",
        }
        run.component_status_json = _json_text(statuses)
        run.provider_metadata_json = _json_text(providers)
        session.commit()
        return warnings, generated_counts


def fuse_breakdown_run(run_id: str) -> BreakdownRun:
    """P2.5 正式入口：读取 immutable sidecars → 写完整匿名 Draft → validator/publish。

    任一 pre-publish Fusion 硬失败会把仍处于 PROCESSING 的 Run 安全收口为 FAILED；
    若 Run 已因 ShotRevision 切换变为 STALE，则保留 STALE，不覆盖生命周期事实。
    """

    try:
        bundle = load_fusion_inputs(run_id)
        warnings, _generated_counts = _write_fused_draft(bundle)
        return breakdown_service_v1.publish_breakdown_run(
            run_id,
            warnings=warnings or None,
        )
    except Exception as exc:
        _safe_fail_run(run_id, exc)
        raise
