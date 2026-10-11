"""Flask application factory. Starts without a language model."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask, jsonify, render_template

from outmark.clock import Clock, SystemClock
from outmark.config import Settings, load_settings, model_is_present
from outmark.display import DisplayTracker, MatrixDisplay, publish
from outmark.engine import SessionEngine
from outmark.generator import ActivitySource, source_from_settings
from outmark.storage import STORE_FILENAME, JsonStore
from outmark.web import register

PACKAGE_ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    display: MatrixDisplay | None = None,
    clock: Clock | None = None,
    source: ActivitySource | None = None,
) -> Flask:
    """Build the local web application and prepare the data directory."""
    resolved = settings if settings is not None else load_settings()
    resolved.data_dir.mkdir(parents=True, exist_ok=True)

    app = Flask(
        __name__,
        template_folder=str(PACKAGE_ROOT / "templates"),
        static_folder=str(PACKAGE_ROOT / "static"),
    )
    app.config["OUTMARK_SETTINGS"] = resolved
    app.config["OUTMARK_DISPLAY"] = display
    app.config["OUTMARK_DISPLAY_OK"] = False
    app.config["OUTMARK_DISPLAY_TRACKER"] = DisplayTracker()
    app.config["OUTMARK_ENGINE"] = _open_engine(resolved, clock or SystemClock())
    app.config["OUTMARK_ACTIVITY_SOURCE"] = source or source_from_settings(
        resolved.llm_url,
        resolved.llm_model,
        resolved.llm_timeout_seconds,
    )
    register(app)
    if display is not None and app.config["OUTMARK_ENGINE"] is not None:
        _publish_startup(app)

    @app.get("/health")
    def health():
        payload = {
            "status": "ok",
            "model_present": model_is_present(resolved.model_dir),
            "data_dir_ready": _data_dir_ready(resolved.data_dir),
        }
        return jsonify(payload)

    @app.get("/")
    def index():
        return render_template("index.html")

    logger.info(
        "Outmark ready on port %s (model_present=%s)",
        resolved.port,
        model_is_present(resolved.model_dir),
    )
    return app


def _data_dir_ready(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)


def _open_engine(settings: Settings, clock: Clock) -> SessionEngine | None:
    """Load stored sessions. A bad file leaves the engine unset and the file untouched."""
    try:
        return SessionEngine(JsonStore(settings.data_dir / STORE_FILENAME), clock)
    except Exception:
        logger.exception("Stored sessions were left unchanged.")
        return None


def _publish_startup(app: Flask) -> None:
    """Push the stored grid once. A bridge failure leaves the JSON file alone."""
    engine = app.config["OUTMARK_ENGINE"]
    try:
        event = app.config["OUTMARK_DISPLAY_TRACKER"].observe(engine)
        publish(engine, app.config["OUTMARK_DISPLAY"], event)
    except Exception:
        logger.exception("Matrix startup skipped. Stored sessions were left unchanged.")
        return
    app.config["OUTMARK_DISPLAY_OK"] = True
