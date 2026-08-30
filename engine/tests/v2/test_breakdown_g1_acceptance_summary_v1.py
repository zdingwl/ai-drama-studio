from engine.app.breakdown_g1_acceptance_summary_v1 import build_g1_console_summary


def test_console_summary_surfaces_g1_acceptance_focus_without_auto_pass() -> None:
    snapshot = {
        "selection": {
            "run_id": "RUN_1",
            "episode_id": "EP_1",
            "vlm_profile": {
                "production_vlm_profile": "breakdown-p2-vlm-fast-grounded-v1",
                "is_fast_grounded": True,
            },
        },
        "runtime": {
            "total_elapsed_minutes": 18.5,
            "provider_timings_seconds": {"ASR": 120.0, "OCR": 40.0, "VLM": 850.0},
            "targets": {"under_30_minutes": True, "at_or_below_20_minutes": True},
        },
        "shot_0001": {
            "source_start_us": 0,
            "source_end_us": 900_000,
            "summary": "蓝色玫瑰插在玻璃花瓶中。",
            "visual_description": "画面只有蓝色玫瑰与透明玻璃花瓶。",
            "subject_count": 0,
            "prop_labels": ["蓝色玫瑰", "玻璃花瓶"],
        },
        "scene_count": 4,
        "scenes": [
            {
                "ordinal": 4,
                "source_start_us": 20_000_000,
                "source_end_us": 60_000_000,
                "shot_count": 18,
                "local_subject_count": 2,
                "location_hint": "客厅",
                "interior_exterior": "INTERIOR",
                "time_of_day": "DAY",
                "local_subjects": [
                    {
                        "display_label": "人物A",
                        "shot_ordinals": [13, 15, 17],
                        "source_members": [
                            {"source_label": "subject_A"},
                            {"source_label": "subject_B"},
                        ],
                        "same_shot_conflicts": [],
                    },
                    {
                        "display_label": "人物B",
                        "shot_ordinals": [14, 16, 18],
                        "source_members": [
                            {"source_label": "subject_B"},
                            {"source_label": "subject_A"},
                        ],
                        "same_shot_conflicts": [],
                    },
                ],
            }
        ],
        "scene_04_focus": {
            "present": True,
            "shot_count": 18,
            "local_subject_count": 2,
        },
        "same_shot_cluster_conflicts": [],
        "ocr_record_only": {
            "ocr_event_count": 8,
            "short_text_samples": ["人", "人民", "副", "V"],
        },
        "artifact_path": "x/g1.json",
    }

    text = build_g1_console_summary(snapshot)

    assert "Runtime: 18.500 min" in text
    assert "subjects=0" in text
    assert "Scene 04 focus" in text
    assert "LocalSubjects=2" in text
    assert "source_labels=subject_A,subject_B" in text
    assert "same_shot_cluster_conflicts=0" in text
    assert "人, 人民, 副, V" in text
    assert "不自动 PASS" in text
    assert "Human review still required" in text
