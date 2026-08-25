"""Character V6 Evidence 持久化增强。

职责：
- 复用 content_analysis_v2 现有表与事务，不引入破坏性 schema migration；
- 在 CharacterCandidate.evidence_json 明确写 identity_status / V6 resolver metadata；
- RESOLVED 与 UNRESOLVED 使用不同 auto_label；
- ContentAnalysisRun.counts_json 同时记录 resolved / unresolved 数量；
- 不改变 Track Evidence：UNRESOLVED 仍完整保留 face_visible / bbox / samples。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from engine.app.content_analysis_v2 import CharacterCandidate, ContentAnalysisRun, _persist_results
from engine.app.studio_v2 import get_session

PROFILE_VERSION = "f05-assets-v6-global-identity"


def persist_results_v6(
    *,
    run_id: str,
    project_id: str,
    shots: list[dict[str, Any]],
    candidates: list[Any],
    scenes: list[Any],
    dialogues: list[dict[str, Any]],
    speaker_segments: list[dict[str, Any]],
    component_status: dict[str, str],
) -> None:
    """先走旧稳定持久化，再补 V6 身份语义。

    这样历史数据库和 API 不需要同步迁移；Final Asset Gate 只读取 evidence_json.identity_status。
    """

    _persist_results(
        run_id=run_id,
        project_id=project_id,
        shots=shots,
        candidates=candidates,
        scenes=scenes,
        dialogues=dialogues,
        speaker_segments=speaker_segments,
        component_status=component_status,
    )

    candidate_status = {
        candidate.id: str(getattr(candidate, "identity_status", "UNRESOLVED"))
        for candidate in candidates
    }
    candidate_metadata = {
        candidate.id: dict(getattr(candidate, "v6_metadata", {}) or {})
        for candidate in candidates
    }

    with get_session() as session:
        rows = list(session.scalars(
            select(CharacterCandidate)
            .where(CharacterCandidate.run_id == run_id)
            .order_by(CharacterCandidate.ordinal)
        ).all())
        resolved_ordinal = 0
        unresolved_ordinal = 0
        for row in rows:
            status = candidate_status.get(row.id, "UNRESOLVED")
            metadata = json.loads(row.evidence_json or "{}")
            metadata.update({
                "identity_status": status,
                "profile": PROFILE_VERSION,
                "identity": "Global Identity Graph; Face primary; CLEAN ReID temporal support",
                "final_asset_eligible": status == "RESOLVED",
            })
            metadata.update(candidate_metadata.get(row.id) or {})
            row.evidence_json = json.dumps(metadata, ensure_ascii=False)
            if status == "RESOLVED":
                resolved_ordinal += 1
                row.auto_label = f"人物 {resolved_ordinal:03d}"
            else:
                unresolved_ordinal += 1
                row.auto_label = f"待解析人物 {unresolved_ordinal:03d}"

        run = session.get(ContentAnalysisRun, run_id)
        if run is not None:
            counts = json.loads(run.counts_json or "{}")
            counts["resolved_character_candidates"] = resolved_ordinal
            counts["unresolved_character_candidates"] = unresolved_ordinal
            counts["character_candidates"] = len(rows)
            run.counts_json = json.dumps(counts, ensure_ascii=False)
            components = json.loads(run.component_status_json or "{}")
            components["characters_profile"] = "V6_GLOBAL_IDENTITY"
            components["resolved_characters"] = str(resolved_ordinal)
            components["unresolved_character_evidence"] = str(unresolved_ordinal)
            run.component_status_json = json.dumps(components, ensure_ascii=False)
            run.profile_version = PROFILE_VERSION
        session.commit()
