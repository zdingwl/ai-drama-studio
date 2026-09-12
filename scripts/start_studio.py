#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
import webbrowser

from studio_windows_lifecycle import WindowsStudioLifetimeGuard, cleanup_repo_services

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
IS_WINDOWS = os.name == "nt"
TTS_MODELS_URL = "http://127.0.0.1:8092/v1/models"
BACKEND_HEALTH_URL = "http://127.0.0.1:8000/api/v3/health"
FRONTEND_URL = "http://127.0.0.1:5173"
MODEL_ID = "IndexTeam/IndexTTS-2.5"
LAUNCHER_PID_FILE = REPO_ROOT / ".runtime" / "studio-launcher.pid"


def _http_json_text(url: str, timeout: float = 1.5) -> str | None:
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:
            if response.status >= 400:
                return None
            return response.read().decode("utf-8", errors="replace")
    except (OSError, URLError, TimeoutError):
        return None


def _http_ok(url: str, timeout: float = 1.5) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.status < 400
    except (OSError, URLError, TimeoutError):
        return False


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _tts_ready() -> bool:
    text = _http_json_text(TTS_MODELS_URL)
    return bool(text and MODEL_ID in text)


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
        # window kills the full backend/frontend/TTS process tree.
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    print("+", " ".join(args))
    return subprocess.Popen(args, **kwargs)


def _cleanup_stale_tts() -> None:
    if _tts_ready() or not _port_open(8092):
        return
    print("[Studio] port 8092 has a non-ready process; attempting one managed IndexTTS cleanup...")
    if IS_WINDOWS:
        command = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -and $_.CommandLine -match 'indextts25_native_server\\.py' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        pattern = "vllm serve .*IndexTTS-2.5.*--port 8092"
        subprocess.run(["bash", "-lc", f"pkill -f {shlex.quote(pattern)} || true"], check=False)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _port_open(8092):
        time.sleep(0.25)


def _start_tts() -> tuple[subprocess.Popen | None, bool]:
    if _tts_ready():
        print("[Studio] IndexTTS-2.5 already READY; reusing it.")
        return None, False
    _cleanup_stale_tts()
    if _port_open(8092):
        raise RuntimeError("Port 8092 is occupied by an unknown/non-ready process. Stop that process and run the unified launcher again.")

    if IS_WINDOWS:
        native = REPO_ROOT / "scripts" / "start_indextts2525_native_windows.ps1"
        print("[Studio] starting managed IndexTTS-2.5 natively on Windows (WSL is not required)...")
        return _popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(native)],
            cwd=REPO_ROOT,
        ), True

    print("[Studio] starting managed IndexTTS-2.5 vLLM-Omni sidecar...")
    return _popen([str(REPO_ROOT / "scripts" / "start_indextts25.sh")], cwd=REPO_ROOT), True


def _start_backend(python: Path) -> tuple[subprocess.Popen | None, bool]:
    if _http_ok(BACKEND_HEALTH_URL):
        print("[Studio] backend already healthy; reusing it.")
        return None, False
    print("[Studio] applying database migrations...")
    _run([str(python), "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR)
    return _popen(
        [str(python), "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"],
        cwd=BACKEND_DIR,
    ), True


def _start_frontend(npm: str) -> tuple[subprocess.Popen | None, bool]:
    if _http_ok(FRONTEND_URL):
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
            # Only processes whose executable/command line resolves to this
            # checkout are removed; unknown port owners fail closed.
            cleanup_repo_services(REPO_ROOT)

        python = _backend_python()
        npm = _ensure_frontend()

        tts, owned_tts = _start_tts()
        processes.append(("IndexTTS-2.5", tts, owned_tts))
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
        if _tts_ready():
            print("[Studio] IndexTTS-2.5 READY")
        else:
            print("[Studio] IndexTTS-2.5 is preparing in the same launcher; first run may install its isolated runtime and download a large model.")
        if IS_WINDOWS:
            print("[Studio] Windows lifecycle guard ACTIVE: closing this launcher will stop backend, frontend and IndexTTS.")
        if os.getenv("AI_DRAMA_NO_BROWSER", "0") != "1":
            webbrowser.open(FRONTEND_URL)

        while True:
            for name, proc, owned in processes:
                if owned and proc is not None and proc.poll() is not None:
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
