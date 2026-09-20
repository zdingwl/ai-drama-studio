"""A paraphrased character quote may establish presence by exact name, not facts."""

import pytest

from app.core.errors import AppError
from app.script_localization.long_text import SourceChunk
from app.script_to_drama.grounding import normalize_world_evidence
from app.script_to_drama.schemas import WorldChunk
from app.script_to_drama.service import _merge_world


def _chunk(text: str) -> SourceChunk:
    return SourceChunk(index=1, start=0, end=len(text), text=text)


def _world(name: str, evidence: str, *, location_evidence: str = "洞穴") -> dict:
    return WorldChunk(
        characters=[{
            "name": name,
            "visual_description": "握拳、泪意发红",
            "source_evidence": evidence,
            "source_fact": "艾娃握拳，泪意发红",
        }],
        locations=[{
            "name": "洞穴", "visual_description": "石壁洞穴",
            "source_evidence": location_evidence,
        }],
    ).model_dump(mode="json")


def test_named_character_paraphrase_is_identity_only_and_needs_review() -> None:
    source = "内景·洞穴。艾娃慢慢走近石壁，然后擦掉眼泪。"
    world = _world("艾娃", "艾娃握拳，泪意发红！她想起前世的往事。")
    normalize_world_evidence(_chunk(source), world)
    assert world["characters"][0]["source_evidence"] == "艾娃"
    assert world["characters"][0]["source_fact"] == ""
    assert world["characters"][0]["source_evidence"] in source
    assert len(world["unresolved_decisions"]) == 1
    assert "人物「艾娃」" in world["unresolved_decisions"][0]
    assert "人工核对" in world["unresolved_decisions"][0]
    merged = _merge_world([{"chunk_index": 1, "semantic": world}])
    assert merged["characters"][0]["source_evidence"] == ["艾娃"]
    assert merged["characters"][0]["source_facts"] == []
    assert merged["unresolved_decisions"] == world["unresolved_decisions"]


@pytest.mark.parametrize("source,name,evidence", [
    ("内景·洞穴。艾莉擦掉眼泪。", "艾娃", "艾娃握拳，泪意发红"),
    ("内景·洞穴。艾娃擦掉眼泪。", "艾娃", "陌生女子握拳，泪意发红"),
    ("内景·洞穴。甲擦掉眼泪。", "甲", "甲握拳，泪意发红"),
])
def test_character_without_explicit_reliable_name_is_still_rejected(source, name, evidence) -> None:
    world = _world(name, evidence)
    with pytest.raises(AppError) as caught:
        normalize_world_evidence(_chunk(source), world)
    assert caught.value.code == "SCRIPT_TO_DRAMA_UNGROUNDED_WORLD"
    assert world["unresolved_decisions"] == []


def test_location_is_not_accepted_from_character_name_anchor() -> None:
    world = _world("艾娃", "艾娃擦掉眼泪。", location_evidence="地下宫殿")
    with pytest.raises(AppError) as caught:
        normalize_world_evidence(_chunk("艾娃擦掉眼泪。"), world)
    assert caught.value.code == "SCRIPT_TO_DRAMA_UNGROUNDED_WORLD"
    assert "场景「洞穴」" in caught.value.message


def test_literal_character_quote_needs_no_extra_review() -> None:
    world = _world("艾娃", "艾娃擦掉眼泪。")
    normalize_world_evidence(_chunk("内景·洞穴。艾娃擦掉眼泪。"), world)
    assert world["characters"][0]["source_evidence"] == "艾娃擦掉眼泪。"
    assert world["unresolved_decisions"] == []
