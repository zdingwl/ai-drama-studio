"""Read-only selector for Fast Grounded G1 acceptance diagnostics.

The selector never starts or mutates a BreakdownRun. It only resolves an already-completed
Fast Grounded Run so the acceptance CLI can be used without manually hunting for a run id.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping, Sequence

from sqlalchemy import select

from engine.app import studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun

FAST_GROUNDED_PROFILE = "breakdown-p2-vlm-fast-grounded-v1"
READY_RUN_STATUSES = ("READY", "READY_WITH_WARNINGS")


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _vlm_profile_snapshot(run: Any) -> dict[str, Any]:
    providers = _json_object(getattr(run, "provider_metadata_json", None))
    sidecar = providers.get("p2_sidecar") if isinstance(providers.get("p2_sidecar"), Mapping) else {}
    vlm = sidecar.get("VLM") if isinstance(sidecar.get("VLM"), Mapping) else {}
    metadata = vlm.get("metadata") if isinstance(vlm.get("metadata"), Mapping) else {}
    profile = str(metadata.get("production_vlm_profile") or "").strip() or None
    return {
        "provider": str(vlm.get("provider") or "").strip() or None,
        "model": str(vlm.get("model") or "").strip() or None,
        "production_vlm_profile": profile,
        "fast_grounded_schema": str(metadata.get("fast_grounded_schema") or "").strip() or None,
        "exact_shot_grounding_profile": str(
            metadata.get("exact_shot_grounding_profile") or ""
        ).strip() or None,
        "visual_truth_policy": str(metadata.get("visual_truth_policy") or "").strip() or None,
        "is_fast_grounded": profile == FAST_GROUNDED_PROFILE,
    }


def _is_fast_grounded_run(run: Any) -> bool:
    return bool(_vlm_profile_snapshot(run)["is_fast_grounded"])


def _choose_fast_grounded_candidate(
    candidates: Sequence[Any],
    *,
    prefer_current: bool,
) -> Any | None:
    """Choose from candidates already ordered newest-first."""

    fast_grounded = [item for item in candidates if _is_fast_grounded_run(item)]
    if not fast_grounded:
        return None
    if prefer_current:
        current = [item for item in fast_grounded if bool(getattr(item, "is_current", False))]
        if current:
            return current[0]
    return fast_grounded[0]


@dataclass(frozen=True)
class G1RunSelection:
    run_id: str
    selection_mode: str
    project_id: str
    episode_id: str
    status: str
    is_current: bool
    started_at: str | None
    completed_at: str | None
    vlm_profile: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _selection(run: BreakdownRun, mode: str) -> G1RunSelection:
    return G1RunSelection(
        run_id=run.id,
        selection_mode=mode,
        project_id=run.project_id,
        episode_id=run.episode_id,
        status=run.status,
        is_current=bool(run.is_current),
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        vlm_profile=_vlm_profile_snapshot(run),
    )


def resolve_g1_run_selection(
    *,
    run_id: str | None = None,
    episode_id: str | None = None,
    latest: bool = False,
) -> G1RunSelection:
    """Resolve exactly one completed Fast Grounded Run for read-only G1 diagnostics.

    Modes:
    - explicit run id: inspect that exact Run, but refuse non-Fast-Grounded/unfinished Runs;
    - episode id: prefer that Episode's current READY-like Fast Grounded Run, then newest fallback;
    - latest: choose the newest completed READY-like Fast Grounded Run in the local database.
    """

    clean_run_id = str(run_id or "").strip()
    clean_episode_id = str(episode_id or "").strip()
    selector_count = int(bool(clean_run_id)) + int(bool(clean_episode_id)) + int(bool(latest))
    if selector_count != 1:
        raise ValueError("必须且只能指定 --run-id / --episode-id / --latest 其中一个")

    with studio_v2.get_session() as session:
        if clean_run_id:
            run = session.get(BreakdownRun, clean_run_id)
            if run is None:
                raise LookupError("Breakdown Run 不存在")
            if run.status not in READY_RUN_STATUSES or run.completed_at is None:
                raise ValueError(
                    f"Breakdown Run 尚未完成可验收：status={run.status}"
                )
            if not _is_fast_grounded_run(run):
                raise ValueError(
                    "该 Run 不是 Fast Grounded V2 生产结果，拒绝用于 G1 真实验收"
                )
            return _selection(run, "run_id")

        statement = select(BreakdownRun).where(
            BreakdownRun.status.in_(READY_RUN_STATUSES),
            BreakdownRun.completed_at.is_not(None),
        )
        if clean_episode_id:
            statement = statement.where(BreakdownRun.episode_id == clean_episode_id)
        statement = statement.order_by(
            BreakdownRun.completed_at.desc(),
            BreakdownRun.started_at.desc(),
        ).limit(100)
        candidates = list(session.scalars(statement).all())
        run = _choose_fast_grounded_candidate(
            candidates,
            prefer_current=bool(clean_episode_id),
        )
        if run is None:
            scope = f"Episode {clean_episode_id}" if clean_episode_id else "本地数据库"
            raise LookupError(f"{scope} 未找到已完成的 Fast Grounded Breakdown Run")
        return _selection(run, "episode_id" if clean_episode_id else "latest")


__all__ = [
    "FAST_GROUNDED_PROFILE",
    "G1RunSelection",
    "READY_RUN_STATUSES",
    "resolve_g1_run_selection",
]
