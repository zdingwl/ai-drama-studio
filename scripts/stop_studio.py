#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sys
import time

from studio_windows_lifecycle import (
    belongs_to_repo,
    cleanup_repo_services,
    process_info,
    terminate_tree,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PID_FILE = REPO_ROOT / ".runtime" / "studio-launcher.pid"


def _read_launcher_pid() -> int | None:
    try:
        value = PID_FILE.read_text(encoding="utf-8").strip()
        pid = int(value)
        return pid if pid > 0 else None
    except (OSError, ValueError):
        return None


def _remove_pid_file() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def main() -> int:
    if os.name != "nt":
        print("stop.cmd / stop_studio.py currently manages the native Windows launcher only.", file=sys.stderr)
        return 2

    errors: list[str] = []
    launcher_pid = _read_launcher_pid()
    if launcher_pid is not None:
        info = process_info(launcher_pid)
        normalized = (info.command_line if info else "").replace("\\", "/").casefold()
        if info and belongs_to_repo(info, REPO_ROOT) and "scripts/start_studio.py" in normalized:
            print(f"[Studio] stopping active launcher PID {launcher_pid}; its Windows Job will close the managed process tree...")
            terminate_tree(launcher_pid)
            time.sleep(1.0)
        elif info is not None:
            print(
                f"[Studio] stale launcher PID file points to PID {launcher_pid}, but that process is not this checkout's launcher; it was not terminated."
            )
        _remove_pid_file()

    try:
        # Covers legacy orphan processes created before the Job Object lifecycle
        # guard existed. Unknown/non-Studio port owners are deliberately not
        # terminated.
        cleanup_repo_services(REPO_ROOT)
    except RuntimeError as exc:
        errors.append(str(exc))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("[Studio] stopped. Managed ports 5173 / 8000 / 8092 are clear for this checkout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
