from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_unified_launcher_is_single_user_entrypoint() -> None:
    start_cmd = (REPO_ROOT / "start.cmd").read_text(encoding="utf-8")
    start_sh = (REPO_ROOT / "start.sh").read_text(encoding="utf-8")
    launcher = (REPO_ROOT / "scripts" / "start_studio.py").read_text(encoding="utf-8")

    assert "scripts\\start_studio.py" in start_cmd
    assert "scripts/start_studio.py" in start_sh
    assert "start_indextts25.sh" in launcher
    assert "alembic" in launcher
    assert "npm" in launcher


def test_managed_indextts_runtime_is_pinned_and_uses_explicit_deploy_config() -> None:
    runtime = (REPO_ROOT / "scripts" / "ensure_indextts25_runtime.sh").read_text(encoding="utf-8")

    assert "vllm==0.28.0" in runtime
    assert "vllm-omni[indextts2]==0.28.0" in runtime
    assert "modelscope" in runtime
    assert "indextts2_5.yaml" in runtime
    assert "--deploy-config" in runtime
    assert "--served-model-name" in runtime
    assert "IndexTeam/IndexTTS-2.5" in runtime


def test_managed_runtime_cache_is_not_committed() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/.models/" in gitignore
    assert "/.runtime/" in gitignore
