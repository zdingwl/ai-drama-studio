"""P4.2 Draft-guided Scene / Prop Evidence verification.

The existing asset-side SceneCandidate / ShotSceneEvidence / PropCandidate /
ShotPropEvidence remain authoritative Evidence containers. This module only changes
*where and what* the asset semantic model verifies:

- current P2/P3 SceneSegmentDraft narrows scene semantics;
- current DraftPropOccurrence becomes an explicit object-verification target;
- the VLM must re-observe the current Shot thumbnail and may reject a Draft hint;
- verified props can carry normalized bounding-box Evidence;
- unprompted prop discovery remains possible but uses a higher confidence threshold;
- no Draft row is ever converted directly to a Final Scene / Prop or Final binding.

When no revision-safe current Breakdown guidance exists, the legacy unguided semantic
enrichment path is used unchanged.
"""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx
from sqlalchemy import delete, select

from engine.app.asset_semantics_v3 import (
    _analyze_image as _legacy_analyze_image,
    _extract_json,
    _image_data_url,
    enrich_asset_run as _legacy_enrich_asset_run,
    semantic_model_status,
)
from engine.app.breakdown_asset_guidance_v1 import (
    GUIDANCE_PROFILE,
    ProjectAssetGuidance,
    PropSearchGuide,
    ShotAssetGuidance,
    load_project_asset_guidance,
)
from engine.app.content_analysis_v2 import (
    ContentAnalysisRun,
    PropCandidate,
    SceneCandidate,
    ShotPropEvidence,
    ShotSceneEvidence,
)
from engine.app.studio_v2 import Episode, Shot, get_session, new_id

SemanticProgress = Callable[[int, int, str], None]
GUIDED_PROP_MIN_CONFIDENCE = 0.45
DISCOVERED_PROP_MIN_CONFIDENCE = 0.68
SCENE_MIN_CONFIDENCE = 0.40
MAX_DISCOVERED_PROPS = 4


class AssetSemanticP4Error(RuntimeError):
    """P4 Draft-guided semantic verification cannot safely continue."""


def _clean_text(value: Any, *, max_len: int = 1200) -> str | None:
    text = " ".join(str(value or "").strip().split())
    return text[:max_len] if text else None


def _confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, number))


def _norm_name(value: Any) -> str:
    return "".join(str(value or "").strip().lower().split())


