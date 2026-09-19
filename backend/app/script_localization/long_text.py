"""Deterministic, lossless source segmentation for bounded text-model requests.

Chunk boundaries are character offsets in the *immutable* source; no overlap, skipping,
stripping or silent truncation. Output coverage is validated separately before publish.
"""

import hashlib
from dataclasses import dataclass

from app.core.errors import AppError

# Product limits, NOT claims about any provider's context window.
CHUNK_CHARS = 4_000
MAX_LONG_CHARS = 200_000
MAX_CHUNKS = 64
CHUNK_CONTRACT_VERSION = "script-source-spans-v1"


@dataclass(frozen=True)
class SourceChunk:
    index: int
    start: int
    end: int
    text: str

    def manifest(self) -> dict:
        return {
            "index": self.index,
            "start": self.start,
            "end": self.end,
            "source_sha256": hashlib.sha256(self.text.encode("utf-8")).hexdigest(),
        }


def split_source(text: str, *, max_chars: int = CHUNK_CHARS) -> list[SourceChunk]:
    if not text or not text.strip():
        raise AppError("SCRIPT_LOCALIZATION_SOURCE_EMPTY", "原剧本不能为空", status_code=422)
    if max_chars < 100 or max_chars > CHUNK_CHARS:
        raise ValueError("max_chars must be between 100 and CHUNK_CHARS")
    if len(text) > MAX_LONG_CHARS:
        raise AppError(
            "SCRIPT_LOCALIZATION_SOURCE_TOO_LONG",
            f"当前长文本生产链最多处理 {MAX_LONG_CHARS} 字符；请按集/章拆成多个文档处理，绝不截断原文",
            status_code=422,
        )
    chunks: list[SourceChunk] = []
    start = 0
    while start < len(text):
        limit = min(start + max_chars, len(text))
        end = limit
        if limit < len(text):
            # Prefer whole scenes/paragraphs; unusually long paragraphs split exactly
            # at the limit rather than dropping any source characters.
            for sep in ("\n\n", "\n"):
                boundary = text.rfind(sep, start + max_chars // 2, limit)
                if boundary >= 0:
                    end = boundary + len(sep)
                    break
        chunks.append(SourceChunk(len(chunks) + 1, start, end, text[start:end]))
        start = end
    assert "".join(part.text for part in chunks) == text
    if len(chunks) > MAX_CHUNKS:
        raise AppError("SCRIPT_LOCALIZATION_CHUNKS_EXCEEDED", "剧本分段数量超过当前安全处理上限，请按集拆分", status_code=422)
    return chunks


def assert_complete(chunks: list[SourceChunk], *, original: str, results: list[dict]) -> None:
    if not chunks or len(chunks) != len(results):
        raise AppError("SCRIPT_LOCALIZATION_CHUNK_INCOMPLETE", "模型生成分段数量不足，禁止发布不完整剧本", status_code=422)
    offset = 0
    for part, item in zip(chunks, results, strict=True):
        if part.start != offset or part.end != part.start + len(part.text):
            raise AppError("SCRIPT_LOCALIZATION_CHUNK_GAP", "原剧本分段存在缺口或重复", status_code=422)
        if item.get("chunk_index") != part.index or item.get("source_sha256") != part.manifest()["source_sha256"]:
            raise AppError("SCRIPT_LOCALIZATION_CHUNK_MISMATCH", "模型输出与原剧本分段不对应", status_code=422)
        if not str(item.get("text") or "").strip():
            raise AppError("SCRIPT_LOCALIZATION_CHUNK_EMPTY", "模型生成了空剧本分段，禁止发布", status_code=422)
        offset = part.end
    if offset != len(original) or "".join(part.text for part in chunks) != original:
        raise AppError("SCRIPT_LOCALIZATION_CHUNK_GAP", "原剧本没有被完整覆盖，禁止发布", status_code=422)
