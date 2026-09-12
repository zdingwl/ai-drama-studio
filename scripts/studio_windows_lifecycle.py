from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

IS_WINDOWS = os.name == "nt"
ERROR_ALREADY_EXISTS = 183
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
BACKEND_HEALTH_URL = "http://127.0.0.1:8000/api/v3/health"


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


@dataclass(frozen=True)
class WindowsProcessInfo:
    process_id: int
    parent_process_id: int
    executable_path: str
    command_line: str


class WindowsStudioLifetimeGuard:
    """Own one Studio launcher and let Windows kill all descendants on exit.

    The launcher process itself is placed in a Job Object configured with
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE before any managed subprocess is
    started. Every normal descendant therefore inherits membership. If the
    console window is closed and Python never reaches a finally block, the OS
    closes the launcher's only job handle and terminates the whole job.
    """

    def __init__(self, repo_root: Path) -> None:
        if not IS_WINDOWS:
            raise RuntimeError("WindowsStudioLifetimeGuard is Windows-only")

        token = hashlib.sha256(str(repo_root.resolve()).casefold().encode("utf-8")).hexdigest()[:20]
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_api()

        mutex_name = f"Local\\AI_Drama_Studio_{token}"
        self._mutex = self._kernel32.CreateMutexW(None, False, mutex_name)
        if not self._mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            self._kernel32.CloseHandle(self._mutex)
            self._mutex = None
            raise RuntimeError(
                "AI Drama Studio is already running for this checkout. "
                "Use the existing launcher window, or run stop.cmd before starting again."
            )

        self._job = self._kernel32.CreateJobObjectW(None, None)
        if not self._job:
            error = ctypes.get_last_error()
            self._kernel32.CloseHandle(self._mutex)
            self._mutex = None
            raise ctypes.WinError(error)

        info = _JobObjectExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = self._kernel32.SetInformationJobObject(
            self._job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            error = ctypes.get_last_error()
            self._cleanup_handles()
            raise ctypes.WinError(error)

        ok = self._kernel32.AssignProcessToJobObject(
            self._job,
            self._kernel32.GetCurrentProcess(),
        )
        if not ok:
            error = ctypes.get_last_error()
            self._cleanup_handles()
            raise RuntimeError(
                "Windows could not place the Studio launcher in its managed Job Object "
                f"(WinError {error}). No services were started because lifecycle cleanup "
                "could not be guaranteed."
            )

    def _configure_api(self) -> None:
        self._kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self._kernel32.CreateMutexW.restype = wintypes.HANDLE
        self._kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self._kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self._kernel32.SetInformationJobObject.restype = wintypes.BOOL
        self._kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        self._kernel32.GetCurrentProcess.argtypes = []
        self._kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL

    def _cleanup_handles(self) -> None:
        if getattr(self, "_job", None):
            self._kernel32.CloseHandle(self._job)
            self._job = None
        if getattr(self, "_mutex", None):
            self._kernel32.CloseHandle(self._mutex)
            self._mutex = None

    # Do not explicitly close the job on normal shutdown. The launcher process
    # is itself a member of this job; closing the final handle would terminate
    # the current process immediately. Process teardown closes it safely and
    # Windows then kills any remaining descendants.


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _powershell_json(script: str) -> dict | None:
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    text = completed.stdout.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _http_json(url: str, *, timeout: float = 1.5) -> dict | None:
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=timeout) as response:
            if response.status >= 400:
                return None
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return None


