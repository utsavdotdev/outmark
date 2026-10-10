"""Import and health checks for the Stage 1 application."""

from __future__ import annotations

from pathlib import Path

import pytest

from outmark.app import create_app
from outmark.config import Settings, load_settings


def test_package_imports() -> None:
    import outmark
    from outmark.app import create_app as factory
    from outmark.config import load_settings as settings_loader

    assert outmark.__version__ == "0.1.0"
    assert callable(factory)
    assert callable(settings_loader)


def test_health_without_model(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "model_present": False,
        "data_dir_ready": True,
    }
    assert (tmp_path / "data").is_dir()
    assert not (tmp_path / "models").exists()


def test_health_sees_a_model_file_without_loading_it(tmp_path: Path) -> None:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    (model_dir / "placeholder.gguf").write_bytes(b"not-a-real-model")

    response = create_app(_settings(tmp_path)).test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json()["model_present"] is True


def test_home_page(tmp_path: Path) -> None:
    client = create_app(_settings(tmp_path)).test_client()
    response = client.get("/")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Outmark" in page
    assert "Make a promise. Step away. Leave a mark." in page

    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "/health" in script.get_data(as_text=True)


def test_load_settings_rejects_a_bad_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OUTMARK_PORT", "nope")
    with pytest.raises(ValueError, match="OUTMARK_PORT"):
        load_settings()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8080,
        data_dir=tmp_path / "data",
        model_dir=tmp_path / "models",
        log_level="INFO",
    )
