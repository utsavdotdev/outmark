"""Local activity generation. A failed model call returns a catalog activity."""

from __future__ import annotations

import ipaddress
import json
import logging
import urllib.error
import urllib.request
from typing import Protocol
from urllib.parse import urlparse

from outmark.catalog import choose_fallback
from outmark.engine import SessionEngine
from outmark.errors import LocalModelError, ValidationError
from outmark.generator_types import GenerationRequest, GenerationResult
from outmark.prompts import SYSTEM_PROMPT, user_message
from outmark.records import ActivityDraft
from outmark.validation import (
    INSTRUCTIONS_LIMIT,
    QUESTION_LIMIT,
    TITLE_LIMIT,
    require_category,
    require_duration,
    require_text,
)

logger = logging.getLogger(__name__)

DEFAULT_LLM_URL = "http://127.0.0.1:8081/v1/chat/completions"
DEFAULT_LLM_MODEL = "qwen2.5-0.5b-instruct"
_COMPLETION_CLAIMS = (
    "you have completed",
    "you already completed",
    "you completed the",
    "marked as kept",
)


class ChatClient(Protocol):
    """Sends one chat-completion request and returns the assistant text."""

    def complete(self, url: str, payload: dict[str, object], timeout: float) -> str:
        """Return the assistant message content."""


class ActivitySource(Protocol):
    """A replaceable generator. It returns an activity and does not start a timer."""

    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Return one validated activity."""


class UrllibChatClient:
    """POST JSON to a local llama-server. No API key is sent."""

    def complete(self, url: str, payload: dict[str, object], timeout: float) -> str:
        if not is_local_model_url(url):
            raise LocalModelError("the model URL is not a local address")
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise LocalModelError("the local model request failed") from exc
        return _assistant_text(parsed)


class LlamaServerSource:
    """OpenAI-compatible llama-server adapter with a deterministic fallback."""

    def __init__(
        self,
        chat_url: str = DEFAULT_LLM_URL,
        model: str = DEFAULT_LLM_MODEL,
        timeout: float = 60.0,
        client: ChatClient | None = None,
    ) -> None:
        self.chat_url = normalize_chat_url(chat_url)
        self.model = model
        self.timeout = timeout
        self._client = client if client is not None else UrllibChatClient()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        prepared = prepare_request(
            request.duration_minutes,
            request.preferred_category,
            request.recent_activities,
            request.recent_reflections,
        )
        if not is_local_model_url(self.chat_url):
            logger.warning("Refusing a non-local model URL. Using a catalog activity.")
            return _fallback(prepared)
        try:
            content = self._client.complete(
                self.chat_url,
                _payload(self.model, prepared),
                self.timeout,
            )
            activity = parse_activity(content, prepared.duration_minutes)
        except (LocalModelError, ValidationError, ValueError) as exc:
            logger.info("Local generation failed (%s). Using a catalog activity.", exc)
            return _fallback(prepared)
        return GenerationResult(activity=activity, source="model")


def source_from_settings(llm_url: str, llm_model: str, timeout: float) -> LlamaServerSource:
    """Build the default local source. This does not contact the model."""
    return LlamaServerSource(chat_url=llm_url, model=llm_model, timeout=timeout)


def prepare_request(
    duration_minutes: object,
    preferred_category: object,
    recent_activities: tuple[str, ...] = (),
    recent_reflections: tuple[str, ...] = (),
) -> GenerationRequest:
    """Validate a generation request before any model call."""
    return GenerationRequest(
        duration_minutes=require_duration(duration_minutes),
        preferred_category=require_category(preferred_category),
        recent_activities=recent_activities,
        recent_reflections=recent_reflections,
    )


def request_from_engine(
    engine: SessionEngine,
    duration_minutes: object,
    preferred_category: object,
) -> GenerationRequest:
    """Use the latest stored sessions, including reflections, as model context."""
    activities: list[str] = []
    reflections: list[str] = []
    for session in engine.sessions()[-5:]:
        activities.append(session.title)
        if session.quest and session.quest != session.title:
            activities.append(session.quest)
        if session.reflection:
            reflections.append(session.reflection)
    return prepare_request(
        duration_minutes,
        preferred_category,
        tuple(activities),
        tuple(reflections),
    )


def parse_activity(content: str, duration_minutes: int) -> ActivityDraft:
    """Accept one JSON object. The requested duration is kept even if the model names another."""
    raw = _extract_json(content)
    if not isinstance(raw, dict):
        raise ValidationError("model response must be a JSON object")
    for field in ("title", "instructions", "reflection_question", "category"):
        if field not in raw:
            raise ValidationError(f"model response is missing {field}")
    title = require_text(raw.get("title"), "title", TITLE_LIMIT)
    instructions = require_text(raw.get("instructions"), "instructions", INSTRUCTIONS_LIMIT)
    question = require_text(raw.get("reflection_question"), "reflection_question", QUESTION_LIMIT)
    _reject_completion_claim(title, instructions, question)
    return ActivityDraft(
        duration_minutes=duration_minutes,
        category=require_category(raw.get("category")),
        title=title,
        instructions=instructions,
        reflection_question=question,
    )


def is_local_model_url(url: str) -> bool:
    """Allow loopback and private addresses only. Hostnames other than localhost are refused."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return False
    host = parsed.hostname
    if host is None:
        return False
    if host.lower() == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(address.is_loopback or address.is_private or address.is_link_local)


def normalize_chat_url(url: str) -> str:
    stripped = url.strip().rstrip("/")
    suffix = "/v1/chat/completions"
    if stripped.endswith(suffix):
        return stripped
    return stripped + suffix


def _payload(model: str, request: GenerationRequest) -> dict[str, object]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message(request)},
        ],
        "temperature": 0.4,
        "max_tokens": 200,
    }


def _fallback(request: GenerationRequest) -> GenerationResult:
    activity = choose_fallback(
        request.duration_minutes,
        request.preferred_category,
        request.recent_activities,
    )
    return GenerationResult(activity=activity, source="fallback")


def _extract_json(content: str) -> object:
    text = content.strip()
    if text.startswith("```"):
        newline = text.find("\n")
        text = text[newline + 1 :] if newline != -1 else text
        fence = text.rfind("```")
        if fence != -1:
            text = text[:fence]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValidationError("model response did not contain JSON")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValidationError("model response was not valid JSON") from exc


def _assistant_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise LocalModelError("model response was not an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LocalModelError("model response did not include a choice")
    first = choices[0]
    if not isinstance(first, dict):
        raise LocalModelError("model response choice was not an object")
    message = first.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise LocalModelError("model response did not include text")
    return message["content"]


def _reject_completion_claim(*fields: str) -> None:
    combined = " ".join(fields).casefold()
    if any(phrase in combined for phrase in _COMPLETION_CLAIMS):
        raise ValidationError("model response claimed the activity was already completed")