def _bbox_norm(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        x1, y1, x2, y2 = (float(item) for item in value[:4])
    except (TypeError, ValueError):
        return None
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    values = [x1, y1, x2, y2]
    if any(item < 0.0 or item > 1.0 for item in values):
        return None
    if x2 - x1 <= 0.001 or y2 - y1 <= 0.001:
        return None
    return [round(item, 6) for item in values]


def _scene_hint_text(guidance: ShotAssetGuidance) -> str:
    scene = guidance.scene
    if scene is None:
        return "无场景 Draft 提示"
    parts = [
        f"地点提示={scene.location_hint or '未知'}",
        f"室内外={scene.interior_exterior or 'UNKNOWN'}",
        f"时段={scene.time_of_day or 'UNKNOWN'}",
    ]
    if scene.environment_description:
        parts.append(f"环境描述={scene.environment_description}")
    if scene.summary:
        parts.append(f"场景摘要={scene.summary}")
    return "；".join(parts)


def _prop_target_rows(guidance: ShotAssetGuidance) -> tuple[list[dict[str, str]], dict[str, PropSearchGuide]]:
    rows: list[dict[str, str]] = []
    mapping: dict[str, PropSearchGuide] = {}
    for index, prop in enumerate(guidance.props[:12], start=1):
        key = f"P{index}"
        mapping[key] = prop
        rows.append({
            "target_key": key,
            "label": prop.label_hint,
            "importance": prop.importance,
            "screen_position_hint": prop.screen_position_hint or "未知",
            "interaction": prop.interaction_summary or "",
            "reason": prop.narrative_reason or "",
        })
    return rows, mapping


def build_guided_prompt(guidance: ShotAssetGuidance) -> tuple[str, dict[str, PropSearchGuide]]:
    """Build a verification prompt. Draft hints are explicitly hypotheses, never facts."""

    prop_rows, target_map = _prop_target_rows(guidance)
    prompt = f"""你正在为短剧资产提取重新验证一个当前 Shot 的场景与关键道具。
下面的 Breakdown Draft 只是搜索提示/假设，可能正确、可能错误。你必须以当前图片中真正可见的内容为准，不能因为 Draft 写了某物就声称看见它。

场景 Draft 提示：
{_scene_hint_text(guidance)}

道具 Draft 待验证目标：
{json.dumps(prop_rows, ensure_ascii=False)}

规则：
1. 只返回一个 JSON object，不要解释。
2. scene.label 用简短稳定中文地点类别；indoor_outdoor 只能是 内/外/未知；time_of_day 只能是 日/夜/未知。
3. scene.draft_match 只能是 MATCH/CONFLICT/UNKNOWN。即使与 Draft 冲突，也要写图片实际支持的 scene.label。
4. guided_props 必须逐个返回上面的 target_key；看不见就 observed=false，不允许猜。
5. observed=true 的道具给出 confidence 0..1；如果能定位，bbox_norm=[x1,y1,x2,y2]，坐标相对图片宽高归一化到 0..1；无法可靠定位则 null。
6. discovered_props 只补充 Draft 漏掉但明显剧情相关、重制需要保持一致的关键物体；普通家具、墙、地板、人物衣服不要列入。
7. 不识别人名/Character，不创建 Scene ID / Prop ID / Final Binding。

JSON 格式：
{{
  "scene": {{
    "label": "",
    "indoor_outdoor": "内|外|未知",
    "time_of_day": "日|夜|未知",
    "confidence": 0.0,
    "draft_match": "MATCH|CONFLICT|UNKNOWN",
    "reason": "简短中文视觉依据"
  }},
  "guided_props": [
    {{
      "target_key": "P1",
      "observed": true,
      "confidence": 0.0,
      "reason": "简短中文视觉依据",
      "bbox_norm": [0.0, 0.0, 1.0, 1.0]
    }}
  ],
  "discovered_props": [
    {{
      "name": "",
      "confidence": 0.0,
      "reason": "",
      "bbox_norm": [0.0, 0.0, 1.0, 1.0]
    }}
  ]
}}
"""
    return prompt, target_map


def _request_vlm(path: Path, prompt: str) -> dict[str, Any]:
    status = semantic_model_status()
    if not status["ready"]:
        raise AssetSemanticP4Error("Qwen3-VL 本地服务未配置")
    base_url = str(status["base_url"])
    model = str(status["model"])
    api_key = os.getenv("AI_DRAMA_VLM_API_KEY", "EMPTY").strip() or "EMPTY"
    payload = {
        "model": model,
        "temperature": 0.0,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _image_data_url(path)}},
            ],
        }],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AssetSemanticP4Error(f"Qwen3-VL P4 请求失败：{exc}") from exc
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AssetSemanticP4Error("Qwen3-VL P4 返回结构不符合 OpenAI-compatible 格式") from exc
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return _extract_json(str(content))


