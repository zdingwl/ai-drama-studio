import json
from types import SimpleNamespace

from app.understanding.evidence_reference_runtime import (
    P7_EVIDENCE_REF_ENCODING,
    _provider_evidence_payload,
    _replace_evidence_refs,
)


def test_provider_receives_short_refs_not_database_ids() -> None:
    dialogue_id = "dialogue-7b72cf3f-55c2-4c49-a9e7-long-id"
    visual_id = "visual-f40725b7-c313-43f8-b64b-long-id"
    context = SimpleNamespace(
        dialogue=[
            SimpleNamespace(
                id=dialogue_id,
                start_us=100_000,
                end_us=900_000,
                text="你终于来了。",
                language="zh",
            )
        ],
        visual_text=[
            SimpleNamespace(
                id=visual_id,
                start_us=120_000,
                end_us=850_000,
                text="三年前",
                confidence=0.98,
            )
        ],
    )

    payload, dialogue_map, visual_map = _provider_evidence_payload(context)

    assert payload["reference_encoding"] == P7_EVIDENCE_REF_ENCODING
    assert payload["dialogue"][0]["id"] == "D0001"
    assert payload["visual_text"][0]["id"] == "O0001"
    assert dialogue_map == {"D0001": dialogue_id}
    assert visual_map == {"O0001": visual_id}
    serialized = json.dumps(payload, ensure_ascii=False)
    assert dialogue_id not in serialized
    assert visual_id not in serialized


def test_short_refs_are_resolved_to_canonical_ids_and_unknown_refs_stay_invalid() -> None:
    dialogue_id = "dialogue-canonical-id"
    visual_id = "visual-canonical-id"
    value = {
        "timed_script": [
            {
                "dialogue_evidence_ids": ["D0001", "invented-dialogue"],
                "visual_text_evidence_ids": ["O0001"],
            }
        ],
        "nested_grounding": {
            "dialogue_evidence_ids": ["D0001"],
            "visual_text_evidence_ids": ["invented-ocr"],
        },
    }

    resolved = _replace_evidence_refs(
        value,
        {"D0001": dialogue_id},
        {"O0001": visual_id},
    )

    assert resolved["timed_script"][0]["dialogue_evidence_ids"] == [dialogue_id, "invented-dialogue"]
    assert resolved["timed_script"][0]["visual_text_evidence_ids"] == [visual_id]
    assert resolved["nested_grounding"]["dialogue_evidence_ids"] == [dialogue_id]
    assert resolved["nested_grounding"]["visual_text_evidence_ids"] == ["invented-ocr"]
