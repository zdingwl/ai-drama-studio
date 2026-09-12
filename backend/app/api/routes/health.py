from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.runtime_identity import BACKEND_RUNTIME_FINGERPRINT
from app.core.time import utc_now

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    service: str
    time: datetime
    timezone: str
    runtime_fingerprint: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        time=utc_now(),
        timezone=settings.timezone,
        runtime_fingerprint=BACKEND_RUNTIME_FINGERPRINT,
    )