def _normalize_guided_result(raw: Mapping[str, Any], guidance: ShotAssetGuidance) -> dict[str, Any]:
    prompt, target_map = build_guided_prompt(guidance)
    del prompt  # target map is what normalization needs; prompt is built by caller too.

    raw_scene = raw.get("scene") if isinstance(raw.get("scene"), Mapping) else {}
    scene = {
        "label": _clean_text(raw_scene.get("label"), max_len=100),
        "indoor_outdoor": str(raw_scene.get("indoor_outdoor") or "未知").strip(),
        "time_of_day": str(raw_scene.get("time_of_day") or "未知").strip(),
        "confidence": _confidence(raw_scene.get("confidence")),
        "draft_match": str(raw_scene.get("draft_match") or "UNKNOWN").strip().upper(),
        "reason": _clean_text(raw_scene.get("reason")),
    }
    if scene["indoor_outdoor"] not in {"内", "外", "未知"}:
        scene["indoor_outdoor"] = "未知"
    if scene["time_of_day"] not in {"日", "夜", "未知"}:
        scene["time_of_day"] = "未知"
    if scene["draft_match"] not in {"MATCH", "CONFLICT", "UNKNOWN"}:
        scene["draft_match"] = "UNKNOWN"

    guided_props: list[dict[str, Any]] = []
    raw_guided = raw.get("guided_props")
    by_key: dict[str, Mapping[str, Any]] = {}
    if isinstance(raw_guided, list):
        for item in raw_guided:
            if not isinstance(item, Mapping):
                continue
            key = str(item.get("target_key") or "").strip().upper()
            if key and key in target_map and key not in by_key:
                by_key[key] = item
    for key, guide in target_map.items():
        item = by_key.get(key) or {}
        observed = item.get("observed") is True
        guided_props.append({
            "target_key": key,
            "prop_hint_id": guide.prop_hint_id,
            "occurrence_id": guide.occurrence_id,
            "name": guide.label_hint,
            "observed": observed,
            "confidence": _confidence(item.get("confidence")) if observed else 0.0,
            "reason": _clean_text(item.get("reason")),
            "bbox_norm": _bbox_norm(item.get("bbox_norm")) if observed else None,
        })

    discovered_props: list[dict[str, Any]] = []
    raw_discovered = raw.get("discovered_props")
    if isinstance(raw_discovered, list):
        for item in raw_discovered[:MAX_DISCOVERED_PROPS]:
            if not isinstance(item, Mapping):
                continue
            name = _clean_text(item.get("name"), max_len=100)
            confidence = _confidence(item.get("confidence"))
            if not name or confidence is None:
                continue
            discovered_props.append({
                "name": name,
                "confidence": confidence,
                "reason": _clean_text(item.get("reason")),
                "bbox_norm": _bbox_norm(item.get("bbox_norm")),
            })

    return {"scene": scene, "guided_props": guided_props, "discovered_props": discovered_props}


def _analyze_guided_image(path: Path, guidance: ShotAssetGuidance) -> dict[str, Any]:
    prompt, _target_map = build_guided_prompt(guidance)
    raw = _request_vlm(path, prompt)
    return _normalize_guided_result(raw, guidance)


def _normalize_legacy_result(raw: Mapping[str, Any]) -> dict[str, Any]:
    props: list[dict[str, Any]] = []
    raw_props = raw.get("props")
    if isinstance(raw_props, list):
        for item in raw_props[:MAX_DISCOVERED_PROPS]:
            if not isinstance(item, Mapping):
                continue
            name = _clean_text(item.get("name"), max_len=100)
            confidence = _confidence(item.get("confidence"))
            if name and confidence is not None:
                props.append({
                    "name": name,
                    "confidence": confidence,
                    "reason": _clean_text(item.get("reason")),
                    "bbox_norm": None,
                })
    return {
        "scene": {
            "label": _clean_text(raw.get("scene_label"), max_len=100),
            "indoor_outdoor": str(raw.get("indoor_outdoor") or "未知"),
            "time_of_day": str(raw.get("time_of_day") or "未知"),
            "confidence": None,
            "draft_match": "UNGUIDED",
            "reason": None,
        },
        "guided_props": [],
        "discovered_props": props,
    }


