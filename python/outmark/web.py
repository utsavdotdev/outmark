"""HTTP routes for the local page. The engine remains the session authority."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from flask import Flask, jsonify, request

from outmark.categories import CATEGORIES
from outmark.config import model_is_present
from outmark.display import publish
from outmark.engine import SessionEngine
from outmark.errors import StorageError, TransitionError, ValidationError
from outmark.generator import ActivitySource, request_from_engine
from outmark.records import CompletionReport, SessionSnapshot
from outmark.validation import require_outcome

logger = logging.getLogger(__name__)


def register(app: Flask) -> None:
    """Attach the session routes. A missing store returns an error and does not write."""

    @app.get("/api/session")
    def session():
        return _respond(app, lambda engine: _view(app, engine))

    @app.post("/api/quest")
    def quest():
        def action(engine: SessionEngine) -> dict[str, Any]:
            body = _object_body()
            prepared = request_from_engine(
                engine,
                body.get("duration_minutes"),
                body.get("category"),
            )
            _require_idle(engine)
            source: ActivitySource = app.config["OUTMARK_ACTIVITY_SOURCE"]
            result = source.generate(prepared)
            engine.propose(replace(result.activity, duration_minutes=prepared.duration_minutes))
            payload = _view(app, engine)
            payload["source"] = result.source
            return payload

        return _respond(app, action)

    @app.post("/api/proposal/reject")
    def reject_proposal():
        def action(engine: SessionEngine) -> dict[str, Any]:
            engine.reject(_identifier(_object_body(), "id"))
            return _view(app, engine)

        return _respond(app, action)

    @app.post("/api/session/start")
    def start_session():
        def action(engine: SessionEngine) -> dict[str, Any]:
            engine.accept(_identifier(_object_body(), "proposal_id"))
            return _view(app, engine)

        return _respond(app, action)

    @app.post("/api/session/report")
    def report_session():
        def action(engine: SessionEngine) -> dict[str, Any]:
            body = _object_body()
            reflection = body.get("reflection")
            engine.report(
                _identifier(body, "session_id"),
                CompletionReport(require_outcome(body.get("outcome")), reflection),
            )
            return _view(app, engine)

        return _respond(app, action)

    @app.get("/api/history")
    def history():
        return _respond(app, lambda engine: _history(engine))


def _respond(app: Flask, action: Any) -> Any:
    try:
        engine = _engine(app)
        payload = action(engine)
        _sync_display(app)
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except TransitionError as exc:
        return jsonify({"error": str(exc)}), 409
    except StorageError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        logger.exception("Request failed before a session change could be confirmed.")
        return jsonify({"error": "The request could not be completed."}), 500
    return jsonify(payload)


def _engine(app: Flask) -> SessionEngine:
    engine = app.config["OUTMARK_ENGINE"]
    if not isinstance(engine, SessionEngine):
        raise StorageError("Stored sessions could not be read.")
    return engine


def _require_idle(engine: SessionEngine) -> None:
    if engine.open_proposal() is not None:
        raise TransitionError("reject the open proposal before you request another activity")
    if engine.active_session() is not None:
        raise TransitionError("report the active session before you request another activity")


def _sync_display(app: Flask) -> None:
    display = app.config["OUTMARK_DISPLAY"]
    engine = app.config["OUTMARK_ENGINE"]
    if display is None or not isinstance(engine, SessionEngine):
        return
    try:
        publish(engine, display)
    except Exception:
        logger.exception("Matrix update failed. Stored sessions were left unchanged.")


def _view(app: Flask, engine: SessionEngine) -> dict[str, Any]:
    proposal = engine.open_proposal()
    snapshot = engine.active_session()
    if snapshot is not None:
        phase = "active"
    elif proposal is not None:
        phase = "proposed"
    else:
        phase = "idle"
    settings = app.config["OUTMARK_SETTINGS"]
    return {
        "phase": phase,
        "model_present": model_is_present(settings.model_dir),
        "proposal": None if proposal is None else proposal.to_dict(),
        "session": None if snapshot is None else _snapshot(snapshot),
    }


def _snapshot(snapshot: SessionSnapshot) -> dict[str, Any]:
    session = snapshot.session
    duration = session.duration_minutes * 60
    payload = session.to_dict()
    payload["elapsed_seconds"] = snapshot.elapsed_seconds
    payload["remaining_seconds"] = max(0.0, duration - snapshot.elapsed_seconds)
    payload["deadline_passed"] = snapshot.deadline_passed
    payload["progress_segments"] = snapshot.progress_segments
    return payload


def _history(engine: SessionEngine) -> dict[str, Any]:
    grid = engine.history()
    visible = [
        session.to_dict()
        for session in engine.sessions()
        if grid.start_date <= session.started_at.date() <= grid.end_date
    ]
    return {
        "start_date": grid.start_date.isoformat(),
        "end_date": grid.end_date.isoformat(),
        "rows": [
            {"id": category_id, "label": label, "cells": list(grid.cells[index])}
            for index, (category_id, label) in enumerate(CATEGORIES)
        ],
        "sessions": list(reversed(visible)),
    }


def _object_body() -> dict[str, Any]:
    raw = request.get_json(silent=True)
    if not isinstance(raw, dict):
        raise ValidationError("request body must be a JSON object")
    return raw


def _identifier(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} is required")
    return value.strip()
