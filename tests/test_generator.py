"""Local generation, malformed output, and the fallback catalog."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from outmark.app import create_app
from outmark.clock import FakeClock
from outmark.config import Settings
from outmark.engine import SessionEngine
from outmark.errors import LocalModelError, ValidationError
from outmark.generator import (
    LlamaServerSource,
    UrllibChatClient,
    is_local_model_url,
    parse_activity,
    prepare_request,
    request_from_engine,
)
from outmark.generator_types import GenerationRequest
from outmark.records import ActivityDraft, CompletionReport
from outmark.storage import JsonStore

ZONE = timezone(timedelta(hours=5, minutes=45))
START = datetime(2026, 10, 10, 12, 0, tzinfo=ZONE)


def test_valid_model_json_keeps_the_requested_duration() -> None:
    client = _Scripted(_activity_json(duration_minutes=15))
    source = LlamaServerSource(client=client)

    result = source.generate(prepare_request(5, "nature_observation"))

    assert result.source == "model"
    assert result.activity.duration_minutes == 5
    assert result.activity.category == "nature_observation"
    assert result.activity.title == "Notice three leaves"
    assert result.activity.instructions.startswith(
        "Spend 5 minutes outside noticing plants, sky, or the ground."
    )
    assert client.calls == 1


def test_thinking_text_is_ignored_and_the_json_after_it_is_used() -> None:
    body = '<think>Maybe birds. {"title":"no"}</think>\n' + _activity_json()
    activity = parse_activity(body, 10)
    assert activity.title == "Notice three leaves"
    body = "```json\n" + _activity_json() + "\n```"
    activity = parse_activity(body, 10)
    assert activity.title == "Notice three leaves"


def test_malformed_invalid_and_completion_claims_use_the_catalog() -> None:
    cases = [
        "not json",
        _activity_json(instructions=""),
        _activity_json(instructions="You have completed this walk."),
    ]
    for content in cases:
        client = _Scripted(content)
        result = LlamaServerSource(client=client).generate(prepare_request(10, "walking"))
        assert result.source == "fallback"
        assert result.activity.category == "walking"
        assert result.activity.duration_minutes == 10


def test_transport_failure_uses_the_next_unused_fallback() -> None:
    client = _Scripted(LocalModelError("down"))
    request = prepare_request(10, "walking", ("Walk a familiar block",))

    result = LlamaServerSource(client=client).generate(request)

    assert result.source == "fallback"
    assert result.activity.title == "Feel the ground change"
    assert "10 minutes" in result.activity.instructions


def test_a_public_model_url_is_not_called() -> None:
    client = _Scripted("unused")
    source = LlamaServerSource(
        chat_url="https://api.openai.com/v1/chat/completions",
        client=client,
    )

    result = source.generate(prepare_request(10, "quiet_outdoor"))

    assert client.calls == 0
    assert result.source == "fallback"
    assert result.activity.category == "quiet_outdoor"
    assert is_local_model_url("https://api.openai.com/v1/chat/completions") is False
    assert is_local_model_url("http://127.0.0.1:8081/v1/chat/completions") is True
    assert is_local_model_url("http://llamacpp-models-runner:9999/v1/chat/completions") is True
    assert is_local_model_url("http://some-other-container:9999/v1/chat/completions") is False


def test_invalid_duration_does_not_call_the_model() -> None:
    client = _Scripted(_activity_json())
    with pytest.raises(ValidationError):
        LlamaServerSource(client=client).generate(
            GenerationRequest(duration_minutes=7, preferred_category="walking")
        )
    assert client.calls == 0


def test_generation_does_not_change_stored_sessions(tmp_path: Path) -> None:
    engine, path, clock = _engine(tmp_path)
    proposal = engine.propose(_draft())
    session = engine.accept(proposal.id)
    clock.advance(session.duration_minutes * 60)
    engine.report(session.id, CompletionReport("kept", "A sparrow on the wall."))
    before = path.read_text(encoding="utf-8")
    request = request_from_engine(engine, 10, "nature_observation")

    LlamaServerSource(client=_Scripted(LocalModelError("down"))).generate(request)

    assert path.read_text(encoding="utf-8") == before
    assert "A sparrow on the wall." in request.recent_reflections
    assert "A sparrow on the wall." in before


def test_recent_reflection_is_included_in_the_prompt(tmp_path: Path) -> None:
    engine, _path, clock = _engine(tmp_path)
    session = engine.accept(engine.propose(_draft()).id)
    clock.advance(session.duration_minutes * 60)
    engine.report(session.id, CompletionReport("kept", "The leaves were wet."))
    client = _Scripted(_activity_json())

    LlamaServerSource(client=client).generate(request_from_engine(engine, 10, "walking"))

    user = client.payloads[0]["messages"][1]["content"]
    system = client.payloads[0]["messages"][0]["content"]
    assert "The leaves were wet." in user
    assert "Walking and movement" in user
    assert "You write one short outdoor activity as JSON." in system
    assert "Authorization" not in json.dumps(client.payloads[0])


def test_a_rejected_suggestion_is_avoided_and_the_category_stays(tmp_path: Path) -> None:
    engine, _path, _clock = _engine(tmp_path)
    engine.reject(engine.propose(_draft()).id)
    client = _Scripted(
        _activity_json(
            title="Bird Spotting",
            category="creative_observation",
            instructions="Watch three birds.",
        )
    )

    result = LlamaServerSource(client=client).generate(request_from_engine(engine, 5, "walking"))

    user = str(client.payloads[0]["messages"][1]["content"])
    assert "Walk a familiar block" in user
    assert "Category id: walking." in user
    assert result.activity.category == "walking"
    assert result.activity.duration_minutes == 5
    assert result.source == "fallback"
    assert result.activity.title != "Bird Spotting"
    assert client.payloads[0]["temperature"] == 0.4
    assert isinstance(client.payloads[0]["seed"], int)


def test_urllib_client_posts_to_loopback_without_an_api_key() -> None:
    server = _ChatServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/v1/chat/completions"
        text = UrllibChatClient().complete(url, {"model": "local", "messages": []}, timeout=5)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert "Notice three leaves" in text
    assert server.path == "/v1/chat/completions"
    assert "Authorization" not in server.headers


def test_app_prepares_a_local_source_without_calling_it(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    source = app.config["OUTMARK_ACTIVITY_SOURCE"]

    assert isinstance(source, LlamaServerSource)
    assert source.chat_url == "http://llamacpp-models-runner:9999/v1/chat/completions"
    assert source.model == "Qwen3.5-0.8B-Q4_0"
    assert app.test_client().get("/health").status_code == 200


def _activity_json(**overrides: object) -> str:
    payload: dict[str, object] = {
        "title": "Notice three leaves",
        "instructions": "Spend the time outside and look at three leaves without picking them.",
        "reflection_question": "Which leaf shape was new?",
        "category": "nature_observation",
    }
    payload.update(overrides)
    return json.dumps(payload)


class _Scripted:
    def __init__(self, result: str | Exception) -> None:
        self._result = result
        self.calls = 0
        self.payloads: list[dict[str, object]] = []

    def complete(self, url: str, payload: dict[str, object], timeout: float) -> str:
        self.calls += 1
        self.payloads.append(payload)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _ChatServer(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _ChatHandler)
        self.path = ""
        self.headers: dict[str, str] = {}


class _ChatHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        server = self.server
        assert isinstance(server, _ChatServer)
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        server.path = self.path
        server.headers = {key: value for key, value in self.headers.items()}
        content = _activity_json()
        body = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _engine(tmp_path: Path) -> tuple[SessionEngine, Path, FakeClock]:
    path = tmp_path / "outmark.json"
    clock = FakeClock(START)
    engine = SessionEngine(JsonStore(path), clock)
    return engine, path, clock


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8080,
        data_dir=tmp_path / "data",
        model_dir=tmp_path / "models",
        log_level="INFO",
    )


def _draft() -> ActivityDraft:
    return ActivityDraft(
        duration_minutes=10,
        category="walking",
        title="Walk the block",
        instructions="Walk a familiar block and notice three doorways.",
        reflection_question="Which doorway had you stopped seeing?",
    )
