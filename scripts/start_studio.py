#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

from studio_windows_lifecycle import WindowsStudioLifetimeGuard, cleanup_repo_services

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
IS_WINDOWS = os.name == "nt"
BACKEND_HEALTH_URL = "http://127.0.0.1:8000/api/v3/health"
FRONTEND_URL = "http://127.0.0.1:5173"
LAUNCHER_PID_FILE = REPO_ROOT / ".runtime" / "studio-launcher.pid"


def _http_ok(url: str, timeout: float = 1.5) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.status < 400
    except (OSError, URLError, TimeoutError):
        return False


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(args: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=str(cwd) if cwd else None, check=True)


def _backend_python() -> Path:
    if sys.version_info < (3, 12):
        raise RuntimeError("AI Drama Studio backend requires Python 3.12+. Run start.cmd with Python 3.12+.")
    venv = REPO_ROOT / ".venv"
    python = venv / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
    if not python.exists():
        print("[Studio] creating backend virtual environment...")
        _run([sys.executable, "-m", "venv", str(venv)])

    marker = venv / ".ai_drama_backend_hash"
    wanted = _sha256(BACKEND_DIR / "pyproject.toml")
    current = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    if current != wanted:
        print("[Studio] installing/updating backend dependencies...")
        _run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
        _run([str(python), "-m", "pip", "install", "-e", "backend[dev]"], cwd=REPO_ROOT)
        marker.write_text(wanted, encoding="utf-8")
    return python


def _ensure_frontend() -> str:
    node = shutil.which("node")
    npm = shutil.which("npm.cmd" if IS_WINDOWS else "npm") or shutil.which("npm")
    if not node or not npm:
        raise RuntimeError("Node.js/npm not found. AI Drama Studio requires Node.js 22+.")
    version = subprocess.check_output([node, "--version"], text=True).strip().lstrip("v")
    try:
        major = int(version.split(".", 1)[0])
    except ValueError as exc:
        raise RuntimeError(f"Cannot parse Node.js version: {version}") from exc
    if major < 22:
        raise RuntimeError(f"Node.js 22+ is required; found {version}")

    marker = FRONTEND_DIR / "node_modules" / ".ai_drama_package_hash"
    wanted = _sha256(FRONTEND_DIR / "package.json")
    current = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    if current != wanted:
        print("[Studio] installing/updating frontend dependencies...")
        _run([npm, "install"], cwd=FRONTEND_DIR)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(wanted, encoding="utf-8")
    return npm


def _popen(args: list[str], *, cwd: Path | None = None) -> subprocess.Popen:
    kwargs: dict = {"cwd": str(cwd) if cwd else None}
    if IS_WINDOWS:
        # The launcher itself is already inside a KILL_ON_JOB_CLOSE Job Object.
        # Descendants inherit that job automatically, so even closing the console
        # window kills the full backend/frontend process tree.
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    print("+", " ".join(args))
    return subprocess.Popen(args, **kwargs)


