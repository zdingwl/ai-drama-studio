from pathlib import Path

from engine.app.breakdown_p2_vlm_v1 import Qwen3VLSemanticProvider


def test_breakdown_vlm_default_checkpoint_path_matches_setup_script(monkeypatch) -> None:
    monkeypatch.delenv("AI_DRAMA_P2_VLM_MODEL_PATH", raising=False)
    monkeypatch.delenv("AI_DRAMA_P2_VLM_MODEL", raising=False)

    provider = Qwen3VLSemanticProvider(inference_runner=lambda _config, _shots: ())
    normalized = provider.model_path.as_posix()

    assert normalized.endswith(".runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct")
    assert provider.model_name == "Qwen/Qwen3-VL-4B-Instruct"


def test_breakdown_vlm_setup_script_provisions_production_checkpoint() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "scripts" / "setup_breakdown_vlm_runtime.ps1").read_text(encoding="utf-8")

    assert "Qwen/Qwen3-VL-4B-Instruct" in script
    assert "pretrained\\Qwen3-VL-4B-Instruct" in script
    assert "snapshot_download" in script
    assert "local_files_only=True" in script
    assert "run_breakdown_p2.py preflight --strict" in script
