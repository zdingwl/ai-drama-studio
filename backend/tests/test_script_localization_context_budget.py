from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.script_localization.long_text import MAX_CHUNKS, MAX_LONG_CHARS, assert_complete, split_source
from app.script_localization.providers import _ark_text


def test_maximum_supported_source_is_lossless_even_with_many_newlines() -> None:
    source = ("场景甲\n\n" * (MAX_LONG_CHARS // len("场景甲\n\n")))
    source += "终" * (MAX_LONG_CHARS - len(source))
    chunks = split_source(source)
    assert len(chunks) <= MAX_CHUNKS
    assert chunks[-1].end == MAX_LONG_CHARS
    assert "".join(chunk.text for chunk in chunks) == source
    results = [{**chunk.manifest(), "chunk_index": chunk.index, "text": "已处理"} for chunk in chunks]
    assert_complete(chunks, original=source, results=results)


def test_ark_incomplete_status_never_treated_as_valid_json() -> None:
    with pytest.raises(AppError) as exc:
        _ark_text(SimpleNamespace(status="incomplete", output_text='{"script_text":"partial"}'))
    assert exc.value.code == "SCRIPT_LOCALIZATION_PROVIDER_INCOMPLETE"