def _start_backend(python: Path) -> tuple[subprocess.Popen | None, bool]:
    if _http_ok(BACKEND_HEALTH_URL):
        if IS_WINDOWS:
            raise RuntimeError(
                "Port 8000 became active after Windows lifecycle cleanup. "
                "Studio will not reuse an unowned backend because it could survive launcher exit."
            )
        print("[Studio] backend already healthy; reusing it.")
        return None, False
    print("[Studio] applying database migrations...")
    _run([str(python), "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR)
    return _popen(
        [
            str(python), "-m", "uvicorn", "app.main:app",
            "--reload", "--reload-dir", "app", "--reload-delay", "0.5",
            "--host", "127.0.0.1", "--port", "8000",
        ],
        cwd=BACKEND_DIR,
    ), True


def _restart_backend(python: Path) -> subprocess.Popen:
    """Recover the development backend without tearing down Vite or the launcher.

    Uvicorn normally keeps its reload supervisor alive while replacing only the
    application worker. If that supervisor itself exits on Windows, keep the
    development session alive and recreate it after applying pending migrations.
    """
    print("[Studio] backend reload supervisor exited; restarting backend only...")
    process, owned = _start_backend(python)
    if process is None or not owned:
        raise RuntimeError("Backend restart did not create a managed process.")
    return process


def _start_frontend(npm: str) -> tuple[subprocess.Popen | None, bool]:
    if _http_ok(FRONTEND_URL):
        if IS_WINDOWS:
            raise RuntimeError(
                "Port 5173 became active after Windows lifecycle cleanup. "
                "Studio will not reuse an unowned frontend because it could survive launcher exit."
            )
        print("[Studio] frontend already running; reusing it.")
        return None, False
    return _popen([npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"], cwd=FRONTEND_DIR), True


def _terminate_tree(process: subprocess.Popen | None, owned: bool) -> None:
    if process is None or not owned or process.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except OSError:
        pass


def _write_launcher_pid() -> None:
    LAUNCHER_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAUNCHER_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def _clear_launcher_pid() -> None:
    try:
        if LAUNCHER_PID_FILE.exists() and LAUNCHER_PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            LAUNCHER_PID_FILE.unlink()
    except OSError:
        pass


def main() -> int:
    processes: list[tuple[str, subprocess.Popen | None, bool]] = []
    lifetime_guard: WindowsStudioLifetimeGuard | None = None
    try:
        if IS_WINDOWS:
            # Acquire single-instance ownership and join the launcher itself to a
            # KILL_ON_JOB_CLOSE Job Object before starting any child process.
            lifetime_guard = WindowsStudioLifetimeGuard(REPO_ROOT)
            _write_launcher_pid()

            # Older launcher versions could leave healthy-looking orphan
            # services behind. A new managed session must not reuse them,
            # otherwise closing this launcher could not guarantee cleanup.
            # This cleanup may also remove a legacy IndexTTS orphan from an old
            # launcher, but the current five-step product launcher never starts
            # or depends on IndexTTS. MiniMax H3 generates synchronized audio and
            # video natively during step 5.
            cleanup_repo_services(REPO_ROOT)

        python = _backend_python()
        npm = _ensure_frontend()

        backend, owned_backend = _start_backend(python)
        processes.append(("backend", backend, owned_backend))
        frontend, owned_frontend = _start_frontend(npm)
        processes.append(("frontend", frontend, owned_frontend))

        print("[Studio] waiting for web application...")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if _http_ok(BACKEND_HEALTH_URL) and _http_ok(FRONTEND_URL):
                break
            for name, proc, owned in processes:
                if owned and proc is not None and proc.poll() is not None:
                    raise RuntimeError(f"{name} exited during startup with code {proc.returncode}")
            time.sleep(1)
        else:
            raise RuntimeError("Backend/frontend did not become ready within 90 seconds.")

        print("[Studio] UI READY: http://127.0.0.1:5173")
        print("[Studio] Replica audio/video mode: MiniMax H3 native synchronized audio + video; IndexTTS is not started.")
        if IS_WINDOWS:
            print("[Studio] Windows lifecycle guard ACTIVE: closing this launcher will stop backend and frontend.")
        if os.getenv("AI_DRAMA_NO_BROWSER", "0") != "1":
            webbrowser.open(FRONTEND_URL)

        backend_restart_times: list[float] = []
        while True:
            for index, (name, proc, owned) in enumerate(processes):
                if not owned or proc is None or proc.poll() is None:
                    continue
                if name == "backend":
                    now = time.monotonic()
                    backend_restart_times = [value for value in backend_restart_times if now - value < 60]
                    if len(backend_restart_times) >= 5:
                        raise RuntimeError("backend exited more than 5 times within 60 seconds; fix the startup error before retrying")
                    backend_restart_times.append(now)
                    time.sleep(0.75)
                    replacement = _restart_backend(python)
                    processes[index] = ("backend", replacement, True)
                    continue
                raise RuntimeError(f"{name} exited unexpectedly with code {proc.returncode}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Studio] stopping managed processes...")
        return 0
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        for _name, process, owned in reversed(processes):
            _terminate_tree(process, owned)
        _clear_launcher_pid()
        # Keep lifetime_guard referenced until process teardown. On Windows the
        # OS closes its Job Object handle as this process exits and kills any
        # descendant that escaped the explicit best-effort cleanup above.
        _ = lifetime_guard


if __name__ == "__main__":
    raise SystemExit(main())