def _append_prop_bucket(
    bucket_by_name: dict[str, dict[str, Any]],
    *,
    shot_id: str,
    name: str,
    confidence: float,
    reason: str | None,
    bbox: list[float] | None,
    mode: str,
    prop_hint_id: str | None = None,
    occurrence_id: str | None = None,
) -> None:
    key = _norm_name(name)
    if not key:
        return
    bucket = bucket_by_name.setdefault(key, {
        "name": name,
        "scores": [],
        "shot_ids": set(),
        "reasons": [],
        "modes": set(),
        "draft_prop_hint_ids": set(),
        "draft_occurrence_ids": set(),
        "bbox_by_shot": {},
    })
    bucket["scores"].append(confidence)
    bucket["shot_ids"].add(shot_id)
    bucket["modes"].add(mode)
    if reason:
        bucket["reasons"].append(reason)
    if prop_hint_id:
        bucket["draft_prop_hint_ids"].add(prop_hint_id)
    if occurrence_id:
        bucket["draft_occurrence_ids"].add(occurrence_id)
    if bbox is not None:
        bucket["bbox_by_shot"][shot_id] = bbox


def enrich_asset_run(
    run_id: str,
    project_id: str,
    progress: SemanticProgress | None = None,
) -> dict[str, Any]:
    """Verify Scene/Prop Evidence using current Breakdown guidance when available."""

    guidance: ProjectAssetGuidance = load_project_asset_guidance(project_id)
    if not guidance.shots:
        legacy = dict(_legacy_enrich_asset_run(run_id, project_id, progress=progress))
        legacy.update({
            "guidance_profile": GUIDANCE_PROFILE,
            "guidance_status": "NO_CURRENT_DRAFT",
            "guided_shot_count": 0,
            "guided_prop_target_count": 0,
        })
        return legacy

    if not semantic_model_status()["ready"]:
        return {
            "status": "NOT_CONFIGURED",
            "prop_count": 0,
            "shot_count": 0,
            "guidance_profile": GUIDANCE_PROFILE,
            "guidance_status": "READY",
            "guided_shot_count": guidance.guided_shot_count,
            "guided_prop_target_count": guidance.prop_target_count,
        }

    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None or run.project_id != project_id:
            raise LookupError("资产分析 Run 不存在")
        shots = list(session.scalars(
            select(Shot)
            .join(Episode, Episode.id == Shot.episode_id)
            .where(Episode.project_id == project_id)
            .order_by(Episode.sort_order, Shot.ordinal)
        ).all())
        scene_links = list(session.scalars(
            select(ShotSceneEvidence).where(ShotSceneEvidence.run_id == run_id)
        ).all())
        scene_id_by_shot = {item.shot_id: item.scene_candidate_id for item in scene_links}

    shot_semantics: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    guided_processed = 0
    total = len(shots)
    for index, shot in enumerate(shots, start=1):
        guide = guidance.shots.get(shot.id)
        mode = "Draft 定向验证" if guide is not None else "常规语义验证"
        if progress:
            progress(index, total, f"Qwen3-VL {mode} Shot {index} / {total}")
        path = Path(shot.thumbnail_path) if shot.thumbnail_path else None
        if path is None or not path.is_file():
            continue
        try:
            if guide is not None:
                shot_semantics[shot.id] = _analyze_guided_image(path, guide)
                guided_processed += 1
            else:
                shot_semantics[shot.id] = _normalize_legacy_result(_legacy_analyze_image(path))
        except Exception as exc:
            failures.append(f"Shot {shot.ordinal}: {type(exc).__name__}: {_clean_text(exc, max_len=500) or 'semantic verification failed'}")

    if not shot_semantics:
        raise AssetSemanticP4Error("P4 场景/道具语义验证没有成功分析任何 Shot")

    scene_values: dict[str, list[dict[str, Any]]] = {}
    prop_bucket: dict[str, dict[str, Any]] = {}
    for shot in shots:
        result = shot_semantics.get(shot.id)
        if not result:
            continue
        guide = guidance.shots.get(shot.id)
        scene_id = scene_id_by_shot.get(shot.id)
        scene = result.get("scene") if isinstance(result.get("scene"), Mapping) else {}
        scene_label = _clean_text(scene.get("label"), max_len=100)
        scene_confidence = _confidence(scene.get("confidence"))
        if scene_id and scene_label and (scene_confidence is None or scene_confidence >= SCENE_MIN_CONFIDENCE):
            scene_values.setdefault(scene_id, []).append({
                "shot_id": shot.id,
                "label": scene_label,
                "indoor_outdoor": str(scene.get("indoor_outdoor") or "未知"),
                "time_of_day": str(scene.get("time_of_day") or "未知"),
                "confidence": scene_confidence,
                "draft_match": str(scene.get("draft_match") or "UNKNOWN"),
                "reason": _clean_text(scene.get("reason")),
                "breakdown_run_id": guide.breakdown_run_id if guide else None,
                "scene_segment_id": guide.scene.scene_segment_id if guide and guide.scene else None,
            })

        raw_guided = result.get("guided_props")
        if isinstance(raw_guided, list):
            for item in raw_guided:
                if not isinstance(item, Mapping) or item.get("observed") is not True:
                    continue
                confidence = _confidence(item.get("confidence"))
                name = _clean_text(item.get("name"), max_len=100)
                if name is None or confidence is None or confidence < GUIDED_PROP_MIN_CONFIDENCE:
                    continue
                _append_prop_bucket(
                    prop_bucket,
                    shot_id=shot.id,
                    name=name,
                    confidence=confidence,
                    reason=_clean_text(item.get("reason")),
                    bbox=_bbox_norm(item.get("bbox_norm")),
                    mode="DRAFT_GUIDED_VERIFIED",
                    prop_hint_id=_clean_text(item.get("prop_hint_id"), max_len=64),
                    occurrence_id=_clean_text(item.get("occurrence_id"), max_len=64),
                )

        raw_discovered = result.get("discovered_props")
        if isinstance(raw_discovered, list):
            for item in raw_discovered:
                if not isinstance(item, Mapping):
                    continue
                confidence = _confidence(item.get("confidence"))
                name = _clean_text(item.get("name"), max_len=100)
                if name is None or confidence is None or confidence < DISCOVERED_PROP_MIN_CONFIDENCE:
                    continue
                _append_prop_bucket(
                    prop_bucket,
                    shot_id=shot.id,
                    name=name,
                    confidence=confidence,
                    reason=_clean_text(item.get("reason")),
                    bbox=_bbox_norm(item.get("bbox_norm")),
                    mode="DISCOVERED",
                )

    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None:
            raise LookupError("资产分析 Run 不存在")

        for scene_id, observations in scene_values.items():
            scene_candidate = session.get(SceneCandidate, scene_id)
            if scene_candidate is None or not observations:
                continue
            label = Counter(str(item["label"]) for item in observations).most_common(1)[0][0]
            matching = [item for item in observations if item["label"] == label]
            io = Counter(str(item["indoor_outdoor"]) for item in matching).most_common(1)[0][0]
            tod = Counter(str(item["time_of_day"]) for item in matching).most_common(1)[0][0]
            suffix = " / ".join(value for value in (io, tod) if value and value != "未知")
            scene_candidate.auto_label = f"{label} · {suffix}" if suffix else label
            try:
                evidence = json.loads(scene_candidate.evidence_json or "{}")
            except (TypeError, ValueError):
                evidence = {}
            evidence["vlm"] = {
                "provider": "Qwen3-VL",
                "scene_label": label,
                "indoor_outdoor": io,
                "time_of_day": tod,
            }
            evidence["p4_breakdown_guided"] = {
                "profile": GUIDANCE_PROFILE,
                "verification_provider": "Qwen3-VL",
                "observation_count": len(observations),
                "breakdown_run_ids": sorted({str(item["breakdown_run_id"]) for item in observations if item.get("breakdown_run_id")}),
                "scene_segment_ids": sorted({str(item["scene_segment_id"]) for item in observations if item.get("scene_segment_id")}),
                "draft_match_counts": dict(Counter(str(item["draft_match"]) for item in observations)),
                "observations": observations[:20],
            }
            scene_candidate.evidence_json = json.dumps(evidence, ensure_ascii=False)

        session.execute(delete(ShotPropEvidence).where(ShotPropEvidence.run_id == run_id))
        session.execute(delete(PropCandidate).where(PropCandidate.run_id == run_id))
        prop_count = 0
        ordered_buckets = sorted(
            prop_bucket.values(),
            key=lambda item: (-len(item["shot_ids"]), item["name"]),
        )
        for ordinal, bucket in enumerate(ordered_buckets, start=1):
            candidate_id = new_id("PROP_CANDIDATE")
            scores = list(bucket["scores"])
            confidence = sum(scores) / len(scores) if scores else None
            session.add(PropCandidate(
                id=candidate_id,
                run_id=run_id,
                project_id=project_id,
                ordinal=ordinal,
                auto_label=str(bucket["name"]),
                confidence=confidence,
                evidence_json=json.dumps({
                    "provider": "Qwen3-VL",
                    "profile": GUIDANCE_PROFILE,
                    "verification_modes": sorted(bucket["modes"]),
                    "shot_count": len(bucket["shot_ids"]),
                    "draft_prop_hint_ids": sorted(bucket["draft_prop_hint_ids"]),
                    "draft_occurrence_ids": sorted(bucket["draft_occurrence_ids"]),
                    "reasons": list(dict.fromkeys(bucket["reasons"]))[:8],
                }, ensure_ascii=False),
            ))
            for shot_id in sorted(bucket["shot_ids"]):
                bbox = bucket["bbox_by_shot"].get(shot_id)
                bbox_json = json.dumps({
                    "format": "xyxy_norm",
                    "bbox": bbox,
                    "provider": "Qwen3-VL",
                    "profile": GUIDANCE_PROFILE,
                }, ensure_ascii=False) if bbox is not None else None
                session.add(ShotPropEvidence(
                    id=new_id("SHOT_PROP"),
                    run_id=run_id,
                    shot_id=shot_id,
                    prop_candidate_id=candidate_id,
                    confidence=confidence,
                    bbox_json=bbox_json,
                ))
            prop_count += 1

        component_status = json.loads(run.component_status_json or "{}")
        component_status["breakdown_guidance"] = "READY"
        component_status["scene_semantics"] = "READY" if scene_values else "NO_SCENE_SEMANTICS"
        component_status["props"] = "READY" if prop_count else "NO_PROP"
        if failures:
            component_status["p4_semantic_verification"] = "READY_WITH_WARNINGS"
        else:
            component_status["p4_semantic_verification"] = "READY"
        run.component_status_json = json.dumps(component_status, ensure_ascii=False)

        counts = json.loads(run.counts_json or "{}")
        counts["prop_candidates"] = prop_count
        counts["vlm_analyzed_shots"] = len(shot_semantics)
        counts["p4_guided_shots"] = guidance.guided_shot_count
        counts["p4_guided_prop_targets"] = guidance.prop_target_count
        counts["p4_semantic_failures"] = len(failures)
        run.counts_json = json.dumps(counts, ensure_ascii=False)

        if failures:
            run.status = "READY_WITH_WARNINGS"
        elif run.status == "READY_WITH_WARNINGS" and component_status.get("characters") in {"READY", "NO_CHARACTER"} and component_status.get("scenes") in {"READY", "NO_SCENE"}:
            run.status = "READY"
        session.commit()

    return {
        "status": "READY_WITH_WARNINGS" if failures else "READY",
        "prop_count": prop_count,
        "shot_count": len(shot_semantics),
        "guidance_profile": GUIDANCE_PROFILE,
        "guidance_status": "READY",
        "guided_shot_count": guidance.guided_shot_count,
        "guided_processed_shot_count": guided_processed,
        "guided_prop_target_count": guidance.prop_target_count,
        "breakdown_run_ids": list(guidance.breakdown_run_ids),
        "skipped_episode_ids": list(guidance.skipped_episode_ids),
        "warnings": list(guidance.warnings) + failures,
    }
