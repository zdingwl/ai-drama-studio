from enum import StrEnum


class SourceAssetKind(StrEnum):
    VIDEO = "VIDEO"
    TEXT = "TEXT"


class SourceDocumentFormat(StrEnum):
    TXT = "TXT"
    MARKDOWN = "MARKDOWN"
