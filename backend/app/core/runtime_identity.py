from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.config import BACKEND_ROOT


def compute_backend_source_fingerprint(app_root: Path | None = None) -> str:
    """Hash backend Python source bytes in a stable path-aware order.

    The fingerprint is intentionally captured once at process import time below. A backend
    process that was started before a git pull therefore keeps its original fingerprint,
    allowing the unified launcher to detect and replace stale-but-healthy processes.
    """

    root = (app_root or (BACKEND_ROOT / "app")).resolve()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


BACKEND_RUNTIME_FINGERPRINT = compute_backend_source_fingerprint()
