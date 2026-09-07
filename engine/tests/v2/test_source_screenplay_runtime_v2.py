from __future__ import annotations

import pytest

from engine.app import source_screenplay_runtime_v2 as runtime
from engine.app.source_story_skills_v1 import SourceStorySkillError
from engine.tests.v2.test_source_story_skills_v1 import _snapshot, _understanding


def _screenplay_plan(_prompt: str) -> dict[str, object]:
    return {
        "scenes": [{
            "scene_key": "SCENE_1",
            "blocks": [
                {
                    "kind": "ACTION",
                    "text": "女邻居站在院子里转头看向对方，神情从不满变得愤怒。",
                    "supporting_fact_refs": ["shot:SHOT_1", "shot:SHOT_2"],
                },
                {
                    "kind": "DIALOGUE",
                    "dialogue_group_id": "DIALOGUE_1",
                },
            ],
        }],
        "unresolved": [],
    }


def test_v2_merges_repeated_shot_descriptions_into_readable_screenplay_action() -> None:
    result = runtime.compile_source_screenplay_v2(
        _snapshot(),
        episode_understanding_provider=_understanding,
        screenplay_reconstruction_provider=_screenplay_plan,
    )

    text = result.screenplay.screenplay_text
    assert "女邻居站在院子里转头看向对方，神情从不满变得愤怒。" in text
    assert "女邻居站在院子里看向画外人物。" not in text
    assert "女邻居继续面向对方说话。" not in text
    assert text.count("你凭什么说是我偷的花？") == 1
    assert "你凭什么说是我\n" not in text
    assert result.screenplay.scenes[0].actions[0].source_refs == ["shot:SHOT_1", "shot:SHOT_2"]


def test_v2_screenplay_prompt_explicitly_forbids_shot_dump_and_dialogue_rewrite() -> None:
    prompts: list[str] = []

    def capture(prompt: str) -> dict[str, object]:
        prompts.append(prompt)
        return _screenplay_plan(prompt)

    runtime.compile_source_screenplay_v2(
        _snapshot(),
        episode_understanding_provider=_understanding,
        screenplay_reconstruction_provider=capture,
    )

    assert len(prompts) == 1
    assert "按 Scene 写，不按 Shot 逐条复读" in prompts[0]
    assert "不得生成、改写、缩写或补充任何对白正文" in prompts[0]
    assert "结果必须让用户明显感觉是在读“剧本”" in prompts[0]


def test_v2_rejects_action_without_current_source_ref() -> None:
    def unsafe(_prompt: str) -> dict[str, object]:
        payload = _screenplay_plan(_prompt)
        payload["scenes"][0]["blocks"][0]["supporting_fact_refs"] = ["shot:NOT_REAL"]  # type: ignore[index]
        return payload

    with pytest.raises(SourceStorySkillError, match="unknown source facts"):
        runtime.compile_source_screenplay_v2(
            _snapshot(),
            episode_understanding_provider=_understanding,
            screenplay_reconstruction_provider=unsafe,
        )


def test_v2_rejects_missing_canonical_dialogue() -> None:
    def unsafe(_prompt: str) -> dict[str, object]:
        return {
            "scenes": [{
                "scene_key": "SCENE_1",
                "blocks": [{
                    "kind": "ACTION",
                    "text": "女邻居转头看向对方。",
                    "supporting_fact_refs": ["shot:SHOT_1"],
                }],
            }],
            "unresolved": [],
        }

    with pytest.raises(SourceStorySkillError, match="every canonical dialogue exactly once"):
        runtime.compile_source_screenplay_v2(
            _snapshot(),
            episode_understanding_provider=_understanding,
            screenplay_reconstruction_provider=unsafe,
        )


def test_materialized_screenplay_read_is_missing_ready_then_stale(monkeypatch, tmp_path) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(runtime.studio_v2, "episode_dir", lambda _project_id, _episode_id: tmp_path)

    missing = runtime.read_source_screenplay_v1(snapshot)
    assert missing.state == "MISSING"
    assert missing.compilation is None

    compiled = runtime.compile_source_screenplay_v2(
        snapshot,
        episode_understanding_provider=_understanding,
        screenplay_reconstruction_provider=_screenplay_plan,
    )
    runtime.persist_source_screenplay_v1(snapshot, compiled)

    ready = runtime.read_source_screenplay_v1(snapshot)
    assert ready.state == "READY"
    assert ready.compilation is not None
    assert ready.compilation.output_fingerprint == compiled.output_fingerprint

    stale_snapshot = snapshot.model_copy(update={"source_fingerprint": "b" * 64})
    stale = runtime.read_source_screenplay_v1(stale_snapshot)
    assert stale.state == "STALE"
    assert stale.compilation is None
