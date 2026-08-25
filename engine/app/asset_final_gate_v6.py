"""Character V6 -> Final Asset Gate。

职责：
- 不修改不可变 CharacterCandidate / CharacterTrack Evidence；
- 读取 CharacterCandidate.evidence_json.identity_status；
- 只有 RESOLVED Candidate 能进入 legacy Final Asset materialization；
- UNRESOLVED Candidate 继续保留真实 face_visible / bbox / samples，但不产生 Final Character。

为什么：旧 _rebuild_from_analysis 的门槛是“Candidate 里只要有任意 face_visible Track 就创建 Character”，
这会把孤立脸/碎片直接变成“人物020”。V6 必须把 Evidence 与 Final Character 彻底分开。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from engine.app import asset_workspace_v3 as legacy
from engine.app.content_analysis_v2 import CharacterCandidate, CharacterTrack

_original_rebuild = legacy._rebuild_from_analysis


def _v6_rebuild_from_analysis(session: Any, project_id: str, run_id: str) -> None:
    candidates = list(session.scalars(
        select(CharacterCandidate).where(CharacterCandidate.run_id == run_id)
    ).all())
    unresolved_candidate_ids: set[str] = set()
    for candidate in candidates:
        try:
            evidence = json.loads(candidate.evidence_json or "{}")
        except json.JSONDecodeError:
            evidence = {}
        if evidence.get("identity_status") == "UNRESOLVED":
            unresolved_candidate_ids.add(candidate.id)

    if not unresolved_candidate_ids:
        _original_rebuild(session, project_id, run_id)
        return

    tracks = list(session.scalars(
        select(CharacterTrack).where(
            CharacterTrack.run_id == run_id,
            CharacterTrack.candidate_id.in_(unresolved_candidate_ids),
        )
    ).all())
    original_face_visible = {track.id: bool(track.face_visible) for track in tracks}

    # legacy materializer 只认 face_visible。这里仅在同一个 Session 的 materialization 窗口里把
    # UNRESOLVED Track 暂时视为不可发布；finally 会恢复 Evidence 的真实 face_visible。
    try:
        for track in tracks:
            track.face_visible = False
        _original_rebuild(session, project_id, run_id)
    finally:
        for track in tracks:
            track.face_visible = original_face_visible.get(track.id, track.face_visible)


# patch legacy module global：apply_analysis_to_assets() 运行时会解析这个变量。
legacy._rebuild_from_analysis = _v6_rebuild_from_analysis


def apply_analysis_to_assets(project_id: str, run_id: str, *, force: bool = False) -> dict[str, Any]:
    return legacy.apply_analysis_to_assets(project_id, run_id, force=force)
