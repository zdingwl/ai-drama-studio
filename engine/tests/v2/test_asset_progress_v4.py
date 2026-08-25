from __future__ import annotations

import engine.app.asset_analysis_progress_v4 as progress_v4


def test_asset_evidence_reports_character_shot_progress(monkeypatch) -> None:
    shots = [
        {
            "id": f"SHOT_{index}",
            "episode_id": "EP_1",
            "episode_order": 1,
            "ordinal": index,
            "start_us": (index - 1) * 1_000_000,
            "end_us": index * 1_000_000,
            "duration_us": 1_000_000,
            "reference_path": "unused.mp4",
            "thumbnail_path": None,
        }
        for index in range(1, 5)
    ]

    monkeypatch.setattr(progress_v4, "_load_context", lambda _project_id: ({"id": "P1"}, [], shots))
    monkeypatch.setattr(progress_v4, "_create_run", lambda _project_id: "RUN_1")
    monkeypatch.setattr(progress_v4, "_cluster_scenes", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(progress_v4, "_persist_results", lambda **_kwargs: None)
    monkeypatch.setattr(progress_v4, "get_analysis_run", lambda _run_id: {"id": "RUN_1", "status": "READY"})

    def fake_characters(_shots, progress=None):
        assert progress is not None
        progress(1, 4, "人物识别：Shot 1 / 4")
        progress(2, 4, "人物识别：Shot 2 / 4")
        progress(4, 4, "人物识别：Shot 4 / 4")
        return []

    monkeypatch.setattr(progress_v4, "analyze_characters", fake_characters)

    events: list[tuple[float, str, str | None, int | None, int | None]] = []

    def capture(percent, stage_key, _stage_label, current_item, current_index, total_items, _message):
        events.append((percent, stage_key, current_item, current_index, total_items))

    result = progress_v4.run_content_analysis_with_progress("P1", progress=capture)

    assert result["id"] == "RUN_1"
    character_events = [item for item in events if item[1] == "characters"]
    assert [item[3] for item in character_events] == [1, 2, 4]
    assert all(item[4] == 4 for item in character_events)
    assert character_events[0][2] == "E01 · SHOT 0001"
    assert character_events[-1][2] == "E01 · SHOT 0004"
    assert 24.0 < character_events[0][0] < 25.0
    assert character_events[-1][0] == 82.0
    assert events[-1][0] == 100.0
    assert events[-1][1] == "evidence_ready"
