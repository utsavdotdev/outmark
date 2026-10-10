"""Process configuration and on-disk locations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Paths are resolved before the server starts."""

    host: str
    port: int
    data_dir: Path
    model_dir: Path
    log_level: str


def load_settings() -> Settings:
    """Read settings from the environment, with local defaults."""
    data_dir = _optional_path("OUTMARK_DATA_DIR", APP_ROOT / "data")
    model_dir = _optional_path("OUTMARK_MODEL_DIR", APP_ROOT / "models")
    return Settings(
        host=os.environ.get("OUTMARK_HOST", "0.0.0.0").strip() or "0.0.0.0",
        port=_port(os.environ.get("OUTMARK_PORT", "8080")),
        data_dir=data_dir,
        model_dir=model_dir,
        log_level=_log_level(os.environ.get("OUTMARK_LOG_LEVEL", "INFO")),
    )


def model_is_present(model_dir: Path) -> bool:
    """Return whether a GGUF weight file is already on disk."""
    if not model_dir.is_dir():
        return False
    return any(path.suffix.lower() == ".gguf" for path in model_dir.iterdir() if path.is_file())


def _optional_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return Path(raw).expanduser().resolve()


def _port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError("OUTMARK_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("OUTMARK_PORT must be between 1 and 65535")
    return port


def _log_level(raw: str) -> str:
    level = raw.strip().upper()
    if level not in _LOG_LEVELS:
        allowed = ", ".join(sorted(_LOG_LEVELS))
        raise ValueError(f"OUTMARK_LOG_LEVEL must be one of: {allowed}")
    return level
