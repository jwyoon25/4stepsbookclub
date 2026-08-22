"""Mistral's OpenAI-compatible registration and response contract."""

from __future__ import annotations

import json

import httpx
import pytest

from bookengine.config import ProviderConfig
from bookengine.errors import ProviderError, StructuredResponseError
from bookengine.llm.base import Completion, Message
from bookengine.llm.cache import ResponseCache
from bookengine.llm.chain import ProviderChain
from bookengine.llm.openai_compatible import OpenAICompatibleProvider
from bookengine.llm.registry import build_provider
from bookengine.llm.structured import generate_structured
from bookengine.vocabulary.schemas import EntryDraft

MODEL = "mistral-large-2512"
KEY = "mistral-test-key"
MESSAGES = [Message(role="user", content="Return the requested JSON.")]
VALID_DRAFT = {
    "definition": "a difficult situation",
    "korean_meaning": "곤경",
    "excerpt_context": "Mara is left alone in the hut.",
}


def provider(monkeypatch, handler) -> OpenAICompatibleProvider:
    monkeypatch.setenv("MISTRAL_API_KEY", KEY)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(
        ProviderConfig(provider="mistral", model=MODEL), client=client
    )


def response(request: httpx.Request, *, content=VALID_DRAFT) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        json={
            "model": MODEL,
            "choices": [
                {
                    "message": {"content": json.dumps(content)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 41, "completion_tokens": 19},
        },
    )


def test_mistral_registry_uses_the_known_endpoint_and_key(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", KEY)
    endpoint = build_provider(ProviderConfig(provider="mistral", model=MODEL))
    try:
        assert endpoint.base_url == "https://api.mistral.ai/v1"
        assert endpoint.api_key_env == "MISTRAL_API_KEY"
    finally:
        endpoint.close()


def test_mistral_and_groq_have_different_cache_keys(tmp_path):
    cache = ResponseCache(directory=tmp_path / "llm")
    common = {
        "messages": MESSAGES,
        "json_schema": {"type": "object"},
        "temperature": 0.2,
        "max_output_tokens": 256,
    }

    mistral = cache.key(provider="mistral", model=MODEL, **common)
    groq = cache.key(
        provider="groq", model="openai/gpt-oss-120b", **common
    )

    assert mistral != groq


def test_transport_pacing_does_not_change_a_completion_cache_key(tmp_path):
    cache = ResponseCache(directory=tmp_path / "llm")
    unpaced = ProviderConfig(provider="mistral", model=MODEL)
    paced = ProviderConfig(
        provider="mistral", model=MODEL, min_request_interval_seconds=15.5
    )
    common = {
        "messages": MESSAGES,
        "json_schema": {"type": "object"},
        "temperature": 0.2,
        "max_output_tokens": 256,
    }

    assert unpaced.provider == paced.provider
    assert unpaced.model == paced.model
    assert cache.key(provider=unpaced.provider, model=unpaced.model, **common) == (
        cache.key(provider=paced.provider, model=paced.model, **common)
    )


def test_mistral_only_chain_cannot_use_a_cached_groq_completion(tmp_path):
    cache = ResponseCache(directory=tmp_path / "llm")
    common = {
        "messages": MESSAGES,
        "json_schema": None,
        "temperature": None,
        "max_output_tokens": None,
    }
    groq_key = cache.key(
        provider="groq", model="openai/gpt-oss-120b", **common
    )
    cache.store(
        groq_key,
        Completion(
            text="old groq answer",
            provider="groq",
            model="openai/gpt-oss-120b",
            prompt_tokens=1,
            completion_tokens=1,
        ),
    )

    class MistralOnly:
        name = "mistral"
        model = MODEL
        calls = 0

        def complete(self, messages, **kwargs):
            self.calls += 1
            return Completion(
                text="new mistral answer",
                provider=self.name,
                model=self.model,
                prompt_tokens=1,
                completion_tokens=1,
            )

    endpoint = MistralOnly()
    result = ProviderChain(
        providers=[endpoint], cache=cache, max_attempts=1
    ).complete(MESSAGES)

    assert result.provider == "mistral"
    assert endpoint.calls == 1


def test_mistral_sends_auth_and_returns_structured_provenance_and_usage(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("Authorization")
        seen["payload"] = json.loads(request.content)
        return response(request)

    endpoint = provider(monkeypatch, handler)
    chain = ProviderChain(providers=[endpoint], max_attempts=1)
    try:
        draft, completion = generate_structured(
            chain, MESSAGES, EntryDraft, max_repairs=0
        )
    finally:
        chain.close()

    assert seen["authorization"] == f"Bearer {KEY}"
    assert seen["payload"]["response_format"]["type"] == "json_schema"
    assert draft.korean_meaning == "곤경"
    assert completion.provider == "mistral"
    assert completion.model == MODEL
    assert completion.prompt_tokens == 41
    assert completion.completion_tokens == 19
    assert KEY not in repr(completion)


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(401, False), (403, False), (429, True), (500, True), (503, True)],
)
def test_mistral_http_failures_are_classified(monkeypatch, status, retryable):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            request=request,
            headers={"Retry-After": "7"},
            json={"error": {"message": "synthetic failure"}},
        )

    endpoint = provider(monkeypatch, handler)
    try:
        with pytest.raises(ProviderError) as failure:
            endpoint.complete(MESSAGES)
    finally:
        endpoint.close()

    assert failure.value.retryable is retryable
    assert failure.value.status_code == status
    assert failure.value.retry_after == 7
    assert KEY not in str(failure.value)


def test_mistral_malformed_http_body_is_rejected(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, text="not JSON")

    endpoint = provider(monkeypatch, handler)
    try:
        with pytest.raises(ProviderError, match="not JSON"):
            endpoint.complete(MESSAGES)
    finally:
        endpoint.close()


def test_mistral_timeout_is_retryable_and_does_not_expose_the_key(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    endpoint = provider(monkeypatch, handler)
    try:
        with pytest.raises(ProviderError) as failure:
            endpoint.complete(MESSAGES)
    finally:
        endpoint.close()

    assert failure.value.retryable is True
    assert failure.value.status_code is None
    assert KEY not in str(failure.value)


def test_mistral_schema_invalid_output_is_rejected_locally(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return response(request, content={"definition": "missing fields"})

    endpoint = provider(monkeypatch, handler)
    chain = ProviderChain(providers=[endpoint], max_attempts=1)
    try:
        with pytest.raises(StructuredResponseError):
            generate_structured(chain, MESSAGES, EntryDraft, max_repairs=0)
    finally:
        chain.close()
