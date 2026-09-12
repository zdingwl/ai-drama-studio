from app.api.routes.health import health
from app.core.runtime_identity import compute_backend_source_fingerprint


def test_health_exposes_process_start_source_fingerprint() -> None:
    result = health()
    assert result.status == "ok"
    assert len(result.runtime_fingerprint) == 64
    int(result.runtime_fingerprint, 16)


def test_backend_source_fingerprint_changes_with_python_source(tmp_path) -> None:
    app_root = tmp_path / "app"
    app_root.mkdir()
    first = app_root / "a.py"
    nested = app_root / "nested"
    nested.mkdir()
    second = nested / "b.py"
    first.write_text("VALUE = 1\n", encoding="utf-8")
    second.write_text("VALUE = 2\n", encoding="utf-8")

    before = compute_backend_source_fingerprint(app_root)
    second.write_text("VALUE = 3\n", encoding="utf-8")
    after = compute_backend_source_fingerprint(app_root)

    assert before != after
    assert len(before) == 64
    assert len(after) == 64
