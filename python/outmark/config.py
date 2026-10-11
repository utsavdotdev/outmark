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
    llm_url: str = "http://127.0.0.1:8081/v1/chat/completions"
    llm_model: str = "qwen2.5-0.5b-instruct"
    llm_timeout_seconds: float = 60.0


def load_settings() -> Settings:
    """Read settings from the environment, with local defaults."""
    data_dir = _optional_path("OUTMARK_DATA_DIR", APP_ROOT / "data")
    model_dir = _optional_path("OUTMARK_MODEL_DIR", APP_ROOT / "models")
    return Settings(
        host=os.environ.get("OUTMARK_HOST", "0.0.0.0").strip() or "0.0.0.0",
        port=_port(os.environ.get("OUTMARK_PORT", "8765")),
        data_dir=data_dir,
        model_dir=model_dir,
        log_level=_log_level(os.environ.get("OUTMARK_LOG_LEVEL", "INFO")),
        llm_url=os.environ.get("OUTMARK_LLM_URL", "http://127.0.0.1:8081/v1/chat/completions"),
        llm_model=_model_name(os.environ.get("OUTMARK_LLM_MODEL", "qwen2.5-0.5b-instruct")),
        llm_timeout_seconds=_timeout(os.environ.get("OUTMARK_LLM_TIMEOUT", "60")),
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


def _timeout(raw: str) -> float:
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise ValueError("OUTMARK_LLM_TIMEOUT must be a number of seconds") from exc
    if not 1 <= timeout <= 600:
        raise ValueError("OUTMARK_LLM_TIMEOUT must be between 1 and 600 seconds")
    return timeout


def _model_name(raw: str) -> str:
    name = raw.strip()
    if not name or len(name) > 80 or any(char.isspace() for char in name):
        raise ValueError("OUTMARK_LLM_MODEL must be a short model alias without spaces")
    return name


def _log_level(raw: str) -> str:
    level = raw.strip().upper()
    if level not in _LOG_LEVELS:
        allowed = ", ".join(sorted(_LOG_LEVELS))
        raise ValueError(f"OUTMARK_LOG_LEVEL must be one of: {allowed}")
    return level
