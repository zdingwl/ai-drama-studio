from pathlib import Path

from engine.app.breakdown_p2_vlm_v1 import Qwen3VLSemanticProvider


def _repo_root() -> Path:
    # engine/tests/v2/<test>.py -> repository root
    return Path(__file__).resolve().parents[3]


def test_legacy_4b_provider_default_checkpoint_remains_compatible(monkeypatch) -> None:
    """Historical 4B provider remains available for compatibility, but is not production P2."""
    monkeypatch.delenv("AI_DRAMA_P2_VLM_MODEL_PATH", raising=False)
    monkeypatch.delenv("AI_DRAMA_P2_VLM_MODEL", raising=False)

    provider = Qwen3VLSemanticProvider(inference_runner=lambda _config, _shots: ())
    normalized = provider.model_path.as_posix()

    assert normalized.endswith(".runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct")
    assert provider.model_name == "Qwen/Qwen3-VL-4B-Instruct"


def test_current_breakdown_vlm_setup_script_provisions_qwen38_checkpoint() -> None:
    script = (_repo_root() / "scripts" / "setup_breakdown_vlm_runtime.ps1").read_text(encoding="utf-8")

    assert "Qwen/Qwen3.8-27B" in script
    assert ".runtime\\Qwen38Visual" in script
    assert "pretrained\\Qwen3.8-27B" in script
    assert "snapshot_download" in script
    assert "qwen-vl-utils[decord]==0.0.14" in script
    assert "run_breakdown_vlm_fast_grounded_qwen38.py" in script
    assert "check_qwen38_visual_runtime.py" in script


def test_breakdown_vlm_setup_script_is_ascii_for_windows_powershell_51() -> None:
    script = (_repo_root() / "scripts" / "setup_breakdown_vlm_runtime.ps1").read_text(encoding="utf-8")

    # Windows PowerShell 5.1 may parse UTF-8-without-BOM .ps1 files through the active ANSI code page.
    # Keeping this setup entrypoint ASCII-only prevents locale-dependent quote/parser corruption.
    script.encode("ascii")
