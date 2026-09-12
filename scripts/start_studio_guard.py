#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_APP_ROOT = REPO_ROOT / "backend" / "app"
BACKEND_HEALTH_URL = "http://127.0.0.1:8000/api/v3/health"
IS_WINDOWS = os.name == "nt"


def _source_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted(
        BACKEND_APP_ROOT.rglob("*.py"),
        key=lambda item: item.relative_to(BACKEND_APP_ROOT).as_posix(),
    ):
        relative = path.relative_to(BACKEND_APP_ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _health_payload() -> dict | None:
    try:
        with urlopen(
            Request(BACKEND_HEALTH_URL, headers={"Accept": "application/json"}),
            timeout=1.5,
        ) as response:
            if response.status >= 400:
                return None
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return None


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _stop_stale_backend() -> None:
    print("[Studio] backend is healthy but belongs to an older source snapshot; replacing it...")
    if IS_WINDOWS:
        command = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { "
            "$_.CommandLine -and "
            "$_.CommandLine -match 'app\\.main:app' -and "
            "$_.CommandLine -match '--port\\s+8000' "
            "} | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        subprocess.run(
            ["bash", "-lc", "pkill -f 'app\\.main:app.*--port 8000' || true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    deadline = time.monotonic() + 6
    while time.monotonic() < deadline and _port_open(8000):
        time.sleep(0.25)
    if _port_open(8000):
        raise RuntimeError(
            "Port 8000 is still occupied after stale-backend cleanup. "
            "Stop the old backend process manually, then run start.cmd/start.sh again."
        )


def main() -> int:
    wanted = _source_fingerprint()
    payload = _health_payload()

    if payload is not None:
        running = str(payload.get("runtime_fingerprint") or "")
        if running == wanted:
            print(f"[Studio] backend runtime matches current source ({wanted[:12]}).")
        else:
            _stop_stale_backend()
    elif _port_open(8000):
        raise RuntimeError(
            "Port 8000 is occupied by a process that is not a readable AI Drama Studio backend. "
            "Stop that process before starting Studio."
        )

    launcher = REPO_ROOT / "scripts" / "start_studio.py"
    return subprocess.call([sys.executable, str(launcher), *sys.argv[1:]], cwd=str(REPO_ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
