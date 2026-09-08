from pathlib import Path

from app.core.config import get_settings


def artifact_root() -> Path:
    root = get_settings().artifact_root
    root.mkdir(parents=True, exist_ok=True)
    return root
