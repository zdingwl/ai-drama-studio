from enum import StrEnum


class ArtifactNamespace(StrEnum):
    SOURCE = "SOURCE"
    TARGET = "TARGET"
    PRODUCTION = "PRODUCTION"


class ArtifactValidity(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"


class ArtifactRelationType(StrEnum):
    DERIVED_FROM = "DERIVED_FROM"
    CONTAINS = "CONTAINS"
    USES = "USES"
    SUPERSEDES = "SUPERSEDES"
