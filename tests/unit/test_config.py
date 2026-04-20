"""Smoke tests for configuration setup."""

from __future__ import annotations

from memory_picker.config import build_settings


def test_build_settings_loads_defaults(tmp_path):
    settings = build_settings(tmp_path)

    assert settings.root_path == tmp_path.resolve()
    assert "jpg" in settings.supported_photo_extensions
    assert settings.managed_folders.rejected == "_rejected"
    assert settings.managed_folders.low_quality == "low_quality"
    assert settings.managed_folders.not_photo == "not_photo"
    assert settings.managed_folders.duplicates == "duplicates"
    assert settings.quality_thresholds.blur_threshold > 0
    assert settings.cleanup_settings.duplicate_similarity_threshold == 0.99
    assert settings.quality_concurrency_settings.enabled is True
    assert settings.quality_concurrency_settings.max_workers == 8
    assert settings.categorization_concurrency_settings.enabled is True
    assert settings.categorization_concurrency_settings.max_concurrent_requests == 4
    assert settings.categorization_concurrency_settings.max_retries == 3
    assert settings.categorization_settings.enabled is False
    assert [category.name for category in settings.categorization_settings.categories] == [
        "people",
        "animals",
        "food",
        "nature",
        "city",
        "architecture",
        "other",
    ]


def test_build_settings_loads_openai_key_from_dotenv(tmp_path, monkeypatch):
    trip_root = tmp_path / "trip"
    trip_root.mkdir()
    dotenv_root = tmp_path / "workspace"
    dotenv_root.mkdir()
    (dotenv_root / ".env").write_text("OPENAI_API_KEY=from-dotenv\n", encoding="utf-8")

    monkeypatch.chdir(dotenv_root)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = build_settings(trip_root)

    assert settings.categorization_settings.openai_api_key == "from-dotenv"


def test_build_settings_loads_hf_token_from_dotenv(tmp_path, monkeypatch):
    trip_root = tmp_path / "trip"
    trip_root.mkdir()
    dotenv_root = tmp_path / "workspace"
    dotenv_root.mkdir()
    (dotenv_root / ".env").write_text("HF_TOKEN=hf-from-dotenv\n", encoding="utf-8")

    monkeypatch.chdir(dotenv_root)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)

    settings = build_settings(trip_root)

    assert settings.embedding_settings.hf_token == "hf-from-dotenv"