def backend_source_fingerprint(repo_root: Path) -> str:
    """Match backend/app/core/runtime_identity.py without importing the backend."""
    app_root = (repo_root / "backend" / "app").resolve()
    digest = hashlib.sha256()
    for path in sorted(app_root.rglob("*.py"), key=lambda item: item.relative_to(app_root).as_posix()):
        relative = path.relative_to(app_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def backend_runtime_matches_checkout(repo_root: Path) -> bool:
    """Use the live backend's immutable startup fingerprint as checkout identity.

    uv-managed Python executables live outside the repository and a perfectly
    valid Studio backend command line may therefore contain no repo path at all.
    The health fingerprint is stronger evidence: it hashes the exact backend
    Python source snapshot captured when that server process started.
    """
    payload = _http_json(BACKEND_HEALTH_URL)
    if payload is None:
        return False
    running = str(payload.get("runtime_fingerprint") or "")
    return bool(payload.get("status") == "ok" and running and running == backend_source_fingerprint(repo_root))


def process_info(process_id: int) -> WindowsProcessInfo | None:
    if not IS_WINDOWS or process_id <= 0:
        return None
    payload = _powershell_json(
        "$p = Get-CimInstance Win32_Process -Filter \"ProcessId = %d\" -ErrorAction SilentlyContinue; "
        "if ($null -ne $p) { [PSCustomObject]@{ ProcessId=$p.ProcessId; ParentProcessId=$p.ParentProcessId; "
        "ExecutablePath=$p.ExecutablePath; CommandLine=$p.CommandLine } | ConvertTo-Json -Compress }" % process_id
    )
    if not payload:
        return None
    try:
        return WindowsProcessInfo(
            process_id=int(payload.get("ProcessId") or 0),
            parent_process_id=int(payload.get("ParentProcessId") or 0),
            executable_path=str(payload.get("ExecutablePath") or ""),
            command_line=str(payload.get("CommandLine") or ""),
        )
    except (TypeError, ValueError):
        return None


def listener_process(port: int) -> WindowsProcessInfo | None:
    if not IS_WINDOWS:
        return None
    payload = _powershell_json(
        "$c = Get-NetTCPConnection -LocalPort %d -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; "
        "if ($null -ne $c) { $p = Get-CimInstance Win32_Process -Filter \"ProcessId = $($c.OwningProcess)\" "
        "-ErrorAction SilentlyContinue; if ($null -ne $p) { [PSCustomObject]@{ ProcessId=$p.ProcessId; "
        "ParentProcessId=$p.ParentProcessId; ExecutablePath=$p.ExecutablePath; CommandLine=$p.CommandLine } | "
        "ConvertTo-Json -Compress } }" % port
    )
    if not payload:
        return None
    try:
        return WindowsProcessInfo(
            process_id=int(payload.get("ProcessId") or 0),
            parent_process_id=int(payload.get("ParentProcessId") or 0),
            executable_path=str(payload.get("ExecutablePath") or ""),
            command_line=str(payload.get("CommandLine") or ""),
        )
    except (TypeError, ValueError):
        return None


def belongs_to_repo(info: WindowsProcessInfo, repo_root: Path) -> bool:
    repo = str(repo_root.resolve()).replace("\\", "/").casefold().rstrip("/")
    haystack = f"{info.executable_path}\n{info.command_line}".replace("\\", "/").casefold()
    return bool(repo and repo in haystack)


def terminate_tree(process_id: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(process_id), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def cleanup_repo_listener(
    repo_root: Path,
    port: int,
    label: str,
    *,
    trusted_identity: bool = False,
    timeout: float = 8.0,
) -> bool:
    """Stop a listener only when its identity is proven to belong to this checkout."""
    if not port_open(port):
        return False

    info = listener_process(port)
    if info is None:
        raise RuntimeError(
            f"Port {port} is occupied, but Studio could not identify its Windows owner. "
            "It was not terminated."
        )
    if not trusted_identity and not belongs_to_repo(info, repo_root):
        detail = info.command_line or info.executable_path or f"PID {info.process_id}"
        raise RuntimeError(
            f"Port {port} is occupied by a process outside this AI Drama Studio checkout: {detail}. "
            "It was not terminated."
        )

    identity_note = "runtime fingerprint" if trusted_identity and not belongs_to_repo(info, repo_root) else "repo path"
    print(
        f"[Studio] removing orphaned {label} from this checkout "
        f"(PID {info.process_id}, verified by {identity_note})..."
    )
    terminate_tree(info.process_id)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and port_open(port):
        time.sleep(0.2)
    if port_open(port):
        raise RuntimeError(f"Port {port} is still occupied after stopping the previous {label} process tree.")
    return True


def cleanup_repo_services(repo_root: Path) -> None:
    if not IS_WINDOWS:
        return

    # The backend may be launched by uv-managed Python outside the repository,
    # so path-based ownership alone is insufficient. Compute this before any
    # cleanup and trust it only for port 8000 when the live server reports the
    # exact immutable source fingerprint for this checkout.
    backend_identity_matches = backend_runtime_matches_checkout(repo_root)

    errors: list[str] = []
    for port, label in ((5173, "frontend"), (8000, "backend"), (8092, "IndexTTS-2.5")):
        try:
            cleanup_repo_listener(
                repo_root,
                port,
                label,
                trusted_identity=(port == 8000 and backend_identity_matches),
            )
        except RuntimeError as exc:
            errors.append(str(exc))
    if errors:
        raise RuntimeError("\n".join(errors))
