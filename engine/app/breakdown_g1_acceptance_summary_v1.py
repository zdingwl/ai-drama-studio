"""Human-readable terminal summary for G1 real-acceptance diagnostics.

This module formats diagnostic evidence only. It intentionally does not decide G1/P2.6 PASS because
Scene boundaries and anonymous continuity still require human review.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, (list, tuple)) else ()


def _fmt_time_us(value: Any) -> str:
    try:
        total_ms = max(0, int(value) // 1000)
    except (TypeError, ValueError):
        return "?"
    minutes, rem_ms = divmod(total_ms, 60_000)
    seconds, millis = divmod(rem_ms, 1000)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def _fmt_bool(value: Any) -> str:
    return "YES" if bool(value) else "NO"


def _clean(value: Any, *, fallback: str = "-", max_len: int = 180) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return fallback
    return text[:max_len]


def _labels_from_members(members: Sequence[Any]) -> list[str]:
    result: list[str] = []
    for raw in members:
        item = _mapping(raw)
        label = _clean(item.get("source_label"), fallback="", max_len=80)
        if label and label not in result:
            result.append(label)
    return result


def build_g1_console_summary(snapshot: Mapping[str, Any]) -> str:
    run = _mapping(snapshot.get("run"))
    selection = _mapping(snapshot.get("selection"))
    vlm_profile = _mapping(selection.get("vlm_profile"))
    runtime = _mapping(snapshot.get("runtime"))
    targets = _mapping(runtime.get("targets"))
    shot_0001 = _mapping(snapshot.get("shot_0001"))
    scenes = list(_sequence(snapshot.get("scenes")))
    scene_04 = _mapping(snapshot.get("scene_04_focus"))
    conflicts = list(_sequence(snapshot.get("same_shot_cluster_conflicts")))
    ocr = _mapping(snapshot.get("ocr_record_only"))

    selected_run_id = selection.get("run_id") or run.get("run_id") or "-"
    episode_id = selection.get("episode_id") or run.get("episode_id") or "-"
    profile = vlm_profile.get("production_vlm_profile") or "-"
    fast_grounded = vlm_profile.get("is_fast_grounded")

    elapsed_minutes = runtime.get("total_elapsed_minutes")
    elapsed_text = f"{float(elapsed_minutes):.3f} min" if isinstance(elapsed_minutes, (int, float)) else "unknown"

    lines = [
        "=== G1 Fast Grounded 真实验收摘要（机器诊断，不自动 PASS）===",
        f"Run: {selected_run_id}",
        f"Episode: {episode_id}",
        f"VLM profile: {profile} | Fast Grounded={_fmt_bool(fast_grounded)}",
        (
            "Runtime: "
            f"{elapsed_text} | <30min={_fmt_bool(targets.get('under_30_minutes'))} "
            f"| <=20min={_fmt_bool(targets.get('at_or_below_20_minutes'))}"
        ),
    ]

    provider_timings = _mapping(runtime.get("provider_timings_seconds"))
    if provider_timings:
        timing_parts = [
            f"{name}={float(value):.1f}s"
            for name, value in provider_timings.items()
            if isinstance(value, (int, float))
        ]
        if timing_parts:
            lines.append("Providers: " + " | ".join(timing_parts))

    if shot_0001:
        props = ", ".join(str(item) for item in _sequence(shot_0001.get("prop_labels"))) or "-"
        lines.extend([
            "",
            "[Shot 0001]",
            (
                f"subjects={shot_0001.get('subject_count', '?')} | props={props} | "
                f"{_fmt_time_us(shot_0001.get('source_start_us'))}–"
                f"{_fmt_time_us(shot_0001.get('source_end_us'))}"
            ),
            "summary: " + _clean(shot_0001.get("summary")),
            "visual: " + _clean(shot_0001.get("visual_description")),
        ])

    lines.extend(["", f"[Scenes] total={snapshot.get('scene_count', len(scenes))}"])
    for raw_scene in scenes:
        scene = _mapping(raw_scene)
        ordinal = scene.get("ordinal", "?")
        lines.append(
            "Scene "
            f"{ordinal}: {_fmt_time_us(scene.get('source_start_us'))}–{_fmt_time_us(scene.get('source_end_us'))} "
            f"| shots={scene.get('shot_count', '?')} "
            f"| LocalSubjects={scene.get('local_subject_count', '?')} "
            f"| location={_clean(scene.get('location_hint'), max_len=80)} "
            f"| {scene.get('interior_exterior') or 'UNKNOWN'} / {scene.get('time_of_day') or 'UNKNOWN'}"
        )

    lines.extend([
        "",
        "[Scene 04 focus]",
        (
            f"present={_fmt_bool(scene_04.get('present'))} "
            f"| shots={scene_04.get('shot_count', '?')} "
            f"| LocalSubjects={scene_04.get('local_subject_count', '?')} "
            "| expected visible cast ≈ one woman + one man"
        ),
    ])

    scene_four_payload = next(
        (
            _mapping(raw_scene)
            for raw_scene in scenes
            if _mapping(raw_scene).get("ordinal") == 4
        ),
        {},
    )
    for raw_subject in _sequence(scene_four_payload.get("local_subjects")):
        subject = _mapping(raw_subject)
        members = list(_sequence(subject.get("source_members")))
        labels = _labels_from_members(members)
        ordinals = [
            str(item)
            for item in _sequence(subject.get("shot_ordinals"))
        ]
        lines.append(
            "  - "
            f"{_clean(subject.get('display_label'), max_len=80)} "
            f"| shots={','.join(ordinals) or '-'} "
            f"| source_labels={','.join(labels) or '-'} "
            f"| same-shot-conflicts={len(_sequence(subject.get('same_shot_conflicts')))}"
        )

    lines.extend([
        "",
        f"[Hard safety] same_shot_cluster_conflicts={len(conflicts)}",
    ])
    if conflicts:
        for raw_conflict in conflicts[:10]:
            conflict = _mapping(raw_conflict)
            labels = ",".join(str(item) for item in _sequence(conflict.get("source_labels"))) or "-"
            lines.append(
                "  ! "
                f"Scene {conflict.get('scene_ordinal', '?')} "
                f"Shot {conflict.get('shot_ordinal', '?')} "
                f"LocalSubject={conflict.get('display_label') or conflict.get('local_subject_id') or '?'} "
                f"labels={labels}"
            )

    short_ocr = [str(item) for item in _sequence(ocr.get("short_text_samples"))]
    lines.extend([
        "",
        f"[OCR record only] events={ocr.get('ocr_event_count', '?')} | short={', '.join(short_ocr) or '-'}",
        "",
        "Human review still required: Scene04 cluster meaning, Scene boundary correctness, and overall G1/P2.6 decision.",
    ])

    artifact_path = snapshot.get("artifact_path")
    if artifact_path:
        lines.append(f"JSON artifact: {artifact_path}")
    return "\n".join(lines)


__all__ = ["build_g1_console_summary"]
