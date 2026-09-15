from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import studio_windows_lifecycle as lifecycle


def test_unified_launcher_is_single_user_entrypoint_without_legacy_tts_bootstrap() -> None:
    start_cmd = (REPO_ROOT / "start.cmd").read_text(encoding="utf-8")
    start_sh = (REPO_ROOT / "start.sh").read_text(encoding="utf-8")
    launcher = (REPO_ROOT / "scripts" / "start_studio.py").read_text(encoding="utf-8")
    guard = (REPO_ROOT / "scripts" / "start_studio_guard.py").read_text(encoding="utf-8")

    assert "scripts\\start_studio_guard.py" in start_cmd
    assert "scripts/start_studio_guard.py" in start_sh
    assert "start_studio.py" in guard
    assert "start_indextts25_native_windows.ps1" not in launcher
    assert "start_indextts25.sh" not in launcher
    assert "_start_tts" not in launcher
    assert "MiniMax H3 native synchronized audio + video" in launcher
    assert "alembic" in launcher
    assert "npm" in launcher


def test_windows_legacy_indextts_runtime_remains_explicit_and_does_not_require_wsl() -> None:
    launcher = (REPO_ROOT / "scripts" / "start_studio.py").read_text(encoding="utf-8")
    windows_runtime = (REPO_ROOT / "scripts" / "start_indextts25_native_windows.ps1").read_text(encoding="utf-8")
    powershell_entry = (REPO_ROOT / "scripts" / "start_indextts25.ps1").read_text(encoding="utf-8")
    adapter = (REPO_ROOT / "scripts" / "indextts25_native_server.py").read_text(encoding="utf-8")

    assert "wsl.exe" not in launcher
    assert "wsl.exe" not in windows_runtime
    assert "start_indextts25_native_windows.ps1" in powershell_entry
    assert "uv sync" in windows_runtime
    assert "IndexTeam/IndexTTS-2.5" in windows_runtime
    assert "ee40fa7d6c6b8a2c7f06105f9f1e65775b74868c" in windows_runtime
    assert "from indextts.infer_v2_5 import IndexTTS2" in adapter
    assert '@app.get("/v1/models")' in adapter
    assert '@app.post("/v1/audio/speech")' in adapter
    assert "use_qwen_emo=True" in adapter
    assert "duration_factor=request.speed" in adapter


def test_linux_legacy_indextts_runtime_is_pinned_and_explicit_only() -> None:
    runtime = (REPO_ROOT / "scripts" / "ensure_indextts25_runtime.sh").read_text(encoding="utf-8")
    launcher = (REPO_ROOT / "scripts" / "start_studio.py").read_text(encoding="utf-8")

    assert "vllm==0.28.0" in runtime
    assert "vllm-omni[indextts2]==0.28.0" in runtime
    assert "modelscope" in runtime
    assert "indextts2_5.yaml" in runtime
    assert "--deploy-config" in runtime
    assert "--served-model-name" in runtime
    assert "IndexTeam/IndexTTS-2.5" in runtime
    assert "start_indextts25.sh" not in launcher


def test_h3_main_chain_uses_native_synchronized_audio_video_without_lip_sync() -> None:
    prompting = (REPO_ROOT / "backend" / "app" / "replica_pipeline" / "h3_prompting.py").read_text(encoding="utf-8")

    assert "GenerationAudioMode.NATIVE_AUDIO_VIDEO" in prompting
    assert "requires_lip_sync=False" in prompting


def test_managed_runtime_cache_is_not_committed() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/.models/" in gitignore
    assert "/.runtime/" in gitignore


def test_windows_cleanup_accepts_repo_owned_uvicorn_parent_for_external_uv_worker(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "ai-drama-studio"
    repo_python = repo_root / ".venv" / "Scripts" / "python.exe"
    listener = lifecycle.WindowsProcessInfo(
        process_id=11720,
        parent_process_id=35532,
        executable_path=r"C:\Users\Admin\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe",
        command_line=(
            r'"C:\Users\Admin\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe" '
            r"-m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        ),
    )
    parent = lifecycle.WindowsProcessInfo(
        process_id=35532,
        parent_process_id=1,
        executable_path=str(repo_python),
        command_line=f'"{repo_python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
    )
    port_states = iter((True, False, False))
    terminated: list[int] = []

    monkeypatch.setattr(lifecycle, "port_open", lambda _port: next(port_states))
    monkeypatch.setattr(lifecycle, "listener_process", lambda _port: listener)
    monkeypatch.setattr(lifecycle, "process_info", lambda pid: parent if pid == parent.process_id else None)
    monkeypatch.setattr(lifecycle, "terminate_tree", terminated.append)

    assert lifecycle.cleanup_repo_listener(repo_root, 8000, "backend", trusted_identity=False, timeout=0.1) is True
    assert terminated == [parent.process_id]
