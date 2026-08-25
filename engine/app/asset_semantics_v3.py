"""03 资产：可选本地 Qwen3-VL 语义增强。

职责：
- 不负责人物身份；人物身份仍由 Face/SFace + Body/服装 Evidence 提供。
- 通过 OpenAI-compatible 本地 VLM 服务读取 Shot 缩略图，补充场景语义和关键道具。
- VLM 未配置时明确返回 NOT_CONFIGURED，不伪造道具，也不阻塞人物/场景基础 Evidence。

配置示例：
AI_DRAMA_VLM_BASE_URL=http://127.0.0.1:8001/v1
AI_DRAMA_VLM_MODEL=Qwen3-VL-4B-Instruct
AI_DRAMA_VLM_API_KEY=EMPTY
"""
from __future__ import annotations

import base64
from collections import Counter
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Callable

import httpx
from sqlalchemy import delete, select

from engine.app.content_analysis_v2 import (
    ContentAnalysisRun,
    PropCandidate,
    SceneCandidate,
    ShotPropEvidence,
    ShotSceneEvidence,
)
from engine.app.studio_v2 import Episode, Shot, get_session, new_id

SemanticProgress = Callable[[int, int, str], None]


class AssetSemanticError(RuntimeError):
    """VLM 语义增强错误。"""


def semantic_model_status() -> dict[str, Any]:
    """返回本地 VLM 配置状态；这里只检查配置，不主动联网。"""

    base_url = os.getenv("AI_DRAMA_VLM_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("AI_DRAMA_VLM_MODEL", "").strip()
    return {
        "ready": bool(base_url and model),
        "provider": "openai-compatible",
        "base_url": base_url or None,
        "model": model or None,
        "configured": bool(base_url and model),
        "purpose": "Qwen3-VL 场景语义 / 关键道具",
    }


def _image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_json(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    if value.startswith("```"):
        value = value.strip("`")
        if value.lower().startswith("json"):
            value = value[4:].lstrip()
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise AssetSemanticError("VLM 没有返回 JSON")
    try:
        payload = json.loads(value[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AssetSemanticError("VLM JSON 解析失败") from exc
    return payload if isinstance(payload, dict) else {}


def _analyze_image(path: Path) -> dict[str, Any]:
    status = semantic_model_status()
    if not status["ready"]:
        raise AssetSemanticError("Qwen3-VL 本地服务未配置")

    base_url = str(status["base_url"])
    model = str(status["model"])
    api_key = os.getenv("AI_DRAMA_VLM_API_KEY", "EMPTY").strip() or "EMPTY"
    prompt = (
        "你正在分析短剧拉片中的单个 Shot。只返回 JSON，不要解释。"
        "scene_label 用简短中文描述可复用的拍摄空间，例如‘公寓走廊’‘客厅’‘办公室’，"
        "indoor_outdoor 只能是‘内’‘外’或‘未知’，time_of_day 只能是‘日’‘夜’或‘未知’。"
        "props 只列剧情重要、反复出现、或重制时需要保持一致的道具；不要把普通家具、墙、地板、衣服列为道具。"
        "格式：{\"scene_label\":\"\",\"indoor_outdoor\":\"\",\"time_of_day\":\"\","
        "\"props\":[{\"name\":\"\",\"confidence\":0.0,\"reason\":\"\"}]}。"
    )
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _image_data_url(path)}},
                ],
            }
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AssetSemanticError(f"Qwen3-VL 请求失败：{exc}") from exc
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AssetSemanticError("Qwen3-VL 返回结构不符合 OpenAI-compatible 格式") from exc
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return _extract_json(str(content))


def _norm_name(value: str) -> str:
    return "".join((value or "").strip().lower().split())


