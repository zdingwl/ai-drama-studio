from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return an aware UTC datetime. Persisted timestamps must use UTC."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)
