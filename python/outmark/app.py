"""Flask application factory. Starts without a language model."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask, jsonify, render_template

from outmark.clock import Clock, SystemClock
from outmark.config import Settings, load_settings, model_is_present
from outmark.display import MatrixDisplay, publish
from outmark.engine import SessionEngine
from outmark.storage import STORE_FILENAME, JsonStore

PACKAGE_ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    display: MatrixDisplay | None = None,
    clock: Clock | None = None,
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
    app.config["OUTMARK_ENGINE"] = None
    if display is not None:
        _publish_startup(app, resolved, display, clock or SystemClock())

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


def _publish_startup(app: Flask, settings: Settings, display: MatrixDisplay, clock: Clock) -> None:
    """Push the stored grid once. A bridge failure leaves the JSON file alone."""
    try:
        engine = SessionEngine(JsonStore(settings.data_dir / STORE_FILENAME), clock)
        app.config["OUTMARK_ENGINE"] = engine
        publish(engine, display)
    except Exception:
        logger.exception("Matrix startup skipped. Stored sessions were left unchanged.")