def enrich_asset_run(run_id: str, project_id: str, progress: SemanticProgress | None = None) -> dict[str, Any]:
    """用 Qwen3-VL 补 Scene label 和 Prop Evidence。

    输入：已经成功完成基础人物/场景 Evidence 的 run_id。
    输出：语义增强状态与数量。
    为什么：Scene/Prop 是容易语义判断错但又需要人工修的层，因此 VLM 只产生 Evidence，Final Asset 仍由资产工作台管理。
    """

    if not semantic_model_status()["ready"]:
        return {"status": "NOT_CONFIGURED", "prop_count": 0, "shot_count": 0}

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
        scene_links = list(session.scalars(select(ShotSceneEvidence).where(ShotSceneEvidence.run_id == run_id)).all())
        scene_id_by_shot = {item.shot_id: item.scene_candidate_id for item in scene_links}

    shot_semantics: dict[str, dict[str, Any]] = {}
    total = len(shots)
    for index, shot in enumerate(shots, start=1):
        if progress:
            progress(index, total, f"Qwen3-VL 正在分析 Shot {index} / {total}")
        path = Path(shot.thumbnail_path) if shot.thumbnail_path else None
        if path is None or not path.is_file():
            continue
        shot_semantics[shot.id] = _analyze_image(path)

    scene_labels: dict[str, list[tuple[str, str, str]]] = {}
    prop_bucket: dict[str, dict[str, Any]] = {}
    for shot in shots:
        result = shot_semantics.get(shot.id) or {}
        scene_id = scene_id_by_shot.get(shot.id)
        if scene_id:
            label = str(result.get("scene_label") or "").strip()
            io = str(result.get("indoor_outdoor") or "未知").strip()
            tod = str(result.get("time_of_day") or "未知").strip()
            if label:
                scene_labels.setdefault(scene_id, []).append((label, io, tod))
        raw_props = result.get("props")
        if not isinstance(raw_props, list):
            continue
        for raw in raw_props[:6]:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            key = _norm_name(name)
            if not key:
                continue
            try:
                confidence = float(raw.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < 0.45:
                continue
            bucket = prop_bucket.setdefault(key, {"name": name, "scores": [], "shot_ids": set(), "reasons": []})
            bucket["scores"].append(confidence)
            bucket["shot_ids"].add(shot.id)
            reason = str(raw.get("reason") or "").strip()
            if reason:
                bucket["reasons"].append(reason)

    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None:
            raise LookupError("资产分析 Run 不存在")

        for scene_id, values in scene_labels.items():
            scene = session.get(SceneCandidate, scene_id)
            if scene is None:
                continue
            names = [value[0] for value in values]
            label = Counter(names).most_common(1)[0][0]
            matching = [value for value in values if value[0] == label]
            io = Counter(value[1] for value in matching).most_common(1)[0][0]
            tod = Counter(value[2] for value in matching).most_common(1)[0][0]
            suffix = " / ".join(value for value in (io, tod) if value and value != "未知")
            scene.auto_label = f"{label} · {suffix}" if suffix else label
            evidence = json.loads(scene.evidence_json or "{}")
            evidence["vlm"] = {"provider": "Qwen3-VL", "scene_label": label, "indoor_outdoor": io, "time_of_day": tod}
            scene.evidence_json = json.dumps(evidence, ensure_ascii=False)

        session.execute(delete(ShotPropEvidence).where(ShotPropEvidence.run_id == run_id))
        session.execute(delete(PropCandidate).where(PropCandidate.run_id == run_id))
        prop_count = 0
        for ordinal, bucket in enumerate(sorted(prop_bucket.values(), key=lambda item: (-len(item["shot_ids"]), item["name"])), start=1):
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
                    "shot_count": len(bucket["shot_ids"]),
                    "reasons": list(dict.fromkeys(bucket["reasons"]))[:5],
                }, ensure_ascii=False),
            ))
            for shot_id in bucket["shot_ids"]:
                session.add(ShotPropEvidence(
                    id=new_id("SHOT_PROP"), run_id=run_id, shot_id=shot_id,
                    prop_candidate_id=candidate_id, confidence=confidence, bbox_json=None,
                ))
            prop_count += 1

        component_status = json.loads(run.component_status_json or "{}")
        component_status["scene_semantics"] = "READY" if scene_labels else "NO_SCENE_SEMANTICS"
        component_status["props"] = "READY" if prop_count else "NO_PROP"
        run.component_status_json = json.dumps(component_status, ensure_ascii=False)
        counts = json.loads(run.counts_json or "{}")
        counts["prop_candidates"] = prop_count
        counts["vlm_analyzed_shots"] = len(shot_semantics)
        run.counts_json = json.dumps(counts, ensure_ascii=False)
        if run.status == "READY_WITH_WARNINGS" and component_status.get("characters") in {"READY", "NO_CHARACTER"} and component_status.get("scenes") in {"READY", "NO_SCENE"}:
            run.status = "READY"
        session.commit()

    return {"status": "READY", "prop_count": prop_count, "shot_count": len(shot_semantics)}
