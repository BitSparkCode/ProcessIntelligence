"""Provider-agnostic LLM foundation (Story 6.3).

Goal: one small, safe, testable abstraction every AI feature builds on. When no
provider/key is configured the client reports itself disabled and callers fall
back to deterministic behavior — the app is always usable without AI.
"""

from __future__ import annotations

import json
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)


class LLMResult(BaseModel):
    text: str
    provider: str
    model: str


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def complete(self, *, system: str, user: str, json_mode: bool) -> str: ...


class NullProvider:
    """Used when AI is disabled. Never makes network calls."""

    name = "none"

    def complete(self, *, system: str, user: str, json_mode: bool) -> str:
        raise LLMError("AI is disabled: no provider/API key configured")


class OpenAIProvider:
    name = "openai"

    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def complete(self, *, system: str, user: str, json_mode: bool) -> str:
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def complete(self, *, system: str, user: str, json_mode: bool) -> str:
        # Anthropic has no JSON mode flag; instruct via the system prompt instead.
        sys_prompt = system
        if json_mode:
            sys_prompt += "\n\nRespond with a single valid JSON object and nothing else."
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self._model,
                "max_tokens": 1024,
                "system": sys_prompt,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


class LLMClient:
    """Thin client wrapping a provider with structured-output support."""

    def __init__(self, provider: LLMProvider, *, model: str) -> None:
        self._provider = provider
        self._model = model

    @property
    def enabled(self) -> bool:
        return self._provider.name != "none"

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def complete(self, *, system: str, user: str, json_mode: bool = False) -> LLMResult:
        text = self._provider.complete(system=system, user=user, json_mode=json_mode)
        return LLMResult(text=text, provider=self._provider.name, model=self._model)

    def structured(self, *, system: str, user: str, schema: type[T]) -> T:
        """Call the model and validate the JSON response against ``schema``."""
        result = self.complete(system=system, user=user, json_mode=True)
        raw = _extract_json(result.text)
        try:
            return schema.model_validate(raw)
        except ValidationError as exc:
            raise LLMError(f"LLM returned data not matching {schema.__name__}: {exc}") from exc


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        # strip ```json ... ``` fences
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM did not return valid JSON: {text[:200]}") from exc


def _build_provider(settings: Settings) -> LLMProvider:
    provider = settings.ai_provider.lower()
    if provider == "openai" and settings.openai_api_key:
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.ai_model,
            timeout=settings.ai_request_timeout,
        )
    if provider == "anthropic" and settings.anthropic_api_key:
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.ai_model,
            timeout=settings.ai_request_timeout,
        )
    return NullProvider()


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    return LLMClient(_build_provider(settings), model=settings.ai_model)


def is_ai_enabled(settings: Settings | None = None) -> bool:
    return get_llm_client(settings).enabled
